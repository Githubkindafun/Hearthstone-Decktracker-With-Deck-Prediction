const { app, BrowserWindow, screen, globalShortcut, Menu, ipcMain, dialog } = require("electron");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const nwm = require("node-window-manager");
const windowManager = nwm.windowManager;
const NwmWindowCtor = nwm.Window;

// --- OKNA ---
let overlayWin = null;    // Layer "standard": Prawa strona (Twój deck)
let opponentWin = null;   // Layer "standard": Lewa strona (Karty zagrane przez przeciwnika)

let guessWin = null;      // Layer "guess": Lewa strona (Zgadywanie decku)
let fullDeckWin = null;   // Layer "guess": Prawa strona (Podgląd wybranego decku)

let menuWin = null;

// --- STANY ---
let overlayEnabled = true;

// activeLayer:
// "standard" = Twój tracker (P) + Przeciwnik tracker (L)
// "guess"    = Guesser (L) + Full Deck Preview (P)
let activeLayer = "standard"; 

let clickThrough = false;   // Domyślnie false (klikalne)
let isQuitting = false;

// ===== data paths (electron_ui/data/...) =====
const DATA_DIR = path.join(__dirname, "..", "data");
const DECKS_DIR = path.join(DATA_DIR, "decks");
const PHOTOS_DIR = path.join(DATA_DIR, "cards_photos");

const SELECTED_DECK_PATH = path.join(DATA_DIR, "selectedDeck.json");
const ALL_CARDS_PATH = path.join(DATA_DIR, "all_cards.json");
const CARD_ALIAS_PATH = path.join(DATA_DIR, "dbfId_aliases.json");

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = 49777;

function ensureDirs() {
  for (const p of [DATA_DIR, DECKS_DIR, PHOTOS_DIR]) {
    if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
  }
  if (!fs.existsSync(SELECTED_DECK_PATH)) {
    fs.writeFileSync(SELECTED_DECK_PATH, JSON.stringify({ deckId: null }, null, 2), "utf8");
  }
}

function safeReadJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}
function writeJson(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), "utf8");
}

let backendSocket = null;
let backendConnected = false;
let backendBuf = "";
let backendReconnectTimer = null;
const backendQueue = [];
const pendingRequests = new Map();
let nextRequestId = 1;

let fixedCards = [];
let deckCounts = {};
let matchStage = "not_in_match";
const deckImagesReady = new Map();
const deckImagesVersion = new Map();
const deckImagesError = new Map();
let opponentImagesVersion = 0;

function deckImagesDir(deckId) {
  return path.join(DECKS_DIR, deckId, "cards_photos");
}

function setDeckImagesPending(deckId) {
  if (!deckId) return;
  deckImagesReady.set(deckId, false);
  deckImagesError.delete(deckId);
}

function bumpDeckImagesVersion(deckId) {
  const current = deckImagesVersion.get(deckId) || 0;
  deckImagesVersion.set(deckId, current + 1);
}

function setDeckImagesReady(deckId) {
  if (!deckId) return;
  deckImagesReady.set(deckId, true);
  deckImagesError.delete(deckId);
  bumpDeckImagesVersion(deckId);
}

function setDeckImagesError(deckId, error) {
  if (!deckId) return;
  deckImagesReady.set(deckId, false);
  deckImagesError.set(deckId, error || "unknown_error");
  bumpDeckImagesVersion(deckId);
}

function deckHasAllImages(deck) {
  if (!deck || !Array.isArray(deck.cards)) return true;
  const deckId = deck.id || "";
  if (!deckId) return true;
  const dir = deckImagesDir(deckId);
  if (!fs.existsSync(dir)) return false;

  const uniqueIds = new Set(
    deck.cards
      .map((c) => String(c.cardId || ""))
      .filter((id) => id)
  );

  for (const cardId of uniqueIds) {
    const imgPath = path.join(dir, `${cardId}.webp`);
    if (!fs.existsSync(imgPath)) return false;
  }
  return true;
}

function opponentImageExists(cardId) {
  if (!cardId) return false;
  const safeId = String(cardId);
  const webp = path.join(PHOTOS_DIR, `${safeId}.webp`);
  if (fs.existsSync(webp)) return true;
  const png = path.join(PHOTOS_DIR, `${safeId}.png`);
  return fs.existsSync(png);
}

