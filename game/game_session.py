from __future__ import annotations

from pathlib import Path
import threading
from typing import Optional, TYPE_CHECKING

from deck import DeckAssets, DeckGuessing
from frontend import FrontendAdapter
from .round_tracker import RoundTracker, IGNORE_TYPES
from log_analysis import PLAYER
# ZMIANA: Usunąłem import listDecks i GetFullDeck, zostawiłem tylko GetFullDeck2
from scraping.Scrap import GetCoreCards, CardIdToType, GetFullDeck2, CardIdShouldIgnore

if TYPE_CHECKING:
    from frontend import FrontendBridge


class GameSession:
    def __init__(
        self,
        cards_photos_dir: Path,
        decks_dir: Path,
        cards_source_dir: Optional[Path] = None,
        predictions_to_show: int = 5,
        instant_updates: bool = False,
    ) -> None:
        self.deck_assets = DeckAssets(
            cards_photos_dir, decks_dir, cards_source_dir=cards_source_dir
        )
        self.round_tracker = RoundTracker()
        self.deck_guessing = DeckGuessing(predictions_to_show)
        self._game_stage = "not_in_match"
        self.frontend = FrontendAdapter(
            self.round_tracker.snapshot_cards,
            self._get_stage,
            self.deck_assets,
            self.round_tracker.get_deck_counts,
            ignored=IGNORE_TYPES,
        )
        self._instant_updates = instant_updates
        self._catching_up = False
        self._has_caught_up = False
        self._pending_tile_ids: set[int] = set()
        self._pending_guesses: Optional[list[dict]] = None
        self._awaiting_new_game = False

    def _get_stage(self) -> str:
        return self._game_stage

    def set_catching_up(self, catching_up: bool) -> None:
        if catching_up and self._has_caught_up:
            return
        self._catching_up = catching_up
        self.frontend.set_suspended(catching_up)
        if catching_up:
            self._pending_tile_ids.clear()
            self._pending_guesses = None

    def catch_up_complete(self) -> None:
        if not self._catching_up or self._has_caught_up:
            return
        self._catching_up = False
        self._has_caught_up = True
        self.frontend.set_suspended(False)
        tile_ids = self._flush_pending_tiles()
        if tile_ids:
            self.frontend.send_opponent_images_ready(tile_ids)
        self.frontend.send_game_state()
        if self._pending_guesses:
            self.frontend.send_opponent_guesses(self._pending_guesses)
            self._pending_guesses = None

    def _flush_pending_tiles(self) -> list[int]:
        cards = self.round_tracker.snapshot_cards()
        tile_ids = {
            card.dbf_id
            for card in cards
            if card.owner == PLAYER.OPPOSING
            and card.fixed
            and card.dbf_id is not None
            and not self._is_ignored_type(card.dbf_id)
        }
        tile_ids.update(self._pending_tile_ids)
        sorted_ids = sorted(tile_ids)
        for dbf_id in sorted_ids:
            self.deck_assets.ensure_image(dbf_id)
            self.deck_assets.ensure_image(dbf_id, image_kind="render")
        self._pending_tile_ids.clear()
        return sorted_ids

    def _is_ignored_type(self, dbf_id: Optional[int]) -> bool:
        if dbf_id is None:
            return False
        try:
            return CardIdShouldIgnore(dbf_id)
        except Exception:
            return False

    def _is_new_game_marker(self, pline: str) -> bool:
        upper = pline.upper()
        if "CREATE_GAME" in upper:
            return True
        if "BEGIN_MULLIGAN" in upper:
            return True
        if "TAG_CHANGE" in upper and "STATE VALUE=RUNNING" in upper:
            if "ENTITY=GAMEENTITY" in upper or "ENTITY=1" in upper:
                return True
        return False

    def set_bridge(self, bridge: Optional[FrontendBridge]) -> None:
        self.frontend.set_bridge(bridge)

    def handle_frontend_message(self, payload: dict, client: object) -> None:
        msg_type = payload.get("type")
        
        # Handler dla detali oponenta
        if msg_type == "get_opponent_details":
            self._handle_opponent_details(payload, client)
            return
            
        self.frontend.handle_message(payload, client)
    
    def _handle_opponent_details(self, payload: dict, client: object) -> None:
        #print(payload)
        deck_name = payload.get("deckName")
        # archetype_id nie jest już używane do szukania decku, tylko deckId
        deck_id = payload.get("deckId") 
        req_id = payload.get("requestId")
        #print(deck_id)
        try:
            # 1. Pobierz ID Core Cards
            core_ids = GetCoreCards(deck_name)
            
            # 2. Pobierz pełny deck TYLKO na podstawie deckId
            full_deck_cards = []

            if deck_id is not None:
                try:
                    # Próbujemy pobrać konkretny wariant decku
                    # Rzutujemy na int, bo w plikach JSON deck_id jest zazwyczaj liczbą
                    full_deck_cards = GetFullDeck2(deck_id)
                except (ValueError, TypeError):
                    # Jeśli deck_id przyszło w dziwnym formacie, próbujemy bez rzutowania
                    full_deck_cards = GetFullDeck2(deck_id)

            # ZMIANA: Całkowicie usunięto blok 'elif archetype_id is not None'.
            # Jeśli deck_id jest pusty, zwracamy pustą listę kart (zamiast szukać "domyślnego" decku).

            # 3. Zbuduj listę detali dla Core Cards (dla Guessera - lewa strona)
            from scraping.Scrap import cards as SCRAP_CARDS
            details = []
            for dbf_id in core_ids:
                c_data = next((c for c in SCRAP_CARDS if c['dbfId'] == dbf_id), None)
                if c_data:
                    details.append({
                        "dbfId": dbf_id,
                        "name": c_data.get('name', ''),
                        "mana": c_data.get('cost', 0)
                    })

            # 4. Wyślij odpowiedź
            response = {
                "type": "response",
                "requestId": req_id,
                "core_cards": details,
                "cards": full_deck_cards 
            }
            
            self.frontend.send_custom(response, client)

            # 5. Pobierz obrazy w tle
            def _download_images() -> None:
                downloaded = 0
                error: Optional[str] = None
                try:
                    all_ids = set(core_ids)
                    for c in full_deck_cards:
                        if isinstance(c, dict) and 'dbfId' in c:
                            all_ids.add(c['dbfId'])
                    all_ids.discard(None)
                    downloaded, error = self.deck_assets.download_core_cards(list(all_ids))
                except Exception as exc:
                    error = str(exc)

                payload = {"type": "deck_images_ready", "deckId": "opponent_core"}
                if downloaded:
                    payload["count"] = downloaded
                if error:
                    payload["error"] = error
                self.frontend.send_custom(payload, client)

            threading.Thread(target=_download_images, daemon=True).start()

        except Exception as e:
            print(f"Error getting opponent details: {e}")
            self.frontend.send_custom({
                "requestId": req_id,
                "error": str(e)
            }, client)

    # ==== Log handling ====
    def handle_power_line(self, pline: str) -> Optional[str]:
        if self._awaiting_new_game:
            if not self._is_new_game_marker(pline):
                return None
            self._awaiting_new_game = False

        result = self.round_tracker.handle_power_line(pline)
        if not result:
            return None

        # game init -> send game init and state
        if result.game_init:
            self._game_stage = "in_match"
            self.frontend.send_game_init()
            self.frontend.send_game_state()
            self._pending_tile_ids.clear()
            self._pending_guesses = None
            self._awaiting_new_game = False

        output = result.round_summary or ""

        # regular round change / step change
        if result.round_end_reason:
            if not self._instant_updates:
                self.frontend.send_round_update(
                    self.round_tracker.round_fixed,
                )
            if result.round_end_reason == "turn":
                self.round_tracker.clear_round(reset_step=True)
            elif result.round_end_reason == "main_ready":
                self.round_tracker.clear_round()

        # game over -> send game over, clear assets and reset game state
        if result.game_over:
            if result.game_summary:
                output += result.game_summary
            self._game_stage = "ended"
            self.frontend.send_game_over()
            self.deck_assets.clear_card_photos()
            self.deck_assets.clear_opponent_core_photos()
            self.round_tracker.reset_game_state()
            self.deck_guessing.reset()
            self.frontend.send_game_state()
            self._pending_tile_ids.clear()
            self._pending_guesses = None
            self._awaiting_new_game = True

        return output or None


    def handle_zone_line(self, zline: str) -> Optional[str]:
        if self._awaiting_new_game:
            return None
        result = self.round_tracker.handle_zone_line(zline)
        summary: Optional[str] = None
        if not result:
            return None

        tile_ready = False
        is_opponent_card = result.card.owner == PLAYER.OPPOSING
        is_ignored_type = self._is_ignored_type(result.tile_dbf_id)
        if result.tile_dbf_id is not None and is_opponent_card and not is_ignored_type:
            if self._catching_up:
                self._pending_tile_ids.add(result.tile_dbf_id)
            else:
                if not self.deck_assets.image_exists(result.tile_dbf_id):
                    self.deck_assets.ensure_image(result.tile_dbf_id)
                if not self.deck_assets.image_exists(result.tile_dbf_id, image_kind="render"):
                    self.deck_assets.ensure_image(result.tile_dbf_id, image_kind="render")
                tile_ready = self.deck_assets.image_exists(result.tile_dbf_id)
                if tile_ready and result.fixed:
                    self.frontend.send_opponent_images_ready([result.tile_dbf_id])

        # instant update handling
        if self._instant_updates:
            fixed_cards = []
            if result.fixed and is_opponent_card and not is_ignored_type and tile_ready:
                fixed_cards = [result.card]
            deck_counts = (
                result.deck_counts_delta if result.card.owner == PLAYER.FRIENDLY else {}
            )
            if fixed_cards or deck_counts:
                self.frontend.send_instant_update(fixed_cards, deck_counts)

        # Guesser logic
        is_opposing_revealed = (
            result.card.owner == PLAYER.OPPOSING
            and result.card.card_id is not None
            and not is_ignored_type
        )

        if is_opposing_revealed:
            guesses = self.deck_guessing.update_guess(result.card)
            
            if guesses:
                if self._catching_up:
                    self._pending_guesses = guesses
                else:
                    self.frontend.send_opponent_guesses(guesses)
                summary = f"Guesses updated: {guesses[0]['name']} (Score: {guesses[0]['score']})"

        return summary