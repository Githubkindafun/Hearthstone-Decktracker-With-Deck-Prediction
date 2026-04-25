
function slugify(s) {
  return String(s || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}
function normRarity(r) { return String(r || "").toUpperCase(); }
function toMana(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toQty(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

function normalizeName(name) {
  return String(name || "").trim().toLowerCase();
}

function buildCardIndex(cards) {
  const map = new Map();
  for (const c of (cards || [])) {
    const key = normalizeName(c.name);
    if (!key) continue;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(c);
  }
  return map;
}

function findCardByName(name, mana) {
  const list = cardIndex.get(normalizeName(name));
  if (!list || list.length === 0) return null;
  const wantedMana = Number(mana);
  if (Number.isFinite(wantedMana)) {
    const exact = list.find(c => Number(c.mana) === wantedMana);
    if (exact) return exact;
  }
  return list[0];
}

function parseDeckText(text) {
  const lines = String(text || "").split(/\r?\n/);
  let deckName = "";
  const cards = [];

  for (const line of lines) {
    if (!deckName) {
      const nameMatch = line.match(/^###\s*(.+)$/);
      if (nameMatch) deckName = nameMatch[1].trim();
    }
    const cardMatch = line.match(/^\s*#?\s*(\d+)x\s*\((\d+)\)\s+(.+?)\s*$/);
    if (!cardMatch) continue;
    const qty = Number(cardMatch[1]);
    const mana = Number(cardMatch[2]);
    const name = String(cardMatch[3] || "").trim();
    if (!name) continue;
    cards.push({ qty, mana, name });
  }

  return { deckName, cards };
}

let allCards = [];
let builder = new Map();
let editingDeckId = null;
let cardIndex = new Map();

let flashTimer = null;

function focusDeckName({ select = false } = {}) {
  setTimeout(() => {
    const el = document.getElementById("deckName");
    if (!el) return;
    el.focus();
    if (select) el.select();
  }, 0);
}

async function afterDialog(select = false) {
  // With native dialogs this is usually unnecessary,
  // but keeping it makes the UI feel consistent.
  try { await window.dt.refocusMenu(); } catch {}
  focusDeckName({ select });
}

function flashMessage(text, ms = 1500) {
  const info = document.getElementById("editInfo");
  if (!info) return;

  info.textContent = text;

  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    updateEditInfoText();
  }, ms);
}

function updateEditInfoText() {
  const info = document.getElementById("editInfo");
  if (!info) return;

  if (!editingDeckId) {
    info.textContent = "";
    return;
  }

  const currentName = document.getElementById("deckName")?.value?.trim() || "";
  info.textContent = currentName
    ? `Editing: ${currentName} (id: ${editingDeckId})`
    : `Editing deck id: ${editingDeckId}`;
}

function setEditMode(deckIdOrNull) {
  editingDeckId = deckIdOrNull;

  const cancelBtn = document.getElementById("cancelEditBtn");
  const saveBtn = document.getElementById("saveDeckBtn");

  if (editingDeckId) {
    if (cancelBtn) cancelBtn.style.display = "inline-block";
    if (saveBtn) saveBtn.textContent = "Save changes";
    updateEditInfoText();
  } else {
    const info = document.getElementById("editInfo");
    if (info) info.textContent = "";
    if (cancelBtn) cancelBtn.style.display = "none";
    if (saveBtn) saveBtn.textContent = "Save deck";
  }
}

function clearBuilderUI({ clearName = true } = {}) {
  builder.clear();
  renderBuilder();

  const deckNameEl = document.getElementById("deckName");
  const searchEl = document.getElementById("cardSearch");
  const suggEl = document.getElementById("suggestions");

  if (clearName && deckNameEl) deckNameEl.value = "";
  if (searchEl) searchEl.value = "";
  if (suggEl) suggEl.innerHTML = "";
}

function makeUniqueDeckId(deckName, decks) {
  const base = slugify(deckName) || "deck";
  const used = new Set((decks || []).map(d => String(d.id)));
  if (!used.has(base)) return base;

  let i = 2;
  while (used.has(`${base}-${i}`)) i++;
  return `${base}-${i}`;
}

// ✅ status placeholder only (no logic)
function setStatusPlaceholder() {
  const el = document.getElementById("statusLine");
  if (!el) return;
  el.textContent = "Status: Waiting for backend...";
}

function setStatus(text) {
  const el = document.getElementById("statusLine");
  if (!el) return;
  el.textContent = text;
}

function stageToStatus(stage) {
  switch (String(stage || "").toLowerCase()) {
    case "in_match":
      return "Status: In match";
    case "ended":
      return "Status: Match ended";
    case "not_in_match":
      return "Status: Not in match";
    default:
      return null;
  }
}

function setStatusFromStage(stage) {
  const text = stageToStatus(stage);
  if (text) setStatus(text);
}

async function refreshDecks() {
  const decks = await window.dt.listDecks();
  const selected = await window.dt.getSelectedDeck();
  const selectedId = selected?.deckId ?? null;

  const deckList = document.getElementById("deckList");
  deckList.innerHTML = "";

  for (const d of decks) {
    const row = document.createElement("div");
    row.className = "deckRow";
    if (selectedId && d.id === selectedId) row.classList.add("deckSelected");

    const left = document.createElement("div");
    left.innerHTML = `
      <div><b>${d.name}</b> <span class="muted">(${d.cardCount} cards)</span></div>
      <div class="muted">id: ${d.id}</div>
    `;

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.gap = "8px";

    const btnSelect = document.createElement("button");
    btnSelect.textContent = "Select";
    btnSelect.onclick = async () => {
      await window.dt.setSelectedDeck(d.id);

      await window.dt.alert(
        `Selected deck: ${d.name}`,
        `ID: ${d.id}\nCards: ${d.cardCount}`,
        "Deck Selected"
      );
      await afterDialog(false);

      await refreshDecks();
    };

    const btnEdit = document.createElement("button");
    btnEdit.textContent = "Edit";
    btnEdit.onclick = async () => {
      const full = await window.dt.loadDeck(d.id);
      if (!full) return;

      builder.clear();
      for (const c of (full.cards || [])) {
        const cardId = String(c.cardId);
        builder.set(cardId, {
          cardId,
          name: String(c.name || ""),
          mana: toMana(c.mana ?? c.cost ?? 0),
          rarity: String(c.rarity ?? ""),
          qty: toQty(c.qty)
        });
      }

      document.getElementById("deckName").value = full.name || d.name;
      document.getElementById("cardSearch").value = "";
      document.getElementById("suggestions").innerHTML = "";

      setEditMode(full.id);
      renderBuilder();
      focusDeckName({ select: true });
    };

    const btnDelete = document.createElement("button");
    btnDelete.textContent = "Delete";
    btnDelete.onclick = async () => {
      const ok = await window.dt.confirm(
        `Delete deck "${d.name}"?`,
        `ID: ${d.id}\nThis will remove the deck file.`,
        "Delete Deck"
      );
      await afterDialog(false);
      if (!ok) return;

      const res = await window.dt.deleteDeck(d.id);
      if (!res?.ok) {
        await window.dt.alert(
          "Delete failed",
          String(res?.error || "unknown error"),
          "Error"
        );
        await afterDialog(false);
        return;
      }

      if (editingDeckId === d.id) {
        clearBuilderUI({ clearName: true });
        setEditMode(null);
      }

      await refreshDecks();
      flashMessage(`Deleted: ${d.name}`);
      focusDeckName({ select: true });
    };

    actions.appendChild(btnSelect);
    actions.appendChild(btnEdit);
    actions.appendChild(btnDelete);

    row.appendChild(left);
    row.appendChild(actions);
    deckList.appendChild(row);
  }
}

function renderBuilder() {
  const list = document.getElementById("builderList");
  list.innerHTML = "";

  const items = [...builder.values()].sort(
    (a, b) => (toMana(a.mana) - toMana(b.mana)) || a.name.localeCompare(b.name)
  );

  for (const c of items) {
    const row = document.createElement("div");
    row.className = "builderRow";

    const left = document.createElement("div");
    left.innerHTML = `<b>${c.name}</b> <span class="muted">(mana ${toMana(c.mana)}, ${normRarity(c.rarity) || "?"})</span>`;

    const controls = document.createElement("div");
    controls.className = "controls";

    const rarity = normRarity(c.rarity);
    const maxQty = rarity === "LEGENDARY" ? 1 : 2;

    const minus = document.createElement("button");
    minus.textContent = "-";
    minus.onclick = () => {
      c.qty = Math.max(0, toQty(c.qty) - 1);
      if (c.qty === 0) builder.delete(c.cardId);
      renderBuilder();
    };

    const label = document.createElement("span");
    label.className = "qty";
    label.textContent = `qty: ${c.qty}`;

    const plus = document.createElement("button");
    plus.textContent = "+";
    plus.onclick = () => {
      c.qty = Math.min(maxQty, toQty(c.qty) + 1);
      renderBuilder();
    };

    controls.appendChild(minus);
    controls.appendChild(label);
    controls.appendChild(plus);

    row.appendChild(left);
    row.appendChild(controls);
    list.appendChild(row);
  }
}

function showSuggestions(q) {
  const box = document.getElementById("suggestions");
  box.innerHTML = "";
  if (!q || q.length < 2) return;

  const qq = q.toLowerCase();
  const matches = allCards
    .filter(c => {
      const name = String(c.name || "").toLowerCase();
      const realId = String(c.realId || "").toLowerCase();
      return name.includes(qq) || (realId && realId.includes(qq));
    })
    .slice(0, 10);

  for (const c of matches) {
    const b = document.createElement("button");
    b.className = "suggestion";
    b.textContent = `${c.name} (mana ${toMana(c.mana)}, ${normRarity(c.rarity) || "?"})`;

    b.onclick = () => {
      const cardId = String(c.cardId);
      const existing = builder.get(cardId);
      const maxQty = normRarity(c.rarity) === "LEGENDARY" ? 1 : 2;

      if (existing) existing.qty = Math.min(maxQty, toQty(existing.qty) + 1);
      else builder.set(cardId, { cardId, name: c.name, mana: toMana(c.mana), rarity: c.rarity, qty: 1 });

      document.getElementById("cardSearch").value = "";
      box.innerHTML = "";
      renderBuilder();
    };

    box.appendChild(b);
  }
}

async function saveDeck() {
  const wasEditing = !!editingDeckId;

  const name = document.getElementById("deckName").value.trim();
  if (!name) return flashMessage("Deck name required", 2000);
  if (builder.size === 0) return flashMessage("Add at least one card", 2000);

  const decks = await window.dt.listDecks();

  // warn on duplicate name (only when creating)
  if (!wasEditing) {
    const sameName = decks.filter(d => String(d.name || "").trim().toLowerCase() === name.toLowerCase());
    if (sameName.length > 0) {
      const ids = sameName.map(x => x.id).join(", ");
      const ok = await window.dt.confirm(
        `A deck named "${name}" already exists.`,
        `Existing IDs: ${ids}\n\nCreate another deck with the same name?`,
        "Duplicate Name"
      );
      await afterDialog(true);
      if (!ok) return;
    }
  }

  const id = wasEditing ? editingDeckId : makeUniqueDeckId(name, decks);

  const deck = {
    id,
    name,
    cards: [...builder.values()].map(c => ({
      cardId: String(c.cardId),
      name: String(c.name || ""),
      mana: toMana(c.mana),
      rarity: String(c.rarity || ""),
      qty: toQty(c.qty)
    }))
  };

  await window.dt.saveDeck(deck);
  await refreshDecks();

  clearBuilderUI({ clearName: true });
  setEditMode(null);

  flashMessage(
    wasEditing ? `Saved changes: ${deck.name} (id: ${deck.id})`
               : `Saved deck: ${deck.name} (id: ${deck.id})`
  );

  focusDeckName({ select: true });
}

async function importDeckFromPaste() {
  const pasteEl = document.getElementById("deckPaste");
  const text = String(pasteEl?.value || "").trim();
  if (!text) {
    await window.dt.alert("Paste a deck first", "Use the box above to paste the HSReplay deck list.", "Import Deck");
    await afterDialog(true);
    pasteEl?.focus();
    return;
  }

  const parsed = parseDeckText(text);
  const name = parsed.deckName || "Imported deck";
  const unresolved = [];

  builder.clear();
  for (const item of parsed.cards) {
    const def = findCardByName(item.name, item.mana);
    if (!def) {
      unresolved.push(`${item.qty}x (${item.mana}) ${item.name}`);
      continue;
    }
    const cardId = String(def.cardId);
    const existing = builder.get(cardId);
    const qty = toQty(item.qty);
    if (existing) {
      existing.qty = toQty(existing.qty) + qty;
    } else {
      builder.set(cardId, {
        cardId,
        name: String(def.name || ""),
        mana: toMana(def.mana),
        rarity: String(def.rarity || ""),
        qty,
      });
    }
  }

  document.getElementById("deckName").value = name;
  setEditMode(null);
  renderBuilder();

  if (builder.size === 0) {
    await window.dt.alert("No cards imported", "No matching cards were found in the paste.", "Import Deck");
    await afterDialog(true);
    return;
  }

  if (unresolved.length > 0) {
    const preview = unresolved.slice(0, 8).join("\n");
    const extra = unresolved.length > 8 ? `\n...and ${unresolved.length - 8} more` : "";
    await window.dt.alert("Some cards were skipped", `${preview}${extra}`, "Import Deck");
    await afterDialog(true);
  }

  const ok = await window.dt.confirm(
    `Import deck "${name}"?`,
    `Cards parsed: ${builder.size}\nSource: paste`,
    "Import Deck"
  );
  await afterDialog(true);
  if (!ok) return;

  await saveDeck();
  if (pasteEl) pasteEl.value = "";
}

window.addEventListener("DOMContentLoaded", async () => {
  setStatusPlaceholder();

  allCards = await window.dt.getAllCards();
  cardIndex = buildCardIndex(allCards);

  try {
    const res = await window.dt.requestGameState();
    if (res?.ok) setStatusFromStage(res?.stage);
  } catch {}

  await refreshDecks();
  renderBuilder();
  setEditMode(null);

  document.getElementById("cardSearch").addEventListener("input", (e) => showSuggestions(e.target.value));
  document.getElementById("deckName").addEventListener("input", () => updateEditInfoText());

  document.getElementById("saveDeckBtn").onclick = saveDeck;
  document.getElementById("importDeckBtn").onclick = importDeckFromPaste;

  document.getElementById("clearBtn").onclick = () => {
    clearBuilderUI({ clearName: !editingDeckId });
    updateEditInfoText();
    focusDeckName({ select: false });
  };

  document.getElementById("cancelEditBtn").onclick = () => {
    clearBuilderUI({ clearName: true });
    setEditMode(null);
    flashMessage("Edit cancelled");
    focusDeckName({ select: true });
  };

  window.dt.onBackendEvent((evt) => {
    if (!evt || !evt.type) return;
    switch (evt.type) {
      case "game_state":
        setStatusFromStage(evt.stage);
        break;
      case "match_stage":
        setStatusFromStage(evt.stage);
        break;
      case "game_init":
        setStatus("Status: Match started");
        break;
      case "game_over":
        setStatus("Status: Match ended");
        break;
      case "deck_images_ready":
        if (evt.error) {
          setStatus(`Status: Deck images failed (${evt.deckId || "deck"}): ${evt.error}`);
        } else {
          const count = typeof evt.count === "number" ? `, downloaded ${evt.count}` : "";
          setStatus(`Status: Deck images ready (${evt.deckId || "deck"}${count})`);
        }
        break;
      default:
        break;
    }
  });

  focusDeckName({ select: false });
});
