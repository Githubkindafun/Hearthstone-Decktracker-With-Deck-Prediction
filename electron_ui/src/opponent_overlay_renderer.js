
// Konfiguracja
const BASE_ROWS = 15;
const GAP_PX = 2;
const STAR = "\u2605";

let cardsMap = {};
let cardDbReady = false;
let aliasMap = {};

let lastState = null;

function setFullImageCandidates(row, cardId, version) {
  const safeCardId = encodeURIComponent(String(cardId || ""));
  const v = `?v=${Number(version || 0)}`;

  row.dataset.full1 = `../data/cards_photos/card${safeCardId}.webp${v}`;
  row.dataset.full2 = `../data/cards_photos/card${safeCardId}.png${v}`;
  row.dataset.full3 = `../data/cards_photos/${safeCardId}.webp${v}`;
  row.dataset.full4 = `../data/cards_photos/${safeCardId}.png${v}`;
}

function setupFullCardTooltip() {
  const tip = document.getElementById("cardTooltip");
  const tipImg = document.getElementById("cardTooltipImg");
  if (!tip || !tipImg) return;

  let currentRow = null;
  let loadingRow = null;

  let lastX = 0;
  let lastY = 0;

  const MARGIN = 6;
  const OFFSET = 14;

  function hide() {
    tip.classList.add("hidden");
    tipImg.removeAttribute("src");
    currentRow = null;
    loadingRow = null;
  }

  function candidatesFromRow(row) {
    return [row.dataset.full1, row.dataset.full2, row.dataset.full3, row.dataset.full4].filter(Boolean);
  }

  function position(mouseX, mouseY) {
    const r = tip.getBoundingClientRect();

    let x = mouseX + OFFSET;
    let y = mouseY + OFFSET;

    if (x + r.width > window.innerWidth - MARGIN) {
      x = mouseX - r.width - OFFSET;
    }
    if (y + r.height > window.innerHeight - MARGIN) {
      y = mouseY - r.height - OFFSET;
    }

    x = Math.max(MARGIN, Math.min(x, window.innerWidth - r.width - MARGIN));
    y = Math.max(MARGIN, Math.min(y, window.innerHeight - r.height - MARGIN));

    tip.style.left = `${x}px`;
    tip.style.top  = `${y}px`;
  }

  function showForRow(row, x, y) {
    const candidates = candidatesFromRow(row);
    if (!candidates.length) return;

    currentRow = row;
    loadingRow = row;
    lastX = x;
    lastY = y;

    tip.classList.add("hidden");

    let idx = 0;

    tipImg.onload = () => {
      if (loadingRow !== row) return;
      tip.classList.remove("hidden");
      position(lastX, lastY);
    };

    tipImg.onerror = () => {
      if (loadingRow !== row) return;
      idx += 1;
      if (idx < candidates.length) {
        tipImg.src = candidates[idx];
      } else {
        hide();
      }
    };

    tipImg.src = candidates[idx];
  }

  document.addEventListener("mousemove", (e) => {
    lastX = e.clientX;
    lastY = e.clientY;
    if (currentRow && !tip.classList.contains("hidden")) {
      position(lastX, lastY);
    }
  });

  document.addEventListener("mouseover", (e) => {
    const row = e.target.closest && e.target.closest(".cardRow");
    if (!row || row === currentRow) return;
    showForRow(row, e.clientX, e.clientY);
  });

  document.addEventListener("mouseout", (e) => {
    if (!currentRow) return;
    const stillInside =
      e.relatedTarget &&
      e.relatedTarget.closest &&
      e.relatedTarget.closest(".cardRow") === currentRow;
    if (!stillInside) hide();
  });

  window.addEventListener("blur", hide);
}

// Funkcje pomocnicze
function imgSrcWebp(cardId, version) {
  return `../data/cards_photos/${encodeURIComponent(String(cardId || ""))}.webp?v=${version || 0}`;
}
function imgSrcPng(cardId, version) {
  return `../data/cards_photos/${encodeURIComponent(String(cardId || ""))}.png?v=${version || 0}`;
}

function updateDebug(msg) {
  const el = document.getElementById("debugStatus");
  if (el) el.textContent = msg;
}

