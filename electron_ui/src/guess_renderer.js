
const BASE_ROWS = 15;
const ROW_GAP_PX = 2;
const GUESS_HEIGHT_RATIO = 0.70;
const PANEL_HEIGHT_RATIO = 0.50;
const PANEL_PAD_PX = 4;
const HEADER_H_PX = 16;
const TITLE_GAP_PX = 2;
const STAR = "\u2605";

let currentGuesses = [];
let currentIndex = 0; 
let imagesVersion = 0;

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

function applyStandardRowH() {
  const approxHsHeight = window.innerHeight / GUESS_HEIGHT_RATIO;
  const baseHeight = approxHsHeight * PANEL_HEIGHT_RATIO;
  const baseListHeight = baseHeight - (PANEL_PAD_PX * 2) - HEADER_H_PX - TITLE_GAP_PX;
  const rowH = Math.max(10, Math.floor((baseListHeight - ROW_GAP_PX * (BASE_ROWS - 1)) / BASE_ROWS));
  document.documentElement.style.setProperty("--rowH", `${rowH}px`);
  document.documentElement.style.setProperty("--gap", `${ROW_GAP_PX}px`);
  return rowH;
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

// === MAIN LOGIC ===

function updateGuesses(newGuesses) {
  if (!newGuesses || newGuesses.length === 0) {
    currentGuesses = [];
    renderEmpty();
    return;
  }

  // Zachowaj aktualnie wybrany deckId jeśli to możliwe
  const currentDeckId = currentGuesses[currentIndex]?.deck_id || currentGuesses[currentIndex]?.archetype_id;
  
  currentGuesses = newGuesses;
  
  // Spróbuj znaleźć ten sam deck w nowej liście
  let newIndex = -1;
  if (currentDeckId) {
      newIndex = currentGuesses.findIndex(g => (g.deck_id || g.archetype_id) === currentDeckId);
  }
  
  currentIndex = newIndex >= 0 ? newIndex : 0;
  renderCarousel();
}

function renderEmpty() {
  document.getElementById("contentArea").classList.add("hidden");
  document.getElementById("loadingArea").classList.remove("hidden");
  
  document.getElementById("deckName").textContent = "WAITING...";
  document.getElementById("pageCounter").textContent = "- / -";
  
  // Czyścimy prawy overlay
  window.dt.previewOpponentDeck(null);
  
  updateNavButtons();
}

async function renderCarousel() {
  if (currentGuesses.length === 0) {
    renderEmpty();
    return;
  }

  document.getElementById("loadingArea").classList.add("hidden");
  document.getElementById("contentArea").classList.remove("hidden");

  const deckData = currentGuesses[currentIndex];

  // 1. ZMIANA: Wysyłamy sygnał do prawego okna (Full Deck) OD RAZU
  // Przekazujemy deckId, żeby full_deck_renderer mógł pobrać karty przez GetFullDeck2
  window.dt.previewOpponentDeck({
    name: deckData.name,
    archetypeId: deckData.archetype_id,
    deckId: deckData.deck_id // <--- TO JEST KLUCZOWE
  });

  // 2. Header Info
  document.getElementById("deckName").textContent = deckData.name || "Unknown Deck";
  document.getElementById("pageCounter").textContent = `${currentIndex + 1}/${currentGuesses.length}`;

  // 3. Stats 
  const wrVal = deckData.win_rate || 0;
  const wrEl = document.getElementById("statWR");
  
  wrEl.textContent = wrVal.toFixed(1) + "%";
  
  if (wrVal > 50.0) {
    wrEl.style.color = "#44ff44"; 
  } else if (wrVal < 50.0) {
    wrEl.style.color = "#ff4444"; 
  } else {
    wrEl.style.color = "#ffffff"; 
  }

  document.getElementById("statPop").textContent = (deckData.popularity || 0).toFixed(1) + "%";
  document.getElementById("statDur").textContent = (deckData.total_games || 0);
  
  const turns = parseFloat(deckData.turns_per_game);
  document.getElementById("statTurns").textContent = (turns && turns > 0) ? turns.toFixed(1) : "-";

  // 4. Update Buttons
  updateNavButtons();

  // 5. Fetch Cards (Core Cards for left panel)
  const listContainer = document.getElementById("coreCardsList");
  listContainer.innerHTML = `<div style="padding:10px; color:#666; font-size:10px; text-align:center;">Loading...</div>`;

  try {
    // Przekazujemy deck_id również tutaj, aby game_session wiedział, z czym pracujemy
    const res = await window.dt.selectOpponentDeck(
      deckData.archetype_id, 
      deckData.name, 
      deckData.deck_id
    );

    if (res && res.core_cards) {
      renderCards(res.core_cards);
    } else {
      listContainer.innerHTML = `<div style="padding:10px; color:#a44; font-size:10px;">No cards data</div>`;
    }
    // Nie wywołujemy tu ponownie previewOpponentDeck, bo zrobiliśmy to na początku
  } catch (err) {
    console.error(err);
    listContainer.innerHTML = `<div style="padding:10px; color:#a44; font-size:10px;">Error</div>`;
  }
}

function updateNavButtons() {
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");

  if (currentGuesses.length === 0) {
    btnPrev.classList.add("disabled");
    btnNext.classList.add("disabled");
    return;
  }
  btnPrev.classList.remove("disabled");
  btnNext.classList.remove("disabled");
}

function normRarity(r) {
  return String(r || "").toUpperCase();
}

function renderCards(cards) {
  const container = document.getElementById("coreCardsList");
  container.innerHTML = "";
  
  cards.sort((a, b) => a.mana - b.mana);

  cards.forEach(c => {
    const cardId = c.dbfId;
    const isLegendary = normRarity(c.rarity) === "LEGENDARY";
    const qty = Number(c.qty || 1);
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

// === EVENTS ===
document.getElementById("btnPrev").onclick = () => {
  if (currentGuesses.length === 0) return;
  currentIndex--;
  if (currentIndex < 0) currentIndex = currentGuesses.length - 1; 
  renderCarousel();
};

document.getElementById("btnNext").onclick = () => {
  if (currentGuesses.length === 0) return;
  currentIndex++;
  if (currentIndex >= currentGuesses.length) currentIndex = 0; 
  renderCarousel();
};

window.addEventListener("DOMContentLoaded", () => {
  applyStandardRowH();
  setupFullCardTooltipAnchored(document.getElementById("coreCardsList"));
});

window.addEventListener("resize", () => {
  applyStandardRowH();
});

window.dt.onBackendEvent((evt) => {
  if (evt.type === "opponent_guess_update") {
    updateGuesses(evt.guesses || []);
  }
  
  if (evt.type === "deck_images_ready" && evt.deckId === "opponent_core") {
    imagesVersion++;
    document.querySelectorAll("#coreCardsList img").forEach((img) => {
      const src = img.src.split("?")[0];
      img.src = `${src}?v=${imagesVersion}`;
    });
  }
  
  if (evt.type === "game_init") {
      updateGuesses([]); 
  }
});