function filterFixedCardsByImage(cards) {
  if (!Array.isArray(cards) || cards.length === 0) return [];
  return cards.filter((id) => opponentImageExists(id));
}

function isDeckImagesReady(deck) {
  const deckId = deck?.id;
  if (!deckId) return true;
  if (deckImagesReady.has(deckId)) return deckImagesReady.get(deckId);
  return deckHasAllImages(deck);
}

function normalizeFixedFromState(cards) {
  if (!Array.isArray(cards)) return [];
  const out = [];
  for (const item of cards) {
    if (!item || typeof item !== "object") continue;
    const player = String(item.player || "").toUpperCase();
    if (player && player !== "OPPOSING") continue;
    const dbfId = item.dbfId ?? item.cardId ?? item.id;
    if (dbfId === undefined || dbfId === null) continue;
    out.push(String(dbfId));
  }
  return out;
}

function setFixedCards(cards) {
  fixedCards = Array.isArray(cards) ? cards : [];
}

function setDeckCounts(counts) {
  if (counts && typeof counts === "object") {
    deckCounts = counts;
  } else {
    deckCounts = {};
  }
}

function setMatchStage(stage, notify = false) {
  if (typeof stage !== "string" || !stage) return;
  const changed = matchStage !== stage;
  matchStage = stage;
  if (notify && changed) {
    broadcastBackendEvent({ type: "match_stage", stage: matchStage });
  }
}

function applyRoundUpdate(msg, mergeDeckCounts = false) {
  let changed = false;
  const fixed = Array.isArray(msg?.fixed) ? msg.fixed : [];
  for (const item of fixed) {
    if (!item || typeof item !== "object") continue;
    const player = String(item.player || "").toUpperCase();
    if (player && player !== "OPPOSING") continue;
    const dbfId = item.dbfId ?? item.cardId ?? item.id;
    if (dbfId === undefined || dbfId === null) continue;
    fixedCards.push(String(dbfId));
    changed = true;
  }

  if (msg?.deck_counts && typeof msg.deck_counts === "object") {
    if (mergeDeckCounts) {
      for (const [dbfId, qty] of Object.entries(msg.deck_counts)) {
        const count = Number(qty) || 0;
        if (count > 0) {
          deckCounts[dbfId] = count;
        } else {
          delete deckCounts[dbfId];
        }
      }
    } else {
      deckCounts = msg.deck_counts;
    }
    changed = true;
  }

  if (matchStage !== "ended") {
    setMatchStage("in_match", true);
  }

  if (changed) broadcastOverlayState();
}

function clearFixedCards() {
  fixedCards = [];
  deckCounts = {};
  broadcastOverlayState();
}

function broadcastBackendEvent(payload) {
  // Dodano fullDeckWin do broadcastu
  for (const win of [overlayWin, menuWin, guessWin, opponentWin, fullDeckWin]) {
    if (!win || win.isDestroyed()) continue;
    win.webContents.send("dt:backendEvent", payload);
  }
}

function flushBackendQueue() {
  if (!backendSocket || !backendConnected) return;
  while (backendQueue.length > 0) backendSocket.write(backendQueue.shift());
}

function sendBackend(payload) {
  const line = JSON.stringify(payload) + "\n";
  if (backendSocket && backendConnected) {
    backendSocket.write(line);
    return;
  }
  backendQueue.push(line);
  connectBackend();
}

function rejectPendingRequests(reason) {
  for (const [id, pending] of pendingRequests.entries()) {
    clearTimeout(pending.timer);
    pending.reject(new Error(reason));
    pendingRequests.delete(id);
  }
}

function requestBackend(payload, timeoutMs = 2500) {
  const requestId = String(nextRequestId++);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error("Backend timeout"));
    }, timeoutMs);

    pendingRequests.set(requestId, { resolve, reject, timer });
    sendBackend({ ...payload, requestId });
  });
}

