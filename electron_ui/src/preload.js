const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dt", {
  // Card DB (for hints/autocomplete)
  getAllCards: () => ipcRenderer.invoke("dt:getAllCards"),
  getCardAliases: () => ipcRenderer.invoke("dt:getCardAliases"), // Zachowane z Twojego pliku

  // Decks
  listDecks: () => ipcRenderer.invoke("dt:listDecks"),
  saveDeck: (deck) => ipcRenderer.invoke("dt:saveDeck", deck),
  loadDeck: (deckId) => ipcRenderer.invoke("dt:loadDeck", deckId),
  deleteDeck: (deckId) => ipcRenderer.invoke("dt:deleteDeck", deckId),

  // Optional focus helper
  refocusMenu: () => ipcRenderer.invoke("dt:refocusMenu"),

  // ✅ Native dialogs (avoid renderer alert/confirm focus bug)
  // Zachowana Twoja oryginalna implementacja
  alert: async (message, detail = "", title = "Decktracker") => {
    await ipcRenderer.invoke("dt:messageBox", {
      type: "info",
      title,
      message: String(message ?? ""),
      detail: String(detail ?? ""),
      buttons: ["OK"],
      defaultId: 0,
      cancelId: 0
    });
    return true;
  },

  confirm: async (message, detail = "", title = "Confirm") => {
    const { response } = await ipcRenderer.invoke("dt:messageBox", {
      type: "question",
      title,
      message: String(message ?? ""),
      detail: String(detail ?? ""),
      buttons: ["Yes", "No"],
      defaultId: 0,
      cancelId: 1
    });
    return response === 0;
  },
  
  // Bezpośredni dostęp (dla elastyczności)
  messageBox: (opts) => ipcRenderer.invoke("dt:messageBox", opts),

  // Selection for overlay
  setSelectedDeck: (deckId) => ipcRenderer.invoke("dt:setSelectedDeck", deckId),
  getSelectedDeck: () => ipcRenderer.invoke("dt:getSelectedDeck"),

  // Guesser logic
  selectOpponentDeck: (archetypeId, deckName, deckId) => // <--- Dodano deckId
      ipcRenderer.invoke("dt:selectOpponentDeck", { archetypeId, deckName, deckId }),

  // --- NOWE METODY (Dla Full Deck Overlay) ---
  
  // 1. Guesser wysyła dane do Main (żeby przekazać je do prawego okna)
  previewOpponentDeck: (deckData) => ipcRenderer.send("dt:previewOpponentDeck", deckData),

  // Overlay state (deck + deck_counts)
  getOverlayState: () => ipcRenderer.invoke("dt:getOverlayState"),
  
  onOverlayState: (cb) => {
    ipcRenderer.removeAllListeners("dt:overlayState");
    ipcRenderer.on("dt:overlayState", (_e, state) => cb(state));
  },
  
  requestGameState: () => ipcRenderer.invoke("dt:requestGameState"),
  
  onBackendEvent: (cb) => {
    ipcRenderer.removeAllListeners("dt:backendEvent");
    ipcRenderer.on("dt:backendEvent", (_e, payload) => cb(payload));
  },

  // --- NOWY LISTENER (Dla Full Deck Overlay) ---
  
  // 2. Prawe okno odbiera dane do wyświetlenia
  onFullDeckPreview: (cb) => {
    ipcRenderer.removeAllListeners("dt:setFullDeckPreview");
    ipcRenderer.on("dt:setFullDeckPreview", (_e, deckData) => cb(deckData));
  }
});