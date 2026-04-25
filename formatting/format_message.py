from __future__ import annotations

from typing import Optional

from log_analysis import Card, PLAYER, ZONE

from scraping import CardIdToType, CardIdShouldIgnore, DeckIDtoName, Prediction



def _is_displayable_card(card: Card, ignore: set[str]) -> bool:
    if card.dbf_id is None:
        return False
    if CardIdShouldIgnore(card.dbf_id):
        return False
    if ignore:
        card_type = CardIdToType(card.dbf_id)
        if card_type in ignore:
            return False
    return True


def cards_to_payload(cards: list[Card], player: Optional[PLAYER] = None, ignore: set[str] = {}) -> list[dict]:
    entries: list[tuple[str, dict]] = []
    for card in cards:
        if player is not None and card.owner != player:
            continue
        if not _is_displayable_card(card, ignore):
            continue
        payload = card.get_payload()
        if payload:
            entries.append((card.owner.name, payload))
    entries.sort(key=lambda item: (item[0]))
    return [payload for _,  payload in entries]

# If a card is not in deck it is incremented by 1. If a card returned it must be decremented.
def cards_to_qty(cards: list[Card], player: PLAYER) -> dict[int, int]:
    counts: dict[int, int] = {}
    for card in cards:
        if card.owner != player:
            continue
        if not card.fixed:
            continue
        if card.dbf_id is None:
            continue

        # Card returned to deck
        if card.zone == ZONE.DECK and card.prev_zone != ZONE.DECK:
            counts[card.dbf_id] = counts.get(card.dbf_id, 0) - 1
        counts[card.dbf_id] = counts.get(card.dbf_id, 0) + 1
    return counts


def build_round_summary(
    label: int,
    fixed_cards: dict[int, Card],
    moved_cards: dict[int, tuple[Card, str, str]],
) -> Optional[str]:
    if not fixed_cards and not moved_cards:
        return None
    lines = [f"[Round {label}]:"]
    for card in fixed_cards.values():
        lines.append(card.get_debug_fixed(card.zone.name))
    for card, from_zone, to_zone in moved_cards.values():
        lines.append(card.get_debug_move(from_zone, to_zone))
    return "\n".join(lines) + "\n\n"


def build_game_summary(cards: list[Card]) -> Optional[str]:
    fixed_cards = [card for card in cards if card.fixed]
    if not fixed_cards:
        return None
    fixed_cards.sort(key=lambda card: (card.owner.name, card.zone.name, card.entity_id))
    lines = ["[GameSummary]:"]
    for card in fixed_cards:
        lines.append(card.get_debug_game())
    return "\n".join(lines) + "\n\n"

def format_predictions(predictions: list[Prediction]) -> Optional[str]:
    if not predictions:
        return None

    lines = ["[DeckGuess]"]

    for idx, pred in enumerate(predictions, start=1):
        deck_data = pred.deck or {}
        arch_id = deck_data.get("archetype_id")
        deck_id = deck_data.get("deck_id")
        win_rate = deck_data.get("win_rate")
        games = deck_data.get("total_games")
        avg_turns = deck_data.get("avg_num_player_turns")
        avg_length = deck_data.get("avg_game_length_seconds")

        deck_name = None
        if arch_id is not None:
            try:
                deck_name = DeckIDtoName(arch_id)
            except Exception:
                deck_name = None
        if not deck_name:
            deck_name = deck_data.get("name") or "Unknown Deck"

        details = [f"score {pred.score}"]
        if win_rate is not None:
            details.append(f"WR {win_rate:.1f}%")
        if games is not None:
            details.append(f"{games} games")
        if avg_turns is not None:
            details.append(f"{avg_turns:.1f} turns avg")
        if avg_length is not None:
            details.append(f"{avg_length:.0f}s avg len")
        if arch_id is not None:
            details.append(f"arch {arch_id}")
        if deck_id:
            details.append(f"id {deck_id}")

        entry_lines = [f"  {idx}. {deck_name}"]
        if details:
            entry_lines.append(f"     {'; '.join(details)}")
        lines.append("\n".join(entry_lines))

    return "\n".join(lines) + "\n\n"
