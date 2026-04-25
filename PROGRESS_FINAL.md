# Program Overview

This document describes the current program in detail, covering both backend (Python) and frontend (Electron).

Scope notes:
- JSON dumps, images, and Markdown files are excluded from module/function listing as requested.
- Source roots covered: `app.py`, `deck/`, `formatting/`, `frontend/`, `game/`, `logs/`, `log_analysis/`, `scraping/`, `electron_ui/src/`.

## High-level architecture
- The Python backend watches Hearthstone log files, tracks match state, predicts opponent decks, and pushes state updates via a TCP bridge.
- The Electron frontend connects to the backend, manages decks, and renders an in-game overlay with remaining cards and deck images.

## Backend (Python)

### app.py (entrypoint)
Purpose: orchestrates startup, connects the frontend bridge, and streams log lines.
Functions:
- `run()`: resolve log dir via `resolve_log_dir()`, wait for `Zone.log` and `Power.log`, start `FrontendBridge`, then merge log streams via `iter_merged_logs()` and dispatch to `GameSession` handlers.

### deck/deck_assets.py
Purpose: manage card tile assets and per-deck image downloads.
Class `DeckAssets`:
- `__init__(cards_photos_dir, decks_dir)`: store root paths for global tiles and per-deck images.
- `ensure_card_tile(dbf_id, output_dir=None)`: return `False` if `dbf_id` is missing or the file exists; otherwise create the output dir and download via `CardIdToPicTile`.
- `clear_card_photos()`: remove cached global tiles from `cards_photos_dir`.
- `download_deck_images(deck_id)`: locate deck JSON, dedupe card ids, download tiles into `decks/<id>/cards_photos`, and return `(count, "deck_not_found" | "deck_load_failed" | None)`.
- `_load_deck_card_ids(deck_path)`: accept `cardId` or `dbfId` fields and return a list of ints.
- `_find_deck_json(deck_id)`: check `deck.json`, `<id>.json`, any `*.json` in the deck folder, then fall back to `decks/<id>.json`.

### deck/deck_guessing.py
Purpose: predict opponent deck based on observed cards.
Class `DeckGuessing`:
- `__init__(predictions_to_show=5)`: set prediction limits and initialize state.
- `reset()`: clear opponent class, predictor, and last summary.
- `update_guess(card)`: ignore friendly cards, call `DeckPredictor.observe_card()`, format results via `format_predictions()`, and suppress duplicate summaries.
- `_ensure_deck_predictor(card)`: infer opponent class from the first opposing `card_id` using `CardRealIdToId` + `CardToClass`, then create a predictor.

### formatting/format_message.py
Purpose: format tracker data for UI or debug output.
Functions:
- `cards_to_payload(cards, player=None)`: filter to payload-capable cards (`dbf_id` + `fixed_round`), optionally by owner, and sort by owner name.
- `cards_to_qty(cards, player)`: increment when a fixed card leaves the deck and decrement when it returns.
- `build_round_summary(label, fixed_cards, moved_cards)`: format fixed cards and collapsed move chains for a round.
- `build_game_summary(cards)`: build a full-game debug summary of fixed cards.
- `format_predictions(predictions)`: format deck prediction results with scores and metadata.

### frontend/frontend_bridge.py
Purpose: TCP server for frontend clients (newline-delimited JSON).
Classes:
- `_ThreadedTCPServer`: thread-per-connection TCP server with address reuse enabled.
- `_ClientHandler.handle()`: buffer partial frames, split on `\n`, ignore empty or invalid JSON lines, and pass messages to the bridge.
- `FrontendBridge`:
  - `__init__(host, port, on_message)`: store connection settings and callback.
  - `start()`: create and start the threaded TCP server.
  - `stop()`: shut down the server and release the port.
  - `send(payload, client=None)`: send JSON (`ensure_ascii=True`) to one client or all connected clients; drop clients on send failure.
  - `_snapshot_clients()`: return a thread-safe list of connected clients.
  - `_register(sock)`: add a client socket to the active set.
  - `_unregister(sock)`: remove a client socket from the active set.
  - `_handle_message(payload, client)`: dispatch an inbound message to the provided callback.