function handleBackendMessage(msg) {
  if (!msg || typeof msg !== "object") return;

  if (msg.requestId && pendingRequests.has(msg.requestId)) {
    const pending = pendingRequests.get(msg.requestId);
    clearTimeout(pending.timer);
    pendingRequests.delete(msg.requestId);
    pending.resolve(msg);
  }

  switch (msg.type) {
    case "step_fixed":
      break;
    case "game_state":
      setFixedCards(normalizeFixedFromState(msg.cards));
      setDeckCounts(msg.deck_counts);
      setMatchStage(msg.stage);
      broadcastBackendEvent({ type: "game_state", stage: msg.stage ?? matchStage });
      broadcastOverlayState();
      break;
    case "round_update":
      applyRoundUpdate(msg, false);
      break;
    case "instant_update":
      applyRoundUpdate(msg, true);
      break;
    case "game_init":
      setMatchStage("in_match", true);
      clearFixedCards();
      broadcastBackendEvent(msg);
      break;
    case "game_over":
      setMatchStage("ended", true);
      clearFixedCards();
      broadcastBackendEvent(msg);
      break;
    case "deck_images_ready":
      if (msg.deckId) {
        if (msg.error) setDeckImagesError(msg.deckId, msg.error);
        else setDeckImagesReady(msg.deckId);
      }
      broadcastOverlayState();
      broadcastBackendEvent(msg);
      break;
    case "opponent_images_ready":
      if (Array.isArray(msg.dbfIds) && msg.dbfIds.length > 0) {
        opponentImagesVersion += 1;
        broadcastOverlayState();
      }
      break;
    case "opponent_guess_update":
      broadcastBackendEvent(msg);
      break;
    default:
      break;
  }
}

function scheduleBackendReconnect() {
  if (backendReconnectTimer) return;
  backendReconnectTimer = setTimeout(() => {
    backendReconnectTimer = null;
    connectBackend();
  }, 1500);
}

function connectBackend() {
  if (backendSocket) return;

  console.log("[backend] connect_attempt", BACKEND_HOST, BACKEND_PORT);
  backendSocket = new net.Socket();
  backendSocket.setNoDelay(true);

  backendSocket.on("connect", () => {
    backendConnected = true;
    console.log("[backend] connected");
    flushBackendQueue();
    requestBackend({ type: "get_game_state" }).catch(() => {});
  });

  backendSocket.on("data", (data) => {
    backendBuf += data.toString("utf8");
    let idx = backendBuf.indexOf("\n");
    while (idx !== -1) {
      const line = backendBuf.slice(0, idx).trim();
      backendBuf = backendBuf.slice(idx + 1);
      if (line) {
        try {
          handleBackendMessage(JSON.parse(line));
        } catch {}
      }
      idx = backendBuf.indexOf("\n");
    }
  });

  backendSocket.on("error", (err) => {
    console.log("[backend] error", err?.message || err);
  });

  backendSocket.on("close", () => {
    backendConnected = false;
    backendSocket = null;
    backendBuf = "";
    console.log("[backend] disconnected");
    rejectPendingRequests("Backend disconnected");
    scheduleBackendReconnect();
  });

  backendSocket.connect(BACKEND_PORT, BACKEND_HOST);
}

function normalizeAllCards(raw) {
  const arr = Array.isArray(raw) ? raw : (raw?.cards ?? []);
  return arr.map(c => ({
    cardId: String(c.dbfId ?? ""),
    realId: String(c.id ?? ""),
    name: String(c.name ?? ""),
    mana: Number(c.cost ?? c.mana ?? 0) || 0,
    rarity: String(c.rarity ?? "")
  })).filter(x => x.cardId && x.name);
}

function findDeckFile(deckId) {
  if (!deckId) return null;
  const dir = path.join(DECKS_DIR, deckId);
  if (fs.existsSync(dir) && fs.statSync(dir).isDirectory()) {
    const deckPath = path.join(dir, "deck.json");
    if (fs.existsSync(deckPath)) return deckPath;

    const altPath = path.join(dir, `${deckId}.json`);
    if (fs.existsSync(altPath)) return altPath;

    const files = fs.readdirSync(dir).filter(f => f.endsWith(".json"));
    if (files.length > 0) return path.join(dir, files[0]);
  }

  const legacyPath = path.join(DECKS_DIR, `${deckId}.json`);
  if (fs.existsSync(legacyPath)) return legacyPath;
  return null;
}

