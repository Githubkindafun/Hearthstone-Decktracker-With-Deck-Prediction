import json
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent    
PROJECT_ROOT = BASE_DIR.parent             

INPUT_FILE = BASE_DIR / "cards.json"
OUTPUT_FILE = PROJECT_ROOT / "electron_ui" / "data" / "all_cards.json"
ALIAS_FILE = PROJECT_ROOT / "electron_ui" / "data" / "dbfId_aliases.json"

FORBIDDEN_SETS = {
    "BATTLEGROUNDS",
    "LETTUCE",
    "NAXX",
    "BRM",
    "LOE",
    "KARA",
    "TB",
    "TUTORIAL",
    "MISSIONS",
    "EVENT",
    "HERO_SKINS",
    "PET",
    "CREDITS",
    "PLACEHOLDER_202204",
    "TEST_TEMPORARY",
    "DEMO",
    "NONE",
    "CHEAT",
    "BLANK",
    "DEBUG_SP",
}

SET_PRIORITY = {
    "CORE": 4,
    "LEGACY": 3,
    "VANILLA": 1
}

# Filtering switches (balanced defaults). Toggle these as needed.
EXCLUDE_FORBIDDEN_SETS = True
EXCLUDE_HB_IDS = True
EXCLUDE_MISSING_COLLECTIBLE = False
EXCLUDE_NON_COLLECTIBLE_OR_NO_COST = False
EXCLUDE_TYPES = {"ENCHANTMENT", "HERO_POWER"}
EXCLUDE_ID_PREFIXES = {
    "TRLA",  # Rumble Run (Troll)
    "DALA",  # Dalaran Heist
    "ULDA",  # Tombs of Terror
    "BOM",   # Book of Mercenaries
    "Story", # Solo adventure story cards
    "PVPDR", # Duels buckets/passives
    "DRGA",  # Galakrond's Awakening
    "DFX",   # Dungeon Run FX placeholders
}
MERGE_BY_NAME = True

# Sets observed to be missing tiles in the current local cache benchmark.
# (Keep this list aligned with your downloaded tiles folder.)
EXCLUDE_SETS_MISSING_TILES = {
    "ICECROWN",
    "REVENDRETH",
    "EXPERT1",
    "DEMON_HUNTER_INITIATE",
    "PATH_OF_ARTHAS",
    "ULDUM",
    "DALARAN",
    "TROLL",
    "GILNEAS",
    "TGT",
    "LOOTAPALOOZA",
    "UNGORO",
    "BOOMSDAY",
    "GVG",
}

def is_forbidden(card):
    if EXCLUDE_FORBIDDEN_SETS and card.get("set") in FORBIDDEN_SETS:
        return True
    if card.get("set") in EXCLUDE_SETS_MISSING_TILES:
        return True
    if EXCLUDE_HB_IDS and "hb" in card.get("id", ""):
        return True
    if EXCLUDE_NON_COLLECTIBLE_OR_NO_COST:
        is_collectible = card.get("collectible") is True and card.get("cost") is not None
        if not is_collectible:
            return True
    return False

def is_token(card):
    cid = card.get("id", "")
    return cid.endswith(("t", "t1", "t2")) or "_t" in cid

def card_score(card):
    return (
        1 if card.get("collectible") else 0,
        SET_PRIORITY.get(card.get("set"), 2),
        # 0 if is_token(card) else 1,   # token zawsze gorszy
        card.get("dbfId", 0)
    )

def slim_card(card):
    result = {}
    for key in ("dbfId", "id", "cost", "name", "rarity"):
        if key in card:
            result[key] = card[key]
        else:
            result[key] = None
    return result

def filter_cards():
    with open(INPUT_FILE, encoding="utf-8") as f:
        cards = json.load(f)

    filtered = []
    for c in cards:
        if EXCLUDE_MISSING_COLLECTIBLE and c.get("collectible") is None:
            continue
        if is_forbidden(c):
            continue
        card_id = c.get("id", "")
        if card_id:
            if any(card_id.startswith(prefix) or card_id.startswith(prefix + "_") for prefix in EXCLUDE_ID_PREFIXES):
                continue
        if c.get("type") in EXCLUDE_TYPES:
            continue
        # if c.get("cost") is None:
        #     continue
        filtered.append(c)

    final_cards = []
    aliases: dict[str, int] = {}
    if MERGE_BY_NAME:
        by_name = defaultdict(list)
        for c in filtered:
            by_name[c["name"]].append(c)

        for name, versions in by_name.items():
            best = max(versions, key=card_score)
            final_cards.append(slim_card(best))
            best_id = best.get("dbfId")
            if best_id is None:
                continue
            for v in versions:
                vid = v.get("dbfId")
                if vid is None or vid == best_id:
                    continue
                aliases[str(vid)] = int(best_id)
    else:
        for c in filtered:
            final_cards.append(slim_card(c))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_cards, f, ensure_ascii=False, indent=2)

    print(f"Zapisano {len(final_cards)} kart do {OUTPUT_FILE}")

    with open(ALIAS_FILE, "w", encoding="utf-8") as f:
        json.dump(aliases, f, ensure_ascii=True, indent=2)

    print(f"Zapisano {len(aliases)} aliasów dbfId do {ALIAS_FILE}")

def check_duplicates():
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        cards = json.load(f)

    name_count = defaultdict(int)
    for c in cards:
        name_count[c["name"]] += 1

    duplicates = {name: count for name, count in name_count.items() if count > 1}
    if duplicates:
        print("Znaleziono duplikaty nazw kart:")
        for name, count in duplicates.items():
            print(f"{name}: {count} razy")
    else:
        print("Brak duplikatów nazw kart.")

filter_cards()
#check_duplicates()