### frontend/frontend_adapter.py
Purpose: convert backend state to frontend payloads and handle frontend requests.
Class `FrontendAdapter`:
- `__init__(snapshot_cards, stage_provider, deck_assets, get_deck_counts)`: wire state providers and asset manager.
- `set_bridge(bridge)`: attach or detach the TCP bridge.
- `send_game_state(client=None, request_id=None)`: send opposing card payloads, friendly `deck_counts`, and stage to one or all clients.
- `send_round_update(round_fixed)`: emit only when there are opposing fixed cards or friendly deck counts.
- `send_instant_update(fixed_cards, deck_counts=None)`: send immediate, small updates during a round.
- `send_game_init()`: notify the UI that a match has started.
- `send_game_over()`: notify the UI that a match has ended.
- `handle_message(payload, client)`: respond to UI requests and spawn a background thread for `deck_saved`.
- `_process_deck_saved(deck_id, client)`: download deck images and emit `deck_images_ready` to the requesting client.

### game/round_tracker.py
Purpose: maintain match state derived from Zone.log and Power.log lines.
Data:
- `ZoneResult` dataclass: `card`, `should_update_guess`, `tile_dbf_id`, `fixed`, `moved`, `deck_counts_delta`.
- `PowerResult` dataclass: `round_end_reason`, `round_summary`, `game_summary`, `game_init`, `game_over`.
Class `RoundTracker`:
- `__init__()`: initialize tracker, locks, and round state.
- `snapshot_cards()`: return a list of all cards currently tracked.
- `handle_power_line(pline)`: detect turn/step boundaries and game over, emitting `PowerResult` summaries.
- `handle_zone_line(zline)`: parse a transition, update tracker state, collapse move chains per entity, and compute `deck_counts_delta`.
- `build_round_summary()`: format current round changes for debug output.
- `build_game_summary()`: format a full-game summary from current card state.
- `clear_round(reset_step=False)`: clear per-round caches and optionally reset the step marker.
- `start_game()`: exit init phase and reset deck counts.
- `reset_game_state(new_turn=None)`: reset tracker and round counters to a clean state.
- `get_deck_counts(player)`: return a snapshot of deck counts for the given player.
- `_resolve_dbf_id(card)`: map card id to dbf id via `CardRealIdToId`, then fall back to `CardNameToId`.

### game/game_session.py
Purpose: orchestrate game state, deck guessing, and frontend updates.
Class `GameSession`:
- `__init__(cards_photos_dir, decks_dir, predictions_to_show=5, instant_updates=False)`: build all core components and wire them together.
- `_get_stage()`: return the current match stage string.
- `set_bridge(bridge)`: attach or detach the frontend bridge.
- `handle_frontend_message(payload, client)`: proxy UI messages to the adapter.
- `handle_power_line(pline)`: handle turn boundaries, emit round/game summaries, send `game_init`/`game_over`, and reset state on game end.
- `handle_zone_line(zline)`: apply zone events, optionally emit instant updates, update deck guesses, and ensure tile downloads.

### logs/log_stream.py
Purpose: merge Zone.log and Power.log by timestamps.
Functions:
- `parse_timestamp(line)`: parse `D HH:MM:SS.mmm` into seconds for ordering.
- `wait_for_logs(log_dir, zone_name="Zone.log", power_name="Power.log")`: block until both files exist and return their paths.
- `iter_merged_logs(zone_log, power_log, poll_interval=0.05)`: merge streams with per-file buffers, prefer Power.log on ties, and sleep when idle.

### log_analysis/decktracker.py
Purpose: parse Zone.log transitions into card and deck state.
Enums: `ZONE`, `PLAYER`.
Functions:
- `normalize_zone(zone)`: map a zone string to the closest `ZONE` enum value.
- `process_line(line)`: parse `TRANSITIONING card` lines into an event dict with ids, zones, and owner.
Classes:
- `Card`:
  - `update(name, card_id, zone)`: update revealed card data and store `prev_zone` before changing `zone`.
  - `short()`: return a compact string `(name, id)` for debug output.
  - `set_dbf_id(dbf_id)`: store resolved dbf id if provided.
  - `set_fixed_round(round_label)`: record the round when the card was first fixed.
  - `set_hand_round(round_label)`: record the round the card entered hand.
  - `get_payload()`: build a UI payload only when `dbf_id` and `fixed_round` are set.
  - `get_debug_fixed(zone_label)`: format a "fixed" event line.
  - `get_debug_move(from_zone, to_zone)`: format a move event line.
  - `get_debug_game()`: format a full-game debug line for this card.