function listDeckFiles() {
  if (!fs.existsSync(DECKS_DIR)) return [];
  const entries = fs.readdirSync(DECKS_DIR, { withFileTypes: true });
  const decksById = new Map();

  for (const entry of entries) {
    if (entry.isDirectory()) {
      const deckId = entry.name;
      const filePath = findDeckFile(deckId);
      if (!filePath) continue;
      const deck = safeReadJson(filePath, null);
      if (deck?.id) decksById.set(deck.id, deck);
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      const deck = safeReadJson(path.join(DECKS_DIR, entry.name), null);
      if (deck?.id && !decksById.has(deck.id)) decksById.set(deck.id, deck);
    }
  }

  return [...decksById.values()];
}

function listDecks() {
  return listDeckFiles().map(d => ({
    id: d.id,
    name: d.name,
    cardCount: Array.isArray(d.cards)
      ? d.cards.reduce((s, c) => s + (Number(c.qty) || 0), 0)
      : 0
  }));
}

function loadDeck(deckId) {
  if (!deckId) return null;
  const filePath = findDeckFile(deckId);
  if (!filePath) return null;
  return safeReadJson(filePath, null);
}

function getSelectedDeckId() {
  return safeReadJson(SELECTED_DECK_PATH, { deckId: null })?.deckId ?? null;
}
function setSelectedDeckId(deckId) {
  writeJson(SELECTED_DECK_PATH, { deckId });
}

function computeOverlayState() {
  const deckId = getSelectedDeckId();
  const deck = loadDeck(deckId);
  const deckCountsPayload = deckCounts && typeof deckCounts === "object" ? deckCounts : {};
  const deckKey = deck?.id || deckId;
  const imagesReady = deck ? isDeckImagesReady(deck) : true;
  const imagesError = deckKey ? (deckImagesError.get(deckKey) || null) : null;
  const imagesVersion = deckKey ? (deckImagesVersion.get(deckKey) || 0) : 0;
  const fixedReady = filterFixedCardsByImage(fixedCards);
  
  return { 
    deckId, deck, 
    deck_counts: deckCountsPayload, 
    fixed: fixedReady, // Dla opponent_overlay
    imagesReady, imagesError, imagesVersion,
    opponentImagesVersion
  };
}

function broadcastOverlayState() {
  const state = computeOverlayState();
  if (overlayWin && !overlayWin.isDestroyed()) overlayWin.webContents.send("dt:overlayState", state);
  if (opponentWin && !opponentWin.isDestroyed()) opponentWin.webContents.send("dt:overlayState", state);
  // GuessWin i FullDeckWin nie używają dt:overlayState w ten sam sposób
}

// ===== IPC handlers =====
ipcMain.handle("dt:getAllCards", async () => {
  const raw = safeReadJson(ALL_CARDS_PATH, []);
  return normalizeAllCards(raw);
});

ipcMain.handle("dt:getCardAliases", async () => {
  return safeReadJson(CARD_ALIAS_PATH, {});
});

ipcMain.handle("dt:listDecks", async () => listDecks());
ipcMain.handle("dt:loadDeck", async (_e, deckId) => loadDeck(deckId));

ipcMain.handle("dt:saveDeck", async (_e, deck) => {
  if (!deck?.id) throw new Error("Deck missing id");
  const deckDir = path.join(DECKS_DIR, deck.id);
  if (!fs.existsSync(deckDir)) fs.mkdirSync(deckDir, { recursive: true });
  writeJson(path.join(deckDir, "deck.json"), deck);
  setDeckImagesPending(deck.id);
  sendBackend({ type: "deck_saved", deckId: deck.id });
  broadcastOverlayState();
  return { ok: true };
});

