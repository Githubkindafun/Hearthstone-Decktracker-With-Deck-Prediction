
const BASE_ROWS = 15;
const ROW_GAP_PX = 2;
const GUESS_HEIGHT_RATIO = 0.70;
const PANEL_HEIGHT_RATIO = 0.50;
const PANEL_PAD_PX = 4;
const HEADER_H_PX = 16;
const TITLE_GAP_PX = 2;
const STAR = "\u2605";
let imagesVersion = 0;

function normRarity(r) {
  return String(r || "").toUpperCase();
}

function applyStandardRowH() {
  const approxHsHeight = window.innerHeight / GUESS_HEIGHT_RATIO;
  const baseHeight = approxHsHeight * PANEL_HEIGHT_RATIO;
  const baseListHeight = baseHeight - (PANEL_PAD_PX * 2) - HEADER_H_PX - TITLE_GAP_PX;

  const rowH = Math.max(10, Math.floor((baseListHeight - ROW_GAP_PX * (BASE_ROWS - 1)) / BASE_ROWS));
  document.documentElement.style.setProperty("--rowH", `${rowH}px`);
  document.documentElement.style.setProperty("--gap", `${ROW_GAP_PX}px`);
  return rowH;
}

function getTileSrc(cardId) {
  const id = encodeURIComponent(String(cardId ?? ""));
  return `../data/decks/opponent_core/cards_photos/${id}.webp?v=${imagesVersion}`;
}

function setFullImageCandidates(row, cardId) {
  const id = encodeURIComponent(String(cardId ?? ""));
  const v = `?v=${imagesVersion}`;

  row.dataset.full1 = `../data/decks/opponent_core/card_photos/card${id}.webp${v}`;
  row.dataset.full2 = `../data/decks/opponent_core/card_photos/card${id}.png${v}`;
  row.dataset.full3 = `../data/decks/opponent_core/cards_photos/card${id}.webp${v}`;
  row.dataset.full4 = `../data/decks/opponent_core/cards_photos/card${id}.png${v}`;
  row.dataset.full5 = `../data/decks/opponent_core/cards_photos/${id}.webp${v}`;
  row.dataset.full6 = `../data/decks/opponent_core/cards_photos/${id}.png${v}`;
}

