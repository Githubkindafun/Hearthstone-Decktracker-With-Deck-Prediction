from __future__ import annotations

import threading
from typing import Callable, Optional, TYPE_CHECKING

from formatting import cards_to_payload
from log_analysis import Card, PLAYER

from deck import DeckAssets

if TYPE_CHECKING:
    from .frontend_bridge import FrontendBridge


class FrontendAdapter:
    def __init__(
        self,
        snapshot_cards: Callable[[], list[Card]],
        stage_provider: Callable[[], str],
        deck_assets: DeckAssets,
        get_deck_counts: Callable[[PLAYER], dict[int, int]],
        ignored: set[str] = set(),
    ) -> None:
        self._snapshot_cards = snapshot_cards
        self._stage_provider = stage_provider
        self._deck_assets = deck_assets
        self._get_deck_counts = get_deck_counts
        self._bridge: Optional[FrontendBridge] = None
        self._suspended = False
        self.ignored = ignored

    def set_bridge(self, bridge: Optional[FrontendBridge]) -> None:
        self._bridge = bridge

    def set_suspended(self, suspended: bool) -> None:
        self._suspended = suspended

    def send_game_state(
        self,
        client: Optional[object] = None,
        request_id: Optional[str] = None,
    ) -> None:
        if not self._bridge:
            return
        if self._suspended and request_id is None:
            return
        cards = self._snapshot_cards()
        stage = self._stage_provider()
        if self._suspended:
            stage = "catching_up"
        payload = {
            "type": "game_state",
            "cards": cards_to_payload(cards, PLAYER.OPPOSING, ignore=self.ignored),
            "deck_counts": self._get_deck_counts(PLAYER.FRIENDLY),
            "stage": stage,
        }
        if request_id is not None:
            payload["requestId"] = request_id
        print(f"[bridge] send game_state cards={len(payload['cards'])} deck_counts={len(payload['deck_counts'])}")
        if client is not None:
            self._bridge.send(payload, client)
        else:
            self._bridge.send(payload)


    def send_round_update(
        self,
        round_fixed: dict[int, Card],
    ) -> None:
        if not self._bridge:
            return
        if self._suspended:
            return
        opponent_fixed = cards_to_payload(list(round_fixed.values()), PLAYER.OPPOSING, ignore=self.ignored)
        friendly = self._get_deck_counts(PLAYER.FRIENDLY)
        if not opponent_fixed and not friendly:
            return
        print(f"[bridge] send round_update fixed={len(opponent_fixed)} deck_counts={len(friendly)}")
        self._bridge.send(
            {
                "type": "round_update",
                "fixed": opponent_fixed,
                "deck_counts": friendly,
            }
        )

    def send_instant_update(
        self,
        fixed_cards: list[Card],
        deck_counts: Optional[dict[int, int]] = None,
    ) -> None:
        if not self._bridge:
            return
        if self._suspended:
            return
        fixed_payload = cards_to_payload(fixed_cards, PLAYER.OPPOSING, ignore=self.ignored)
        deck_counts = deck_counts or {}
        if not fixed_payload and not deck_counts:
            return
        payload = {"type": "instant_update"}
        if fixed_payload:
            payload["fixed"] = fixed_payload
        if deck_counts:
            payload["deck_counts"] = deck_counts
        print(
            "[bridge] send instant_update "
            f"fixed={len(fixed_payload)} deck_counts={len(deck_counts)}"
        )
        self._bridge.send(payload)

    def send_game_init(self) -> None:
        if self._bridge:
            if self._suspended:
                return
            print("[bridge] send game_init")
            self._bridge.send({"type": "game_init"})

    def send_game_over(self) -> None:
        if self._bridge:
            if self._suspended:
                return
            print("[bridge] send game_over")
            self._bridge.send({"type": "game_over"})

    def handle_message(self, payload: dict, client: object) -> None:
        msg_type = payload.get("type")
        
        if msg_type in {"request_game_state", "get_game_state"}:
            request_id = payload.get("requestId")
            self.send_game_state(client, request_id)
            return

        if msg_type == "deck_selected":
            request_id = payload.get("requestId")
            self.send_game_state(client, request_id)
            deck_id = payload.get("deckId")
            if deck_id:
                threading.Thread(
                    target=self._process_deck_saved,
                    args=(deck_id, client),
                    daemon=True,
                ).start()
            return

        if msg_type == "deck_saved":
            deck_id = payload.get("deckId")
            if not deck_id:
                return
            threading.Thread(
                target=self._process_deck_saved,
                args=(deck_id, client),
                daemon=True,
            ).start()

    def _process_deck_saved(self, deck_id: str, client: object) -> None:
        downloaded, error = self._deck_assets.download_deck_images(deck_id)
        if not self._bridge:
            return
        payload = {"type": "deck_images_ready", "deckId": deck_id, "count": downloaded}
        if error:
            payload["error"] = error
        self._bridge.send(payload, client)

    def send_opponent_guesses(self, guesses: list[dict]) -> None:
        if not self._bridge:
            return
        if self._suspended:
            return
        payload = {
            "type": "opponent_guess_update",
            "guesses": guesses
        }
        print(f"[bridge] send opponent_guesses count={len(guesses)}")
        self._bridge.send(payload)
    
    def send_custom(self, payload: dict, client: Optional[object] = None) -> None:
        if not self._bridge:
            return
        if self._suspended and client is None:
            return
        self._bridge.send(payload, client)

    def send_opponent_images_ready(self, dbf_ids: list[int]) -> None:
        if not self._bridge:
            return
        if self._suspended:
            return
        if not dbf_ids:
            return
        self._bridge.send({"type": "opponent_images_ready", "dbfIds": dbf_ids})