ipcMain.handle("dt:deleteDeck", async (_e, deckId) => {
  if (!deckId || typeof deckId !== "string") return { ok: false, error: "Invalid deckId" };
  const safeNameRe = /^[a-z0-9-]+$/i;
  if (!safeNameRe.test(deckId)) return { ok: false, error: "Invalid deckId format" };
  const filePath = path.join(DECKS_DIR, `${deckId}.json`);
  const deckDir = path.join(DECKS_DIR, deckId);
  const resolved = path.resolve(filePath);
  const decksResolved = path.resolve(DECKS_DIR);
  if (!resolved.startsWith(decksResolved + path.sep)) return { ok: false, error: "Path escape blocked" };
  const resolvedDir = path.resolve(deckDir);
  if (!resolvedDir.startsWith(decksResolved + path.sep)) return { ok: false, error: "Path escape blocked" };
  if (!fs.existsSync(filePath) && !fs.existsSync(deckDir)) return { ok: false, error: "Deck not found" };
  if (fs.existsSync(deckDir)) {
    fs.rmSync(deckDir, { recursive: true, force: true });
  } else {
    fs.unlinkSync(filePath);
  }
  if (getSelectedDeckId() === deckId) setSelectedDeckId(null);
  deckImagesReady.delete(deckId);
  deckImagesError.delete(deckId);
  deckImagesVersion.delete(deckId);
  broadcastOverlayState();
  return { ok: true };
});

ipcMain.handle("dt:setSelectedDeck", async (_e, deckId) => {
  setSelectedDeckId(deckId);
  sendBackend({ type: "deck_selected", deckId });
  requestBackend({ type: "get_game_state" }).catch(() => {});
  broadcastOverlayState();
  return { ok: true };
});

ipcMain.handle("dt:getSelectedDeck", async () => ({ deckId: getSelectedDeckId() }));
ipcMain.handle("dt:getOverlayState", async () => computeOverlayState());
ipcMain.handle("dt:requestGameState", async () => {
  try {
    const res = await requestBackend({ type: "get_game_state" });
    return { ok: true, cards: res?.cards ?? [], stage: res?.stage ?? null };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
});

// Handler dla Deck Guessera (detale oponenta)
ipcMain.handle("dt:selectOpponentDeck", async (_e, { archetypeId, deckName, deckId }) => {
  try {
    const res = await requestBackend({ 
      type: "get_opponent_details", 
      archetypeId, 
      deckName,
      deckId // <--- TO JEST KLUCZOWE! Dodajemy deckId do JSONa wysyłanego do Pythona
    });
    return res; 
  } catch (err) {
    return { ok: false, error: String(err) };
  }
});

// Handler dla Dialog Boxów
ipcMain.handle("dt:messageBox", async (e, opts) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  const {
    type = "info", title = "Decktracker", message = "", detail = "",
    buttons = ["OK"], defaultId = 0, cancelId = buttons.length - 1
  } = (opts || {});
  const result = await dialog.showMessageBox(win, {
    type, title, message, detail, buttons, defaultId, cancelId, noLink: true
  });
  try {
    if (win && !win.isDestroyed()) {
      win.blur(); win.focus(); win.webContents.focus();
    }
  } catch {}
  return { response: result.response };
});

// Handler dla refocusMenu
ipcMain.handle("dt:refocusMenu", async () => {
  if (!menuWin || menuWin.isDestroyed()) return { ok: false };
  try {
    if (!menuWin.isVisible()) menuWin.show();
    menuWin.blur(); menuWin.focus(); menuWin.webContents.focus();
  } catch {}
  return { ok: true };
});

// NOWE IPC: Przekazywanie podglądu z Guessera do FullDeckWin
ipcMain.on("dt:previewOpponentDeck", (event, deckData) => {
    if (fullDeckWin && !fullDeckWin.isDestroyed()) {
        fullDeckWin.webContents.send("dt:setFullDeckPreview", deckData);
    }
});


// ========================= Overlay positioning / Hearthstone attach =========================
const HS_EXE_RE = /\\Hearthstone\.exe$/i;

const PANEL_WIDTH_RATIO = 3 / 25;
const PANEL_HEIGHT_RATIO = 0.50;

const BASE_ROWS = 15;
const PANEL_PAD_PX = 4;
const ROW_GAP_PX = 2;
const HEADER_H_PX = 16;
const TITLE_GAP_PX = 2;

