from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Optional, cast

from formatting import build_game_summary, build_round_summary
from log_analysis import Card, Tracker, process_line, PLAYER, ZONE
from scraping import CardNameToId, CardRealIdToId, CardIdShouldIgnore


GAMEOVER_PATTERN = re.compile(
    r"TAG_CHANGE\s+Entity=GameEntity.*tag=STATE value=COMPLETE",
    re.IGNORECASE,
)
TURN_PATTERN = re.compile(r"TAG_CHANGE Entity=GameEntity tag=TURN value=(\d+)", re.IGNORECASE)
NEXT_STEP_PATTERN = re.compile(r"NEXT_STEP value=(?P<step>\w+)", re.IGNORECASE)
IGNORE_TYPES = {"HERO_POWER", "ENCHANTMENT"}


@dataclass
class ZoneResult:
    card: Card
    should_update_guess: bool
    tile_dbf_id: Optional[int]
    fixed: bool
    moved: bool
    deck_counts_delta: dict[int, int]


@dataclass
class PowerResult:
    round_end_reason: Optional[str] = None  # "turn", "main_ready", "game_over"
    round_summary: Optional[str] = None
    game_summary: Optional[str] = None
    game_init: bool = False
    game_over: bool = False


class RoundTracker:
    def __init__(self) -> None:
        self.tracker = Tracker()
        self.state_lock = threading.Lock()
        self.current_round = 0
        self.init_phase = True
        self.round_fixed: dict[int, Card] = {}
        self.round_moved: dict[int, tuple[Card, str, str]] = {}
        self.last_next_step: Optional[str] = None

    # With lock applied, fetch whole game state from tracker
    def snapshot_cards(self) -> list[Card]:
        with self.state_lock:
            return [card for player in self.tracker.players.values() for card in player.cards.values()]

    # Handle power line and update round/game info
    def handle_power_line(self, pline: str) -> Optional[PowerResult]:
        turn_match = TURN_PATTERN.search(pline)
        if turn_match:
            turn_value = int(turn_match.group(1))
            result = PowerResult()

            if turn_value == 1 and self.init_phase:
                self.start_game()
                result.game_init = True

            target_round = max(0, turn_value - 1)
            if target_round > self.current_round:
                self.current_round = target_round
                result.round_summary = self.build_round_summary()
                result.round_end_reason = "turn"

            return result if result.game_init or result.round_end_reason else None

        step_match = NEXT_STEP_PATTERN.search(pline)
        if step_match:
            step_value = step_match.group("step")
            if step_value == "MAIN_READY" and not self.init_phase:
                if self.last_next_step != "MAIN_READY":
                    self.last_next_step = "MAIN_READY"
                    return PowerResult(
                        round_end_reason="main_ready",
                        round_summary=self.build_round_summary(),
                    )
                self.last_next_step = "MAIN_READY"
            else:
                self.last_next_step = step_value
            return None

        if GAMEOVER_PATTERN.search(pline):
            result = PowerResult(
                round_end_reason="game_over",
                round_summary=self.build_round_summary(),
                game_summary=self.build_game_summary(),
                game_over=True,
            )
            return result

        return None

    # Process a zone line, updating state and returning any relevant results
    def handle_zone_line(self, zline: str) -> Optional[ZoneResult]:
        event = process_line(zline)
        if not event:
            return None

        with self.state_lock:
            handled, fixed, moved, card = self.tracker.handle_event(event, self.init_phase)
            if not handled or card is None:
                return None
            card = cast(Card, card)

            if fixed:
                self.round_fixed[card.entity_id] = card
                if card.dbf_id is None:
                    card.set_dbf_id(self._resolve_dbf_id(card))
                if card.fixed_round is None:
                    card.set_fixed_round(self.current_round)

            if moved and card.prev_zone is not None and card.zone is not None:
                from_zone = card.prev_zone.name
                to_zone = card.zone.name
                existing = self.round_moved.get(card.entity_id)
                if existing:
                    self.round_moved[card.entity_id] = (card, existing[1], to_zone)
                else:
                    self.round_moved[card.entity_id] = (card, from_zone, to_zone)

            if card.zone == ZONE.HAND and card.prev_zone != ZONE.HAND:
                card.set_hand_round(self.current_round)

            should_update_guess = fixed and card.owner == PLAYER.OPPOSING
            tile_dbf_id = card.dbf_id
            ignored = False
            if card.dbf_id is not None:
                try:
                    ignored = CardIdShouldIgnore(card.dbf_id)
                except Exception:
                    ignored = False
            deck_counts_delta = {} if ignored else self.tracker.update_deck_counts(card)

        return ZoneResult(
            card=card,
            should_update_guess=should_update_guess,
            tile_dbf_id=tile_dbf_id,
            fixed=fixed,
            moved=moved,
            deck_counts_delta=deck_counts_delta,
        )

    def build_round_summary(self) -> Optional[str]:
        return build_round_summary(self.current_round, self.round_fixed, self.round_moved)

    def build_game_summary(self) -> Optional[str]:
        return build_game_summary(self.snapshot_cards())

    def clear_round(self, reset_step: bool = False) -> None:
        self.round_fixed = {}
        self.round_moved = {}
        if reset_step:
            self.last_next_step = None

    # Called after init_phase is over
    def start_game(self) -> None:
        self.clear_round(reset_step=True)
        self.init_phase = False
        with self.state_lock:
            self.tracker.reset_deck_counts()

    # Called only after game finished
    def reset_game_state(self, new_turn: Optional[int] = None) -> None:
        with self.state_lock:
            self.tracker = Tracker()
        self.init_phase = True
        self.current_round = new_turn if new_turn is not None else 0
        self.clear_round(reset_step=True)

    def get_deck_counts(self, player: PLAYER) -> dict[int, int]:
        with self.state_lock:
            return self.tracker.get_deck_counts(player)

    def _resolve_dbf_id(self, card: Card) -> Optional[int]:
        if card.card_id:
            try:
                return CardRealIdToId(card.card_id)
            except Exception:
                pass
        if card.name:
            try:
                return CardNameToId(card.name)
            except Exception:
                pass
        return None
