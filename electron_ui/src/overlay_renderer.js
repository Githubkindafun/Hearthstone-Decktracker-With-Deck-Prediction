
const BASE_ROWS = 15;
const GAP_PX = 2;

// ★ BLACK STAR (U+2605), decimal 9733
const STAR = "\u2605";

let lastState = null;

function normRarity(r) { return String(r || "").toUpperCase(); }

function fixedToCounts(fixed) {
  if (!fixed) return {};
  if (Array.isArray(fixed)) {
    const m = {};
    for (const id of fixed) m[id] = (m[id] || 0) + 1;
    return m;
  }
  if (typeof fixed === "object") return fixed;
  return {};
}

function imgSrc(deckId, cardId, version) {
  const safeDeckId = encodeURIComponent(String(deckId || ""));
  const safeCardId = encodeURIComponent(String(cardId || ""));
  const v = version ? `?v=${version}` : "";
  return `../data/decks/${safeDeckId}/cards_photos/${safeCardId}.webp${v}`;
}

function setFullImageCandidates(row, deckId, cardId, version) {
  const safeDeckId = encodeURIComponent(String(deckId || ""));
  const safeCardId = encodeURIComponent(String(cardId || ""));
  const v = version ? `?v=${version}` : "";

  row.dataset.full1 = `../data/decks/${safeDeckId}/card_photos/card${safeCardId}.webp${v}`;
  row.dataset.full2 = `../data/decks/${safeDeckId}/card_photos/card${safeCardId}.png${v}`;
  row.dataset.full3 = `../data/decks/${safeDeckId}/cards_photos/card${safeCardId}.webp${v}`;
  row.dataset.full4 = `../data/decks/${safeDeckId}/cards_photos/card${safeCardId}.png${v}`;
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


function applyRowHeight(rowsForSizing) {
  const container = document.getElementById("deckList");
  if (!container) return;

  const listH = container.clientHeight;

  const rowH = Math.max(
    10,
    Math.floor((listH - GAP_PX * (rowsForSizing - 1)) / rowsForSizing)
  );

  document.documentElement.style.setProperty("--rowH", `${rowH}px`);
  document.documentElement.style.setProperty("--gap", `${GAP_PX}px`);
}

function render(state) {
  lastState = state;

  const container = document.getElementById("deckList");
  container.innerHTML = "";

  const deck = state?.deck;
  if (!deck?.cards?.length) {
    container.innerHTML = `<div class="emptyMsg">No deck selected (select one in Menu).</div>`;
    return;
  }

  const deckId = deck.id || state?.deckId;
  const imagesError = state?.imagesError;
  const imagesReady = state?.imagesReady !== false;

  if (imagesError) {
    container.innerHTML = `<div class="emptyMsg">Deck images error: ${imagesError}</div>`;
    return;
  }
  if (!imagesReady) {
    container.innerHTML = `<div class="emptyMsg">Loading deck images...</div>`;
    return;
  }
  if (!deckId) {
    container.innerHTML = `<div class="emptyMsg">Deck id missing.</div>`;
    return;
  }

  const cards = [...deck.cards].sort(
    (a, b) => (Number(a.mana || 0) - Number(b.mana || 0)) || String(a.name).localeCompare(String(b.name))
  );

  const fixedCounts = fixedToCounts(state.deck_counts ?? state.fixed?.fixed ?? state.fixed);

  // Keep size stable for <15 cards; for >15, main.js grows window so this still stays readable
  const rowsForSizing = Math.max(BASE_ROWS, cards.length);
  applyRowHeight(rowsForSizing);

  for (const c of cards) {
    const drawn = Number(fixedCounts[c.cardId] || 0);
    const inDeck = Number(c.qty) || 0;
    const remaining = Math.max(0, inDeck - drawn);

    const isLegendary = normRarity(c.rarity) === "LEGENDARY";

    const row = document.createElement("div");
    row.className = "cardRow" + (remaining <= 0 ? " isEmpty" : "");

    setFullImageCandidates(row, deckId, c.cardId, state?.imagesVersion);


    // LEFT square = QTY / ★
    const qtyLeft = document.createElement("div");
    qtyLeft.className = "qtyLeft" + (isLegendary ? " legendary" : "");
    qtyLeft.textContent = isLegendary ? STAR : String(remaining);

    // image + overlay mana square
    const imgWrap = document.createElement("div");
    imgWrap.className = "imgWrap";

    const img = document.createElement("img");
    img.src = imgSrc(deckId, c.cardId, state?.imagesVersion);
    img.alt = c.name || "";

    // OVER IMAGE square = MANA
    const manaOver = document.createElement("div");
    manaOver.className = "manaOver";
    manaOver.textContent = String(Number(c.mana ?? 0) || 0);

    // NOWE: Nazwa karty
    const cardName = document.createElement("div");
    cardName.className = "cardName";
    cardName.textContent = c.name || "";

    imgWrap.appendChild(img);
    imgWrap.appendChild(manaOver);
    imgWrap.appendChild(cardName); // Dodano

    row.appendChild(qtyLeft);
    row.appendChild(imgWrap);

    container.appendChild(row);
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  setupFullCardTooltip();
  render(await window.dt.getOverlayState());
  window.dt.onOverlayState(render);

  window.addEventListener("resize", () => {
    if (lastState) render(lastState);
  });
});