const MARGIN_LEFT_PX = 10;
const MARGIN_RIGHT_PX = 10;
const MARGIN_TOP_PX = 65; // ZMIANA: Zwiększony margines, aby nie zasłaniać nicku
const MARGIN_BOTTOM_PX = 10;
const TITLE_BAR_DIP = 32;

const POLL_MS = 10;

let overlayNwmWindow = null;
let opponentNwmWindow = null;
let guessNwmWindow = null;
let fullDeckNwmWindow = null; // Nowe
let attachTimer = null;

function safeGetInfo(win) {
  try {
    if (typeof win.getInfo === "function") return win.getInfo();
  } catch {}
  return null;
}

function isHearthstoneWindow(win) {
  if (!win) return false;
  const info = safeGetInfo(win);
  const exePath = info?.path ?? win.path;
  if (exePath && HS_EXE_RE.test(exePath)) return true;
  const title = (info?.title ?? (typeof win.getTitle === "function" ? win.getTitle() : "") ?? "").trim();
  return title.toLowerCase() === "hearthstone";
}

function findHearthstoneWindow() {
  try {
    const wins = windowManager.getWindows();
    const candidates = wins
      .filter((w) => {
        try { return typeof w.isWindow !== "function" ? true : w.isWindow(); } catch { return false; }
      })
      .filter(isHearthstoneWindow)
      .map((w) => ({ w, b: w.getBounds?.() }))
      .filter((x) => x.b && x.b.width > 200 && x.b.height > 200);

    if (!candidates.length) return null;
    candidates.sort((a, b) => b.b.width * b.b.height - a.b.width * a.b.height);
    return candidates[0].w;
  } catch {
    return null;
  }
}

function isHearthstoneForeground(hsWin) {
  try {
    const active = windowManager.getActiveWindow();
    if (!active || !hsWin) return false;
    if (active.id === hsWin.id) return true;
    if (isHearthstoneWindow(active)) return true;
    return false;
  } catch {
    return false;
  }
}

function getWindowHwndAsNumber(win) {
  if (!win) return 0;
  const buf = win.getNativeWindowHandle();
  if (buf.length === 8) return Number(buf.readBigUInt64LE(0));
  return buf.readUInt32LE(0);
}

function tryAttachOverlayAsOwnedWindow(hsWin) {
  if (!NwmWindowCtor || !hsWin) return;

  const windows = [
      { win: overlayWin, nwm: overlayNwmWindow, setNwm: (n) => overlayNwmWindow = n },
      { win: opponentWin, nwm: opponentNwmWindow, setNwm: (n) => opponentNwmWindow = n },
      { win: guessWin, nwm: guessNwmWindow, setNwm: (n) => guessNwmWindow = n },
      { win: fullDeckWin, nwm: fullDeckNwmWindow, setNwm: (n) => fullDeckNwmWindow = n }
  ];

  windows.forEach(({ win, nwm, setNwm }) => {
    try {
        if (win && !nwm) {
            const hwnd = getWindowHwndAsNumber(win);
            if (hwnd) setNwm(new NwmWindowCtor(hwnd));
        }
        if (nwm && typeof nwm.setOwner === "function") {
            nwm.setOwner(hsWin);
        }
    } catch {}
  });
}

// Ujednolicona funkcja do obliczania granic
function computeBoundsUnified(hsDip, rowsForSizing, side, mode = "dynamic") {
  // Common width calculation
  const baseWidth = Math.round(hsDip.width * PANEL_WIDTH_RATIO);
  // Standardized width: base + 20 (padding/scrollbar buffer)
  const width = baseWidth + 20;

  let height;
  if (mode === "dynamic") {
    // Height based on content rows (Standard Overlay / Opponent Overlay)
    const baseHeight = Math.round(hsDip.height * PANEL_HEIGHT_RATIO);
    const baseListHeight = baseHeight - (PANEL_PAD_PX * 2) - HEADER_H_PX - TITLE_GAP_PX;
    const rowH = Math.max(10, Math.floor((baseListHeight - ROW_GAP_PX * (BASE_ROWS - 1)) / BASE_ROWS));
    const rows = Math.max(BASE_ROWS, Number(rowsForSizing) || 0);
    const listHeight = (rows * rowH) + (ROW_GAP_PX * (rows - 1));
    height = (PANEL_PAD_PX * 2) + HEADER_H_PX + TITLE_GAP_PX + listHeight;
    const maxHeight = Math.max(80, Math.floor(hsDip.height - MARGIN_TOP_PX - MARGIN_BOTTOM_PX));
    if (height > maxHeight) height = maxHeight;
  } else {
    // Fixed ratio height (Guesser / Full Deck)
    height = Math.min(
        Math.round(hsDip.height * 0.70),
        Math.floor(hsDip.height - MARGIN_TOP_PX - MARGIN_BOTTOM_PX)
    );
  }

  // Standardized X Position
  const x = side === "left"
    ? Math.round(hsDip.x + MARGIN_LEFT_PX)
    : Math.round(hsDip.x + hsDip.width - width - MARGIN_RIGHT_PX);
  
  // Standardized Y Position
  const y = Math.round(hsDip.y + MARGIN_TOP_PX);

  return { x, y, width, height };
}

