import re
from typing import Optional
from enum import Enum


# TODO: there are possibly more zones than this 8 (i.e. quest, passive ?)
# in consideration : keeping only DECK, HAND, PLAY, GRAVEYARD and OTHER
class ZONE(Enum):
    DECK = 0
    HAND = 1
    PLAY = 2
    GRAVEYARD = 3
    SECRET = 4
    SETASIDE = 5
    REMOVEDFROMGAME = 6
    INVALID = 7


class PLAYER(Enum):
    FRIENDLY = 0
    OPPOSING = 1


transition_pattern = re.compile(
    r"TRANSITIONING card "
    r"\[entityName=(?P<name>[^\[]+)"  # capture name until first '['
    r".*?id=(?P<entity_id>\d+)\b"  # find id=NUMBER
    r".*?zone=(?P<zone>\w+)"  # find zone=TEXT NOT IMPORTANT FOR NOW
    r".*?cardId=(?P<card_id>\S*)"  # find cardId= (may be empty)
    r".*?player=(?P<player>\d+)"  # find player=#
    r"\]\s+to\s+(?P<dst>.*)",  # find " to DST"
    re.IGNORECASE,
)


# Based on string version of a zone (either from zone or dst) cast it onto Enum class specified above
def normalize_zone(zone: str) -> ZONE:
    for z in ZONE:
        if z.name in zone:
            return z
    return ZONE.INVALID


class Card:
    def __init__(self, entity_id: int, owner: PLAYER):
        self.entity_id = entity_id  # ID of anonymous card locally (set only during initialization phase)
        self.owner = owner
        self.prev_zone: Optional[ZONE] = None
        self.zone: ZONE = ZONE.DECK
        self.card_id: Optional[str] = None  # ID of specific card globally
        self.name: Optional[str] = None
        self.fixed: bool = (
            False  # whether the card name was fixed (revealed) at some point
        )
        self.dbf_id: Optional[int] = None
        self.fixed_round: Optional[int] = None
        self.hand_round: Optional[int] = None

    # Update card info, if card is revealed, return fixed_card as true
    def update(self, name: Optional[str], card_id: Optional[str], zone: ZONE) -> bool:
        fixed = self.fixed

        if name and name != "UNKNOWN ENTITY":
            if name != self.name:
                self.name = name
                self.fixed = True

        if card_id and card_id != "UNKNOWN":
            if card_id != self.card_id:
                self.card_id = card_id
                self.fixed = True

        self.prev_zone = self.zone
        self.zone = zone
        return self.fixed != fixed

    # Printing card state in SHORT form
    def short(self):
        name = self.name or "Unknown"
        cid = self.card_id or "?"
        return f"{name} ({cid})"

    def set_dbf_id(self, dbf_id: Optional[int]) -> None:
        if dbf_id is not None:
            self.dbf_id = dbf_id

    def set_fixed_round(self, round_label: int) -> None:
        if self.fixed_round is None:
            self.fixed_round = round_label

    def set_hand_round(self, round_label: int) -> None:
        if self.hand_round is None:
            self.hand_round = round_label

    def get_payload(self) -> Optional[dict]:
        if self.dbf_id is None or self.fixed_round is None:
            return None
        payload = {
            "player": self.owner.name,
            "round_fixed": self.fixed_round,
            "dbfId": self.dbf_id,
            "card_name": self.name,
            "zone": self.zone.name,
        }
        if self.hand_round is not None:
            payload["round_hand"] = self.hand_round
        return payload

    def get_debug_fixed(self, zone_label: str) -> str:
        return f"  FIXED: {self.owner.name} {self.short()} @ {zone_label} (entity {self.entity_id})"

    def get_debug_move(self, from_zone: str, to_zone: str) -> str:
        return f"  MOVE: {self.owner.name} {self.short()} {from_zone} -> {to_zone} (entity {self.entity_id})"

    def get_debug_game(self) -> str:
        name = self.name or "Unknown"
        dbf_id = self.dbf_id if self.dbf_id is not None else "?"
        zone_label = self.zone.name
        round_label = self.fixed_round if self.fixed_round is not None else "?"
        return f" {round_label} {self.owner.name} {name} ({dbf_id}) @ {zone_label} (entity {self.entity_id})"