// 1. Inicjalizacja
async function init() {
  updateDebug("JS Started. Loading DB...");
  
  try {
    const allCards = await window.dt.getAllCards();
    
    if (!allCards || allCards.length === 0) {
      updateDebug("ERROR: DB Empty!");
    } else {
      allCards.forEach(c => {
        if (c.cardId) cardsMap[String(c.cardId)] = c; 
        if (c.realId) cardsMap[String(c.realId)] = c; 
      });
      cardDbReady = true;
      updateDebug("DB Loaded (" + allCards.length + "). Waiting for state...");
    }

    const aliases = await window.dt.getCardAliases();
    if (aliases && typeof aliases === "object") {
      aliasMap = aliases;
    }
    
    const state = await window.dt.getOverlayState();
    render(state);

  } catch (err) {
    updateDebug("Init Error: " + String(err));
  }
}

// 2. Renderowanie
function render(state) {
  lastState = state;
  const container = document.getElementById("deckList");
  if (!container) return;

  if (!state) return;

  const fixedIds = state.fixed || [];
  const version = Number(state.opponentImagesVersion || 0);
  
  if (fixedIds.length === 0) {
    // ZMIANA: Użycie klasy .msg i tekstu w kursywie (CSS w HTML załatwia resztę)
    container.innerHTML = `<div class="msg">No opponent cards yet.</div>`;
    return;
  }

  container.innerHTML = "";

  const counts = {};
  fixedIds.forEach(id => {
    counts[id] = (counts[id] || 0) + 1;
  });

  const displayCards = [];
  
  Object.keys(counts).forEach(id => {
    const resolvedId = aliasMap[String(id)] || id;
    const def = cardsMap[String(resolvedId)] || cardsMap[String(id)];
    
    if (def) {
      if (def.type === "HERO_POWER" || def.type === "ENCHANTMENT") {
        return; 
      }
      displayCards.push({ ...def, cardId: String(id), qty: counts[id] });
    } else {
      
      displayCards.push({
        cardId: id,
        name: `Unknown (${id})`,
        mana: 0,
        rarity: "COMMON",
        qty: counts[id],
        isUnknown: true
      });
    }
  });

  displayCards.sort((a, b) => (a.mana - b.mana) || a.name.localeCompare(b.name));

  const rowsForSizing = Math.max(BASE_ROWS, displayCards.length);
  const listH = container.clientHeight || 400;
  const rowH = Math.max(10, Math.floor((listH - GAP_PX * (rowsForSizing - 1)) / rowsForSizing));
  
  document.documentElement.style.setProperty("--rowH", `${rowH}px`);
  document.documentElement.style.setProperty("--gap", `${GAP_PX}px`);

  // HTML
  displayCards.forEach(c => {
    const isLegendary = c.rarity === "LEGENDARY";
    
    const row = document.createElement("div");
    row.className = "cardRow";

    if (!c.isUnknown) {
      setFullImageCandidates(row, c.cardId, version);
    }

    const qtyDiv = document.createElement("div");
    qtyDiv.className = "qtyLeft" + (isLegendary ? " legendary" : "");
    qtyDiv.textContent = isLegendary ? STAR : String(c.qty);

    const imgWrap = document.createElement("div");
    imgWrap.className = "imgWrap";

    if (c.isUnknown) {
       imgWrap.innerHTML = `<div style="padding:2px; color:#f55; font-size:10px;">${c.name}</div>`;
    } else {
       const img = document.createElement("img");
       img.src = imgSrcWebp(c.cardId, version);
       img.onerror = () => {
         if (!img.dataset.fallback) {
           img.dataset.fallback = "1";
           img.src = imgSrcPng(c.cardId, version);
         } else {
           img.style.display = "none";
           const txt = document.createElement("div");
           txt.className = "fallbackName";
           txt.textContent = c.name;
           imgWrap.appendChild(txt);
         }
       };
       imgWrap.appendChild(img);
    }

    if (!c.isUnknown) {
      const manaDiv = document.createElement("div");
      manaDiv.className = "manaOver";
      manaDiv.textContent = String(c.mana);
      imgWrap.appendChild(manaDiv);

      const cardName = document.createElement("div");
      cardName.className = "cardName";
      cardName.textContent = c.name || "";
      imgWrap.appendChild(cardName);
    }

    row.appendChild(qtyDiv);
    row.appendChild(imgWrap);
    container.appendChild(row);
  });
}

window.addEventListener("DOMContentLoaded", () => {
  setupFullCardTooltip();

  window.dt.onOverlayState(render);
  init();

  window.addEventListener("resize", () => {
    if (lastState) render(lastState);
  });
});