function applyClickThrough() {
    const wins = [overlayWin, opponentWin, guessWin, fullDeckWin];
    wins.forEach(w => {
        if (w && !w.isDestroyed()) w.setIgnoreMouseEvents(clickThrough, { forward: true });
    });
}

// ===================== LOGIKA POZYCJONOWANIA WARSTW =====================

function updateOverlayPosition() {
  const allWins = [overlayWin, opponentWin, guessWin, fullDeckWin];

  if (!overlayEnabled || matchStage !== "in_match") {
    allWins.forEach(w => { if (w && w.isVisible()) w.hide(); });
    return;
  }

  const hsWin = findHearthstoneWindow();
  if (!hsWin || !isHearthstoneForeground(hsWin)) {
    allWins.forEach(w => { if (w && w.isVisible()) w.hide(); });
    return;
  }

  tryAttachOverlayAsOwnedWindow(hsWin);
  const hsBounds = hsWin.getBounds();
  const display = screen.getDisplayMatching(hsBounds);
  const bounds = display?.bounds ?? screen.getPrimaryDisplay().bounds;
  const nearFullscreen =
    Math.abs(hsBounds.width - bounds.width) <= 2 &&
    Math.abs(hsBounds.height - bounds.height) <= 2;
  const titleOffset = nearFullscreen ? 0 : TITLE_BAR_DIP;
  const hsDip = {
    x: hsBounds.x,
    y: hsBounds.y + titleOffset,
    width: hsBounds.width,
    height: Math.max(0, hsBounds.height - titleOffset),
  };

  // === WARSTWA 1: STANDARD (TRACKING) ===
  // Lewa: Opponent, Prawa: Player
  if (activeLayer === "standard") {
    // Ukrywamy Guess Mode
    if (guessWin && guessWin.isVisible()) guessWin.hide();
    if (fullDeckWin && fullDeckWin.isVisible()) fullDeckWin.hide();

    // 1. Player Overlay (PRAWA STRONA)
    if (overlayWin) {
      const deckId = getSelectedDeckId();
      const deck = loadDeck(deckId);
      const uniqueCards = Array.isArray(deck?.cards) ? deck.cards.length : 0;
      const rowsForSizing = Math.max(BASE_ROWS, uniqueCards);
      const b = computeBoundsUnified(hsDip, rowsForSizing, "right", "dynamic");
      overlayWin.setBounds(b, false);
      if (!overlayWin.isVisible()) overlayWin.showInactive();
    }

    // 2. Opponent Tracker (LEWA STRONA)
    if (opponentWin) {
      const uniqueFixed = new Set(fixedCards).size;
      const rowsForSizing = Math.max(BASE_ROWS, uniqueFixed);
      const b = computeBoundsUnified(hsDip, rowsForSizing, "left", "dynamic");
      opponentWin.setBounds(b, false);
      if (!opponentWin.isVisible()) opponentWin.showInactive();
    }
  } 
  
  // === WARSTWA 2: GUESS (PREDYKCJA) ===
  // Lewa: Guesser, Prawa: Full Deck Preview
  else if (activeLayer === "guess") {
    // Ukrywamy Standard Mode
    if (overlayWin && overlayWin.isVisible()) overlayWin.hide();
    if (opponentWin && opponentWin.isVisible()) opponentWin.hide();

    // 1. Guess Overlay (LEWA STRONA)
    if (guessWin) {
      const b = computeBoundsUnified(hsDip, 0, "left", "fixed"); 
      guessWin.setBounds(b, false);
      if (!guessWin.isVisible()) guessWin.showInactive();
    }

    // 2. Full Deck Preview (PRAWA STRONA)
    if (fullDeckWin) {
      const b = computeBoundsUnified(hsDip, 0, "right", "fixed");
      fullDeckWin.setBounds(b, false);
      if (!fullDeckWin.isVisible()) fullDeckWin.showInactive();
    }
  }
}