class PlayerState:
    def __init__(self, label: PLAYER):
        self.label = label
        self.cards: dict[int, Card] = {}

    def create_card(self, entity_id: int):
        self.cards[entity_id] = Card(entity_id, self.label)

    def get(self, entity_id: int) -> Card | None:
        if entity_id in self.cards.keys():
            return self.cards[entity_id]
        return None

    # Function that returns all Cards owned by the Player that are located in specified zone
    def by_zone(self, zone: ZONE):
        return [c for c in self.cards.values() if c.zone == zone]


class Tracker:
    def __init__(self):
        self.players: dict[PLAYER, PlayerState] = {}
        self.mapping: dict[int, PLAYER] = {}
        self.learned_mapping = False
        self.deck_counts: dict[PLAYER, dict[int, int]] = {
            PLAYER.FRIENDLY: {},
            PLAYER.OPPOSING: {},
        }

    # Learning mapping is always called once for first TRANSITIONING message with player = 1
    # player = 2 is automatically chosen
    # TODO: There would be cases where this is not true. Haven't met this case yet though.
    def learn_mapping(self, src: str, dst: str):
        s, d = (src or "").strip().upper(), (dst or "").strip().upper()
        if "FRIENDLY" in s or "FRIENDLY" in d:
            self.mapping[1] = PLAYER.FRIENDLY
            self.mapping[2] = PLAYER.OPPOSING
        else:
            self.mapping[1] = PLAYER.OPPOSING
            self.mapping[2] = PLAYER.FRIENDLY
        self.learned_mapping = True

    # get or create and get player state
    def get_player(self, pid: int) -> PlayerState:
        player = self.mapping[pid]
        if pid not in self.players:
            self.players[pid] = PlayerState(player)
        return self.players[pid]

    # Handle event of card state change. Return tuple:
    #   - success : Bool
    #   - fixed card name : Bool
    #   - transition between zones : Bool
    #   - card : Card/None
    def handle_event(
        self, event, init_phase: bool
    ) -> tuple[bool, bool, bool, Optional[Card]]:
        if not self.learned_mapping:
            self.learn_mapping(event["zone"], event["dst"])

        player = self.get_player(event["player"])

        if init_phase:
            player.create_card(event["entity_id"])

        card = player.get(event["entity_id"])

        if card is None:
            return False, False, False, None

        zone = normalize_zone(event["dst"])

        fixed = card.update(event["card_name"], event["card_id"], zone)
        moved = card.prev_zone != zone

        return True, fixed, moved, card

    def update_deck_counts(self, card: Card) -> dict[int, int]:
        if card.dbf_id is None or not card.fixed:
            return {}

        from_deck = card.prev_zone == ZONE.DECK and card.zone != ZONE.DECK
        to_deck = card.prev_zone != ZONE.DECK and card.zone == ZONE.DECK
        if not from_deck and not to_deck:
            return {}

        delta = 1 if from_deck else -1
        counts = self.deck_counts.setdefault(card.owner, {})
        new_count = max(0, counts.get(card.dbf_id, 0) + delta)
        if new_count > 0:
            counts[card.dbf_id] = new_count
        else:
            counts.pop(card.dbf_id, None)
        return {card.dbf_id: new_count}

    def get_deck_counts(self, player: PLAYER) -> dict[int, int]:
        return dict(self.deck_counts.get(player, {}))

    def reset_deck_counts(self) -> None:
        self.deck_counts = {
            PLAYER.FRIENDLY: {},
            PLAYER.OPPOSING: {},
        }

    # Simple debug info - not used outside
    def print_summary(self):
        print("\n===== CURRENT CARD STATES =====")
        for pid, player in self.players.items():
            print(f"\n{player.label.name}:")
            zones = {z for z in ZONE}
            for z in zones:
                cards = "\n  ".join(
                    str(c.entity_id) + " " + c.short() for c in player.by_zone(z)
                )
                print(f" {z.name}: \n  {cards if cards else 'EMPTY'}\n")
        print("===============================\n")


# Recognize the pattern from the line
def process_line(line: str):
    m = transition_pattern.search(line)
    if not m:
        return None

    return {
        "card_name": m.group("name").strip(),
        "entity_id": int(m.group("entity_id")),
        "card_id": m.group("card_id"),
        "zone": m.group(
            "zone"
        ),  # Zone is sometimes different than dst, but not always, better track both, even if only one used for now
        "dst": m.group("dst"),
        "player": int(m.group("player")),
    }


# The main loop was moved to app.py at the repository root to keep this module
# focused on parsing and tracking. get_latest_log_folder is retained for reuse.