- `PlayerState`:
  - `create_card(entity_id)`: create and register a new `Card`.
  - `get(entity_id)`: fetch a card by entity id.
  - `by_zone(zone)`: list cards currently in a given zone.
- `Tracker`:
  - `learn_mapping(src, dst)`: decide which player id is FRIENDLY/OPPOSING based on zone labels.
  - `get_player(pid)`: return or create `PlayerState` for a player id.
  - `handle_event(event, init_phase)`: apply a transition event and return `(handled, fixed, moved, card)`.
  - `update_deck_counts(card)`: increment/decrement deck counts on deck in/out transitions, never below zero.
  - `get_deck_counts(player)`: return a copy of current deck counts for a player.
  - `reset_deck_counts()`: clear deck counts for both players.
  - `print_summary()`: print a debug dump of all tracked cards and zones.

### log_analysis/log_paths.py
Purpose: locate Hearthstone install and log directory.
Data:
- `LOGS_BASE`
Functions:
- `find_hearthstone_install()`: locate the install folder via env var, registry, common paths, then a bounded `rglob`.
- `resolve_logs_base(preferred=None)`: choose the Logs base path from preferred, default, or install path.
- `get_latest_log_folder(base_path)`: pick the newest `Hearthstone_*` subfolder.
- `resolve_log_dir(preferred_path=None)`: return the latest log directory by modification time.

### scraping/Scrap.py
Purpose: load HSReplay data and provide deck/card utilities.
Data load: JSON datasets are loaded at import time into `metaDecks`, `cards`, and matchup/deck lists.
Functions:
- `_load_json(filename)`: load a JSON file from the scraping data directory.
- `ClassDeck(class_name)`: return meta decks for a given class.
- `DeckNametoAID(deck_name)`: map a deck name to an archetype id, with "Other" fallback.
- `DeckIDtoName(deck_id)`: map an archetype id to a deck name, including "Other" ids.
- `GetCoreCards(deck_name)`: return core component card ids for a deck.
- `DeckNameClass(deck_name)`: infer class name from a deck name or meta entry.
- `FoundDeck(deck_name)`: find deck info entry for a given deck name.
- `DeckPopularity(deck_name)`: return `pct_of_total` for a deck.
- `DeckWinrate(deck_name)`: return win rate for a deck.
- `DeckTotalGames(deck_name)`: return total games for a deck.
- `GetFullDeck(archetype_id)`: return full card list for archetype_id (most played is chosen).
- `CardIdToName(id)`: map dbf id to card name.
- `CardIdToType(id)`: map dbf id to card type.
- `CardNameToId(card_name)`: map card name to dbf id.
- `CoreCardsNames(coreCards)`: map a list of dbf ids to card names.
- `CardToClass(id)`: map dbf id to card class.
- `CardNameToClass(card_name)`: map card name to card class.
- `CardRealIdToId(real_id)`: map Hearthstone card id to dbf id.
- `CardIdToRealId(id)`: map dbf id to Hearthstone card id.
- `CardIdToPic(id)`: download a full-size jpg by dbf id into the current directory.
- `_resolve_output_path(output_dir, filename)`: choose output directory and ensure it exists.
- `CardIdToPicTile(id, output_dir=None)`: download a `.webp` tile by dbf id into a target directory (creating it if needed).
- `StringDeckListToList(str_deck_list)`: parse serialized deck list JSON into dbf ids.
- `classOtherDeckID(class_name)`: map class name to "Other" archetype id.
- `OtherDecks(deck_id)`: map negative "Other" ids to display names.
- `Matchup(my_deck_name, enemy_deck_name)`: find matchup stats between two decks.
- `MatchupWinrate(my_deck_name, enemy_deck_name)`: return matchup win rate.
- `MatchupTotalGames(my_deck_name, enemy_deck_name)`: return matchup total games.
- `which_class(deck_list)`: return class of a deck.
- `my_deck()`: return name our deck (from cards in json).
Classes:
- `Prediction`: simple container for `(deck, score)` pairs.
- `DeckPredictor`:
  - `__init__(class_name)`: load decks for a class and prepare lookup tables.
  - `_preprocess()`: build card-to-deck maps (core and full lists) and win-rate metadata.
  - `print_mappings()`: print debug mappings of cards to decks.
  - `observe_card(real_id)`: update scores (+4 core match, +1 general match).
  - `predict(k=5)`: return top-k predictions ordered by score and win rate.