function setupFullCardTooltipAnchored(scrollContainerEl) {
  const tip = document.getElementById("cardTooltip");
  const tipImg = document.getElementById("cardTooltipImg");
  if (!tip || !tipImg) return;

  let currentRow = null;
  let loadingRow = null;

  const MARGIN = 6;
  const OFFSET_X = 10;
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

  function candidatesFromRow(row) {
    return [
      row.dataset.full1,
      row.dataset.full2,
      row.dataset.full3,
      row.dataset.full4,
      row.dataset.full5,
      row.dataset.full6,
    ].filter(Boolean);
  }

  function hide() {
    tip.classList.add("hidden");
    tipImg.removeAttribute("src");
    currentRow = null;
    loadingRow = null;
  }

  function positionForRow(row) {
    if (!row) return;
    const tipRect = tip.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();

    let x = rowRect.right + OFFSET_X;
    let y = rowRect.top + (rowRect.height / 2) - (tipRect.height / 2);

    if (x + tipRect.width > window.innerWidth - MARGIN) {
      x = rowRect.left - tipRect.width - OFFSET_X;
    }

    x = clamp(x, MARGIN, window.innerWidth - tipRect.width - MARGIN);
    y = clamp(y, MARGIN, window.innerHeight - tipRect.height - MARGIN);

    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  }

  function showForRow(row) {
    const candidates = candidatesFromRow(row);
    if (!candidates.length) return;

    currentRow = row;
    loadingRow = row;

    let idx = 0;
    tip.classList.add("hidden");

    tipImg.onload = () => {
      if (loadingRow !== row) return;
      tip.classList.remove("hidden");
      positionForRow(row);
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

  document.addEventListener("mouseover", (e) => {
    const row = e.target?.closest?.(".cardRow");
    if (!row || row === currentRow) return;
    showForRow(row);
  });

  document.addEventListener("mouseout", (e) => {
    if (!currentRow) return;
    const stillInside =
      e.relatedTarget &&
      e.relatedTarget.closest &&
      e.relatedTarget.closest(".cardRow") === currentRow;
    if (!stillInside) hide();
  });

  if (scrollContainerEl) {
    scrollContainerEl.addEventListener("scroll", () => {
      if (currentRow && !tip.classList.contains("hidden")) positionForRow(currentRow);
    });
  }

  window.addEventListener("resize", () => {
    if (currentRow && !tip.classList.contains("hidden")) positionForRow(currentRow);
  });

  window.addEventListener("blur", hide);
}

function renderList(cards) {
  const container = document.getElementById("deckList");
  container.innerHTML = "";

  cards.sort((a, b) => (a.mana - b.mana) || a.name.localeCompare(b.name));

  cards.forEach(c => {
    const cardId = c.dbfId;
    const isLegendary = normRarity(c.rarity) === "LEGENDARY";
    const qty = c.qty || 1;

    const row = document.createElement("div");
    row.className = "cardRow";

    setFullImageCandidates(row, cardId);

    const qtyLeft = document.createElement("div");
    qtyLeft.className = "qtyLeft" + (isLegendary ? " legendary" : "");
    qtyLeft.textContent = isLegendary ? STAR : String(qty);

    const imgWrap = document.createElement("div");
    imgWrap.className = "imgWrap";

    const img = document.createElement("img");
    img.src = getTileSrc(cardId);
    img.alt = c.name || "";

    const manaOver = document.createElement("div");
    manaOver.className = "manaOver";
    manaOver.textContent = String(Number(c.mana ?? 0) || 0);

    const name = document.createElement("div");
    name.className = "cardName";
    name.textContent = c.name || "";

    imgWrap.appendChild(img);
    imgWrap.appendChild(manaOver);
    imgWrap.appendChild(name);

    row.appendChild(qtyLeft);
    row.appendChild(imgWrap);

    container.appendChild(row);
  });
}

async function loadAndRender(deckData) {
  applyStandardRowH();
  const container = document.getElementById("deckList");
  const title = document.getElementById("headerTitle");
  
  if (!deckData) {
    title.textContent = "FULL DECK";
    // ZMIANA: Tekst zgodny z guess_overlay
    container.innerHTML = `<div class="msg">Waiting for opponent cards...</div>`;
    return;
  }

  title.textContent = deckData.name || "FULL DECK";
  container.innerHTML = `<div class="msg">Loading cards...</div>`;

  if (Object.prototype.hasOwnProperty.call(deckData, "cards")) {
    if (Array.isArray(deckData.cards) && deckData.cards.length > 0) {
      renderList(deckData.cards);
    } else {
      container.innerHTML = `<div class="msg">No cards found.</div>`;
    }
    return;
  }

  try {
    // ZMIANA: Przekazujemy trzeci parametr: deckData.deck_id
    // (deck_id to nazwa pola, którą dodaliśmy w Pythonie w kroku 1)
    const res = await window.dt.selectOpponentDeck(
        deckData.archetypeId || deckData.archetype_id, 
        deckData.name,
        deckData.deckId || deckData.deck_id // <--- OTO BRAKUJĄCY ELEMENT
    );
    
    // Szukamy pełnej listy (cards) lub fallback do core_cards
    let cardsToShow = res.cards || res.core_cards || [];

    if (!cardsToShow || cardsToShow.length === 0) {
      container.innerHTML = `<div class="msg">No cards found.</div>`;
      return;
    }

    renderList(cardsToShow);

  } catch (err) {
    console.error(err);
    container.innerHTML = `<div class="msg" style="color:#f55">Error loading deck</div>`;
  }
}

// Nasłuch z Main (przekazany z Guessera)
window.dt.onFullDeckPreview((deckData) => {
  loadAndRender(deckData);
});

window.addEventListener("DOMContentLoaded", () => {
  applyStandardRowH();
  setupFullCardTooltipAnchored(document.getElementById("deckList"));
});

window.addEventListener("resize", () => {
  applyStandardRowH();
});

// Nasłuch na odświeżenie obrazków
window.dt.onBackendEvent((evt) => {
  if (evt.type === "deck_images_ready" && evt.deckId === "opponent_core") {
    imagesVersion++;
    document.querySelectorAll("#deckList img").forEach(img => {
      let src = img.src.split("?")[0];
      img.src = `${src}?v=${imagesVersion}`;
    });
  }
});