// === TWORZENIE OKIEN ===

function createCommonWindow(filename) {
    const w = new BrowserWindow({
        width: 300, height: 600,
        frame: false, transparent: true,
        resizable: false, movable: false, focusable: false, show: false,
        alwaysOnTop: false, skipTaskbar: true, hasShadow: false,
        webPreferences: { contextIsolation: true, preload: path.join(__dirname, "preload.js") }
    });
    w.loadFile(path.join(__dirname, filename));
    return w;
}

function createOverlayWindow() {
  overlayWin = createCommonWindow("overlay.html");
}

function createOpponentWindow() {
  opponentWin = createCommonWindow("opponent_overlay.html");
}

function createGuessWindow() {
  guessWin = createCommonWindow("guess_overlay.html");
}

function createFullDeckWindow() {
  fullDeckWin = createCommonWindow("full_deck_overlay.html");
}

function createMenuWindow() {
  menuWin = new BrowserWindow({
    width: 900, height: 600, show: false,
    webPreferences: { contextIsolation: true, preload: path.join(__dirname, "preload.js") }
  });
  menuWin.loadFile(path.join(__dirname, "menu.html"));
  menuWin.on("close", (e) => {
    if (!isQuitting) { e.preventDefault(); menuWin.hide(); }
  });
  menuWin.on("closed", () => { menuWin = null; });
}

function toggleOverlayLayer() {
  activeLayer = (activeLayer === "standard") ? "guess" : "standard";
  updateOverlayPosition(); // Wymuś odświeżenie
}

function toggleMenu() {
  if (!menuWin || menuWin.isDestroyed()) {
    createMenuWindow();
    menuWin.show(); menuWin.focus(); menuWin.moveTop?.(); return;
  }
  if (menuWin.isVisible()) { menuWin.hide(); }
  else { menuWin.show(); menuWin.focus(); menuWin.moveTop?.(); }
}

function toggleClickThrough() {
  clickThrough = !clickThrough;
  applyClickThrough();
}

function registerHotkeys() {
  globalShortcut.register("CommandOrControl+Shift+D", toggleOverlayLayer);
  globalShortcut.register("CommandOrControl+Shift+M", toggleMenu);
  globalShortcut.register("CommandOrControl+Shift+T", toggleClickThrough);
}

function createApplicationMenu() {
  const template = [{ label: "File", submenu: [{ label: "Exit", accelerator: "Alt+F4", click: () => { isQuitting = true; app.quit(); } }] }];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.on("before-quit", () => { isQuitting = true; });

app.whenReady().then(() => {
  ensureDirs();
  connectBackend();

  setSelectedDeckId(null);

  createOverlayWindow();
  overlayWin.webContents.on("did-finish-load", () => broadcastOverlayState());

  createOpponentWindow();
  opponentWin.webContents.on("did-finish-load", () => broadcastOverlayState());

  createGuessWindow();
  // Guesser i FullDeck nie potrzebują broadcastOverlayState przy loadzie, bo działają na eventach

  createFullDeckWindow();
  
  applyClickThrough();

  fs.watchFile(SELECTED_DECK_PATH, { interval: 300 }, broadcastOverlayState);

  createMenuWindow();
  createApplicationMenu();
  registerHotkeys();

  attachTimer = setInterval(updateOverlayPosition, POLL_MS);
});

app.on("will-quit", () => {
  if (attachTimer) clearInterval(attachTimer);
  globalShortcut.unregisterAll();
});