### scraping/cards_filter.py
Purpose: build a slim card database for the UI.
Functions:
- `is_forbidden(card)`: exclude cards by set or "hb" id suffix.
- `is_token(card)`: detect token cards by id suffix.
- `card_score(card)`: rank cards by collectible flag, set priority, and dbf id.
- `slim_card(card)`: project a full card record to a minimal schema for UI.
- `filter_cards()`: filter, group by name, keep best versions, and write `electron_ui/data/all_cards.json`.

### scraping/update_data.py
Purpose: fetch and refresh HSReplay and HearthstoneJSON datasets.
Data:
- `URLS`, `scraper`
Functions:
- `fetch_hsreplay(url)`: fetch and parse HSReplay JSON, stripping the `)]}',` XSSI prefix.
- `fetch_normal(url)`: fetch JSON from a standard endpoint.
- `data()`: iterate `URLS`, download each dataset, and save to `<name>.json` in the current directory.

### scaping/cards_filter.py
- `is_forbidden(card)`: return bool if card is from normal game mode
- `is_token(card)`: return bool if card is a token (non playable card)
- `card_score(card)`: heuristic for card (better if from newer set)
- `slim_card(card)`: return card with fewer fields
- `filter_cards()`: saves only playable cards without duplicates in json all_cards.json
- `check_duplicates()`: helper function to check if filter method works

## Frontend (Electron UI)

This segment describes the frontend architecture of the Decktracker, built with Electron. It covers the main process orchestration, window management, and specific renderer logic for overlays and menus.

Scope notes:
- CSS styles and HTML structure details are summarized by purpose rather than line-by-line listing.
- Source roots covered: `electron_ui/src/`.

## High-level architecture
- **Main Process (`main.js`):** Acts as the central controller. It manages the application lifecycle, connects to the Python backend via TCP, handles IPC (Inter-Process Communication) between windows, and executes complex logic for overlay positioning and "layering" (Standard vs. Guess mode).
- **Renderer Processes:** Separate browser windows for the Player Overlay, Opponent Overlay, Deck Guesser, Full Deck Preview, and Menu. They communicate with `main.js` via a secure `preload.js` bridge.

## Main Process

### main.js
Purpose: Entry point, window management, backend communication, and overlay positioning/attachment.
State:
- `overlayWin`, `opponentWin`, `guessWin`, `fullDeckWin`: References to the four overlay windows.
- `activeLayer`: Controls which set of overlays is visible (`"standard"` or `"guess"`).
- `fixedCards`, `deckCounts`: Local cache of match state received from the backend.
- `matchStage`: Current game state (e.g., "in_match", "not_in_match").
- `opponentImagesVersion`: Counter used to force-refresh opponent card images when the backend updates them.

Functions:
- `createWindows()`: Initialize all overlay windows with specific flags (transparent, click-through, always-on-top).
- `createMenuWindow()`: Create the deck management window.
- `updateOverlayPosition()`:
  - Locates the Hearthstone window handle and bounds.
  - Attaches overlays as "owned" windows using `node-window-manager`.
  - Calculates coordinates using **`computeBoundsUnified`** to ensure consistent sizing and margins across all overlays.
  - Applies a top margin offset (65px) to avoid obscuring the opponent's name.
  - **Standard Layer:** Opponent Tracker (Left) + Player Tracker (Right).
  - **Guess Layer:** Deck Guesser (Left) + Full Deck Preview (Right).
- `connectBackend()`: Establish TCP connection to Python backend (`127.0.0.1:49777`).
- `handleBackendMessage(msg)`: Dispatch incoming JSON messages:
  - `game_state`/`round_update`/`instant_update`: Update local cache and broadcast to renderers.
  - `deck_images_ready`: Signal overlays to refresh images.
  - `opponent_images_ready`: Increments `opponentImagesVersion` and refreshes opponent/guess overlays.
  - `opponent_guess_update`: Forward predictions to the Guess Overlay.
