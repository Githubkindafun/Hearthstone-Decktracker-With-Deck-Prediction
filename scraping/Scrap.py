import json
import threading
from pathlib import Path
from tokenize import String
from typing import Optional, List, Dict, Any
from collections import defaultdict
import heapq
import requests

# Pobiera ze strony zaktualizowane dane, no chyba że znowu zmienią linki to nie zadziała
#update_data.data() 

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent 

def _load_json(filename):
    with open(BASE_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


metaDecks = _load_json("archetypes.json")
cards = _load_json("cards.json")
matchupsInfo = _load_json("matchups.json")['series']['data']
decksInfo = _load_json("deckInfo.json")['series']['data']
listDecks = _load_json("listDecks.json")['series']['data']

_IGNORE = {"HERO_POWER", "ENCHANTMENT"}

_SESSION_LOCAL = threading.local()

def _get_session():
    sess = getattr(_SESSION_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4, pool_maxsize=4, max_retries=1
        )
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _SESSION_LOCAL.session = sess
    return sess
classes = ['deathknight', 'demonhunter', 'druid', 'hunter', 'mage', 'paladin', 'priest', 'rogue', 'shaman', 'warlock', 'warrior']

# ------------------------- META DECKS ---------------------------------------

# Wszystkie decki danej klasy
def ClassDeck(class_name):
    return [d for d in metaDecks if d["player_class_name"] == class_name.upper()]

# Nazwa decku na Archetype_ID
def DeckNametoAID(deck_name):
    deck = next((d for d in metaDecks if d["name"].lower() == deck_name.lower()), None)
    if deck is None:
        return classOtherDeckID(deck_name.split()[-1].lower())
    id = deck['id']
    return id

# ID na nazwe decku
def DeckIDtoName(deck_id):
    if deck_id < 0:
        return OtherDecks(deck_id)
    deck = next(d for d in metaDecks if d['id'] == deck_id)
    name = deck['name']
    return name

# Core karty danego decku - niektóre decki mają nulla na standart_cpp_signature_core
def GetCoreCards(deck_name):
    deck = next(d for d in metaDecks if d["name"] == deck_name)
    core_cards = deck["standard_ccp_signature_core"]["components"]
    return core_cards

def DeckNameClass(deck_name):
    deck = next((d for d in metaDecks if d["name"].lower() == deck_name.lower()), None)
    if deck is None:
        return deck_name.split()[-1]
    c = deck['player_class_name']
    return c

# ------------------------- DECK INFO ---------------------------------------

def FoundDeck(deck_name):
    class_name = DeckNameClass(deck_name)
    deck_id = DeckNametoAID(deck_name)

    classInfo = decksInfo[class_name.upper()]

    found = next((d for d in classInfo if d["archetype_id"] == deck_id), None)
    if not found:
        found = next(d for d in classInfo if d["archetype_id"] == -1)
    
    return found

def DeckPopularity(deck_name):

    found = FoundDeck(deck_name)
    return found['pct_of_total']

def DeckWinrate(deck_name):

    found = FoundDeck(deck_name)
    return found['win_rate']

def DeckTotalGames(deck_name):

    found = FoundDeck(deck_name)
    return found['total_games']

def GetFullDeck2(deck_id: str) -> List[Dict[str, Any]]:
    for class_name, decks_list in listDecks.items():
        for d in decks_list:
            if d.get('deck_id') == deck_id:
                raw_list_str = d.get('deck_list', "[]")
                try:
                    raw_list = json.loads(raw_list_str)
                except json.JSONDecodeError:
                    return []
                
                final_cards = []
                cards_map = {c['dbfId']: c for c in cards if 'dbfId' in c}

                for item in raw_list:
                    if len(item) < 2: continue
                    
                    dbf_id = item[0]
                    qty = item[1]
                    
                    c_info = cards_map.get(dbf_id)
                    if c_info:
                        final_cards.append({
                            "dbfId": dbf_id,
                            "name": c_info.get("name", "Unknown"),
                            "mana": c_info.get("cost", 0),
                            "rarity": c_info.get("rarity", "COMMON"),
                            "qty": qty
                        })
                
                return final_cards

print(GetFullDeck2("7bLxXSD80cRzqSY5AzAQVd"))
print("--------------------------------------------")
         
# --- NOWA FUNKCJA (Dla Full Deck Overlay) ---
def GetFullDeck(archetype_id: int) -> List[Dict[str, Any]]:
    """
    Pobiera pełną listę kart dla danego archetype_id z listDecks.json.
    Wybiera wariant z największą liczbą gier.
    """
    candidates = []
    
    # listDecks jest słownikiem { "CLASS_NAME": [ {deck_obj}, ... ] }
    for class_name, decks_list in listDecks.items():
        for d in decks_list:
            if d.get('archetype_id') == archetype_id:
                candidates.append(d)
    
    if not candidates:
        return []

    # Wybieramy najpopularniejszą wersję tego decku
    best_deck = max(candidates, key=lambda x: x.get('total_games', 0))
    
    # deck_list jest stringiem: "[[123, 2], [456, 1]]"
    raw_list_str = best_deck.get('deck_list', "[]")
    try:
        raw_list = json.loads(raw_list_str)
    except json.JSONDecodeError:
        return []

    final_cards = []
    # Tworzymy szybką mapę kart, żeby nie iterować po `cards` 30 razy
    cards_map = {c['dbfId']: c for c in cards if 'dbfId' in c}

    for item in raw_list:
        # item to [dbfId, qty]
        if len(item) < 2: continue
        
        dbf_id = item[0]
        qty = item[1]
        
        c_info = cards_map.get(dbf_id)
        if c_info:
            final_cards.append({
                "dbfId": dbf_id,
                "name": c_info.get("name", "Unknown"),
                "mana": c_info.get("cost", 0),
                "rarity": c_info.get("rarity", "COMMON"),
                "qty": qty
            })
    
    return final_cards

print(GetFullDeck(842))   
# ---------------------------------------------

# ------------------------- CARDS ---------------------------------------

# ! ID karty w DECKU to dbfID karty w kartach !

def CardIdToName(id):
    card = next(c for c in cards if c['dbfId'] == id)
    return card['name']

def CardIdToType(id):
    card = next(c for c in cards if c['dbfId'] == id)
    return card["type"]

def CardIdIsPlayableHero(id) -> bool:
    card = next(c for c in cards if c['dbfId'] == id)
    if not card:
        return False
    if card["type"] != "HERO":
        return False
    cost = card.get("cost")
    if cost is None:
        return False
    try:
        return int(cost) > 0
    except (TypeError, ValueError):
        return False

def CardIdShouldIgnore(id) -> bool:
    card = next(c for c in cards if c['dbfId'] == id)
    if not card:
        return False
    card_type = card["type"]
    if card_type in _IGNORE:
        return True
    if card_type == "HERO":
        return not CardIdIsPlayableHero(id)
    return False

def CardNameToId(card_name):
    card = next(c for c in cards if c['name'] == card_name and 'cardClass' in c)
    return card['dbfId']

def CoreCardsNames(coreCards):
    names = []
    for id in coreCards:
        names.append(CardIdToName(id))
    return names

def CardToClass(id):
    card = next(c for c in cards if c['dbfId'] == id)
    if 'cardClass' in card:
        return card['cardClass']
    elif 'classes' in card and len(card['classes']) > 0:
        return card['classes']

def CardNameToClass(card_name):
    return CardToClass(CardNameToId(card_name))

def CardRealIdToId(real_id):
    card = next(c for c in cards if c['id'] == real_id)
    return card['dbfId']

def CardIdToRealId(id):
    card = next(c for c in cards if c['dbfId'] == id)
    return card['id']

def CardIdToPic(id):
    piccardid = CardIdToRealId(id)
    picname = str(id) + ".jpg"

    picurl = f"https://art.hearthstonejson.com/v1/512x/{piccardid}.jpg"
    session = _get_session()
    try:
        picresponse = session.get(picurl, timeout=(3, 10))
    except requests.RequestException as exc:
        print(f"[image] render request failed: {picurl} error={exc}")
        return None
    if picresponse.status_code == 200:
        with open(picname, "wb") as f:
            f.write(picresponse.content)

def CardIdToPicRender(id, output_dir: Optional[Path] = None, prefix: str = "card"):
    piccardid = CardIdToRealId(id)
    picname = f"{prefix}{id}.png" if prefix else f"{id}.png"
    out_path = _resolve_output_path(output_dir, picname)

    if out_path.exists():
        return out_path

    picurl = f"https://art.hearthstonejson.com/v1/render/latest/enUS/512x/{piccardid}.png"
    session = _get_session()
    try:
        picresponse = session.get(picurl, timeout=(3, 10))
    except requests.RequestException:
        return None
    if picresponse.status_code == 200:
        with open(out_path, "wb") as f:
            f.write(picresponse.content)
        return out_path
    print(f"[image] render request returned status={picresponse.status_code} url={picurl}")
    return None

def _resolve_output_path(output_dir: Optional[Path], filename: str) -> Path:
    if output_dir is None:
        return Path(filename)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename

def CardIdToPicTile(id, output_dir: Optional[Path] = None):
    piccardid = CardIdToRealId(id)
    picname = str(id) + ".webp"
    out_path = _resolve_output_path(output_dir, picname)

    if out_path.exists():
        return out_path

    picurl = f"https://art.hearthstonejson.com/v1/tiles/{piccardid}.webp"
    session = _get_session()
    try:
        picresponse = session.get(picurl, timeout=(3, 10))
    except requests.RequestException as exc:
        print(f"[image] tile request failed: {picurl} error={exc}")
        return None
    if picresponse.status_code == 200:
        with open(out_path, "wb") as f:
            f.write(picresponse.content)
        return out_path
    print(f"[image] tile request returned status={picresponse.status_code} url={picurl}")
    return None

#------------------------- CardNameToPossibleDecks działa ---------------------------------------

def StringDeckListToList(str_deck_list):
    if isinstance(str_deck_list, str):
        s = str_deck_list.strip()
        if s == '':
            return []
        if s.lower() in ('null', 'none'):
            return []
        else:
            parsed = json.loads(s)
            return [int(t[0]) for t in parsed if len(t) >= 2]

class Prediction:
    def __init__(self, deck, score):
        self.deck = deck
        self.score = score

class DeckPredictor:
    def __init__(self, class_name):
        self.class_name = class_name.upper()
        self.decks = ClassDeck(self.class_name)

        self.card_to_core_decks = defaultdict(set)
        self.card_to_decks = defaultdict(set)
        self.deck_meta = {}

        self.deck_scores = defaultdict(int)
        self.deck_win_rate = {}

        self._preprocess()
    
    def _preprocess(self):
        decks_list = listDecks[self.class_name]

        for lD in decks_list:
            deck_id = lD['deck_id']
            archetype_id = lD['archetype_id']

            if archetype_id < 0:
                continue

            self.deck_win_rate[deck_id] = lD.get('win_rate', 0.0)
            archetype_name = DeckIDtoName(archetype_id)

            self.deck_meta[deck_id] = archetype_name

            deck_cards = StringDeckListToList(lD['deck_list'])
            for card_id in deck_cards:
                self.card_to_decks[card_id].add(deck_id)

        for deck in self.decks:
            if deck['id'] >= 0:
                archetype_name = deck['name']
                core_cards = []
                if deck['standard_ccp_signature_core'] is not None:
                    core_cards = deck['standard_ccp_signature_core']['components']

                matching_decks = [
                    lD for lD in listDecks[self.class_name]
                    if lD['archetype_id'] == deck['id']
                ]

                for card_id in core_cards:
                    for lD in matching_decks:
                        self.card_to_core_decks[card_id].add(lD['deck_id'])
        
    def print_mappings(self):
        print("Card to Core Decks Mapping:")
        for card_id, decks in self.card_to_core_decks.items():
            card_name = CardIdToName(card_id)
            deck_names = ', '.join(decks)
            print(f"{card_name} ({card_id}): {deck_names}")

        print("\nCard to Decks Mapping:")
        for card_id, decks in self.card_to_decks.items():
            card_name = CardIdToName(card_id)
            deck_names = ', '.join(decks)
            print(f"{card_name} ({card_id}): {deck_names}")

    def observe_card(self, real_id: str):
        card_id = CardRealIdToId(real_id)

        for deck_id in self.card_to_core_decks.get(card_id, []):

            if deck_id in self.deck_scores:
                self.deck_scores[deck_id] += 4
            else:
                self.deck_scores[deck_id] = 4

        for deck_id in self.card_to_decks.get(card_id, []):
            if deck_id in self.deck_scores:
                self.deck_scores[deck_id] += 1
            else:
                self.deck_scores[deck_id] = 1

    def predict(self, k=5) -> list[Prediction]:
        top = heapq.nlargest(
            k,
            self.deck_scores.items(),
            key=lambda x: (x[1], self.deck_win_rate.get(x[0], 0.0))
        )

        return [
            Prediction(
                deck=next(lD for lD in listDecks[self.class_name] if lD['deck_id'] == deck_id),
                score=score
            )
            for deck_id, score in top
        ]

    
# ------------------------- MATCHUP INFO ---------------------------------------

# -1 : deathknight
# -4 : mage
# -9 : warlock
# -6 : priest
# -10 : warrior
# -2 : druid
# -3 : hunter
# -14 : demonhunter
# -8 : shaman
# -5 : paladin
# -7 : rogue

def classOtherDeckID(class_name):
    match class_name.lower():
        case 'deathknight':
            return -1
        case 'druid':
            return -2
        case 'hunter':
            return -3
        case 'mage':
            return -4
        case 'paladin':
            return -5
        case 'priest':
            return -6
        case 'rogue':
            return -7
        case 'shaman':
            return -8
        case 'warlock':
            return -9
        case 'warrior':
            return -10
        case 'demonhunter':
            return -14
        
def OtherDecks(deck_id):
    match deck_id:
        case -1:
            return 'Other DeathKnight'
        case -2:
            return 'Other Druid'
        case -3:
            return 'Other Hunter'
        case -4:
            return 'Other Mage'
        case -5:
            return 'Other Paladin'
        case -6:
            return 'Other Priest'
        case -7:
            return 'Other Rogue'
        case -8:
            return 'Other Shaman'
        case -9:
            return 'Other Warlock'
        case -10:
            return 'Other Warrior'
        case -14:
            return 'Other DemonHunter'

def Matchup(my_deck_name, enemy_deck_name):
    my_deck_id = DeckNametoAID(my_deck_name)
    enemy_deck_id = DeckNametoAID(enemy_deck_name)

    if str(my_deck_id) in matchupsInfo.keys():
        matchups = matchupsInfo[str(my_deck_id)]
    else:
        matchups = matchupsInfo[str(classOtherDeckID(DeckNameClass(my_deck_name)))]

    if str(enemy_deck_id) in matchups.keys():
        matchup = matchups[str(enemy_deck_id)]
    else:
        matchup = matchups[str(classOtherDeckID(DeckNameClass(enemy_deck_name)))]

    return matchup

def MatchupWinrate(my_deck_name, enemy_deck_name):
    matchup = Matchup(my_deck_name, enemy_deck_name)
    return matchup['win_rate']

def MatchupTotalGames(my_deck_name, enemy_deck_name):
    matchup = Matchup(my_deck_name, enemy_deck_name)
    return matchup['total_games']

# ------------------------- MY_DECK_GUESS -------------------------------

# Na podstawie naszego decku (z jsona który się tworzy) dostajemy nazwę naszego decku (tego najbardziej zbliżonego)
# Potem z nazwy naszego decku i nazwy decku przeciwnika, który będziemy predictować można brać matchup

def which_class(deck_list):
    card_classes = {}
    for card_id in deck_list:
        card_class = CardToClass(card_id)
        if isinstance(card_class, list):
            for c in card_class:
                if c != 'NEUTRAL':
                    if c in card_classes:
                        card_classes[c] += 1
                    else:
                        card_classes[c] = 1
        else:
            if card_class != 'NEUTRAL':
                if card_class in card_classes:
                    card_classes[card_class] += 1
                else:
                    card_classes[card_class] = 1
    if card_classes:
        return max(card_classes, key=card_classes.get)
    return "NEUTRAL"

def my_deck():
    DECK_ID = PROJECT_ROOT / "electron_ui" / "data" / "selectedDeck.json"
    with DECK_ID.open("r", encoding="utf-8") as f:
        d = json.load(f)
        deck_id = d["deckId"]
    
    cards = []
    deck_dir =  PROJECT_ROOT / "electron_ui" / "data" / "decks" / deck_id
    json_file = next(deck_dir.glob("*.json"))
    with json_file.open("r", encoding="utf-8") as f:
        deck = json.load(f)
        cards = deck['cards']
    
    scores = {}
    deck_class = {}
    deck_list = [int(c['cardId']) for c in cards]

    for c in cards:
        card_id = int(c["cardId"])
        for class_name in classes:
            for d in listDecks[class_name.upper()]:
                d_cards = StringDeckListToList(d['deck_list'])
                deck_id = d['deck_id']
                if card_id in d_cards:
                    deck_class[deck_id] = class_name.upper()
                    if deck_id in scores.keys():
                        scores[deck_id] += 1
                    else:
                        scores[deck_id] = 1
    
    if len(scores) == 0:
        class_name = which_class(deck_list)
        if class_name == "NEUTRAL":
            return "Unknown Deck"
        return OtherDecks(classOtherDeckID(class_name.lower()))
    
    guess = max(scores, key=scores.get)
    guess = next((d for d in listDecks[deck_class[guess]] if d["deck_id"] == guess), None)
    return DeckIDtoName(guess['archetype_id'])

#print(my_deck())

# ------------------------- TESTY ---------------------------------------

# print(MatchupWinrate("Quest Paladin", "Quest Shaman"))
# print(f'{DeckPopularity("deathknight", "leech death knight"):.1f}')
# print(CoreCardsNames(GetCoreCards('Aggro Paladin')))

#print(CardNameToDecksNames('Muster for Battle'))

# decks_names = CardNameToDecksCardsList('Zilliax Deluxe 3000')
# for k,v in decks_names.items():
#     print(f"{k}: {v}")
#     print()

# decks = CardNameToDecks('Zilliax Deluxe 3000')
# decks2 = EliminatePossibleDecks('Blizzard', decks)
# print(len(decks))
# print()
# print(len(decks2))

#print(CardIdToPicCardId(2549))
#print(CardIdToPic(2549))
#if __name__ == "__main__":
#    print(CardIdToPicTile(2549))

# --------------------------------------------------
# TESTY FUNKCJI META DECKS
#print(ClassDeck('deathknight')) # działa
#print(DeckNametoAID('Stegodon Death Knight')) # działa
#print(DeckIDtoName(808)) # działa
#print(GetCoreCards('Stegodon Death Knight')) # działa
#print(DeckNameClass('Stegodon Death Knight')) # działa

# TESTY FUNKCJI DECK INFO
#print(FoundDeck("Bwonsamdi Death Knight")) # działa
#print(DeckPopularity("Bwonsamdi Death Knight")) # działa
#print(DeckWinrate("Bwonsamdi Death Knight")) # działa
#print(DeckTotalGames("Bwonsamdi Death Knight")) # działa

# TESTY FUNKCJI CARDS
#print(CardIdToName(104998)) # działa
#print(CardNameToId("Fire Festival Ragnaros")) działa
#print(CoreCardsNames(GetCoreCards("Stegodon Death Knight"))) # działa
#print(CardToClass(104998)) # działa
#print(CardNameToClass("Fire Festival Ragnaros")) działa

# TESTY FUNKCJI MATCHUP

#print(Matchup("Midrange Shaman", "Protoss Mage")) # działa ale trzeba aktualizować jsony jak się zmienia meta - słabe
# jak to działa to MatchupWinrate i MatchupTotalGames też działają

# TESTY CardNameToPossibleDecks

# enemy_class = 'deathknight'
# predictor = DeckPredictor(enemy_class)
# #predictor.print_mappings()
# predictor.observe_card("TOY_330") # Zilliax Deluxe 3000
# predictor.observe_card("TIME_619t") # Bwonsamdi
# predictions = predictor.predict(5)
# for p in predictions:
#     print(p.score, DeckIDtoName(p.deck['archetype_id']), f"({p.deck['deck_id']})", f"Winrate: {p.deck.get('win_rate', 'N/A'):.2f}")