- `broadcastOverlayState()`: Send calculated state (deck, counts, fixed cards, image versions) to relevant renderers via IPC.
- `ipcMain` handlers:
  - `dt:previewOpponentDeck`: Relay deck data from Guesser (Left) to Full Deck Overlay (Right).
  - `dt:saveDeck`, `dt:deleteDeck`, `dt:loadDeck`: File system operations for deck management.
  - `dt:getCardAliases`: Load JSON for mapping card IDs (e.g., Core set versions).

## Preload Bridge

### preload.js
Purpose: Securely expose Node.js/Electron capabilities to the renderer processes via `contextBridge`.
API (`window.dt`):
- `getAllCards()`, `getCardAliases()`: Fetch static DBs.
- `listDecks()`, `saveDeck()`, `loadDeck()`, `deleteDeck()`: Deck CRUD operations.
- `alert()`, `confirm()`: Native system dialog wrappers.
- `previewOpponentDeck(deckData)`: Send signal to Main to update the Full Deck view.
- `onOverlayState(cb)`, `onBackendEvent(cb)`, `onFullDeckPreview(cb)`: Event listeners.

## Renderers (UI Windows)

### overlay.html & overlay_renderer.js (Player Tracker)
Purpose: Display the user's active deck and remaining cards.
Logic:
- `render(state)`:
  - Calculates remaining card quantities (`inDeck - drawn`).
  - Sorts cards by Mana cost.
  - Dynamically calculates row height based on card count.
  - **Visuals:** Displays Card Name overlaid on the image, Mana cost, and Quantity/Legendary star.
  - **Tooltips:** Implements `setupFullCardTooltip` to show full card art on hover.

### opponent_overlay.html & opponent_overlay_renderer.js (Opponent Tracker)
Purpose: Display cards played by the opponent (grave/revealed).
Logic:
- `init()`: Loads card database and aliases map on startup.
- `render(state)`:
  - Receives `state.fixed` (list of played IDs).
  - **Filtering:** Excludes cards of type HERO, HERO_POWER, and ENCHANTMENT.
  - Aggregates duplicates (e.g., 2x "Fireball").
  - Displays list with "Unknown" fallback for missing IDs.
  - **Visuals:** Matches the visual style of the Player Overlay (header shape, fonts, colors).
  - **Tooltips:** Shows full card art on hover.

### guess_overlay.html & guess_renderer.js (Deck Guesser)
Purpose: Carousel interface for predicting opponent's deck archetype.
Logic:
- `updateGuesses(newGuesses)`: Updates the list of potential decks received from the backend.
- `renderCarousel()`:
  - Displays header with Deck Name (top) and Navigation arrows (bottom).
  - Shows stats: Winrate (color-coded), Popularity, Games, Turns/Game.
  - Renders "Core Cards" (defining cards for that archetype) with names overlaid.
  - **Interaction:** Calls `window.dt.previewOpponentDeck` when the slide changes to update the right-side overlay.
  - **Tooltips:** Shows full card art for core cards on hover.

### full_deck_overlay.html & full_deck_renderer.js (Full Deck Preview)
Purpose: Detailed view of the deck currently selected in the Guesser.
Logic:
- `loadAndRender(deckData)`:
  - Triggered via `onFullDeckPreview`.
  - Checks if `deckData` contains a full card list (`cards`).
  - If not, invokes `dt:selectOpponentDeck` to fetch details from backend.
  - Displays a standardized "Waiting..." message if no deck is selected.
- `renderList(cards)`: Renders the full 30-card list sorted by Mana.
- **Tooltips:** Uses `setupFullCardTooltipAnchored` to intelligently position tooltips within the window bounds.

### menu.html & menu_renderer.js (Settings & Builder)
Purpose: Application dashboard, deck creation, and editing.
Logic:
- `refreshDecks()`: Fetches and lists all local decks.
- `renderBuilder()`: UI for adding/removing cards from a draft.
- `importDeckFromPaste()`: Parses HSReplay-style text strings into deck objects.
- `saveDeck()`: Validates input and persists the deck to JSON.
- `showSuggestions(q)`: Autocomplete logic for card search.
- Status Bar: Displays connection state and backend event logs (e.g., "Deck images ready").
