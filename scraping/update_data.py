import json
import requests
import cloudscraper

# ---- URL-e ----

URLS = {
    "archetypes": "https://hsreplay.net/api/v1/archetypes/?hl=en",
    "cards": "https://api.hearthstonejson.com/v1/latest/enUS/cards.json",
    "matchups": "https://hsreplay.net/analytics/query/head_to_head_archetype_matchups_v2/?GameType=RANKED_STANDARD&LeagueRankRange=BRONZE_THROUGH_GOLD&Region=ALL&TimeRange=LAST_7_DAYS",
    "deckInfo": "https://hsreplay.net/analytics/query/archetype_popularity_distribution_stats_v2/?GameType=RANKED_STANDARD&LeagueRankRange=BRONZE_THROUGH_GOLD&Region=ALL&TimeRange=LAST_7_DAYS",
    "listDecks": "https://hsreplay.net/analytics/query/list_decks_by_win_rate_v2/?GameType=RANKED_STANDARD&TimeRange=LAST_30_DAYS&Region=ALL&LeagueRankRange=BRONZE_THROUGH_GOLD"
}


# ---- scraper dla HSReplay ----
scraper = cloudscraper.create_scraper()

def fetch_hsreplay(url):
    r = scraper.get(url, timeout=20)
    if r.status_code != 200:
        print(f"[HSReplay] Błąd {r.status_code} dla {url}")
        return None

    text = r.text

    # usuń prefix jeśli jest
    if text.startswith(")]}',"):
        text = text[5:]

    try:
        return json.loads(text)
    except:
        print("Nie udało się sparsować JSON. Zapisuję do debug_hsreplay.html")
        with open("debug_hsreplay.html", "w", encoding="utf-8") as f:
            f.write(text)
        return None

def fetch_normal(url):
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        print(f"[NORMAL] Błąd {r.status_code} dla {url}")
        return None
    return r.json()

# ---- Pobieranie ----

def data():
    for name, url in URLS.items():
        print(f"Pobieram: {name} ...")

        if "hsreplay.net" in url:
            data = fetch_hsreplay(url)
        else:
            data = fetch_normal(url)

        if data is None:
            print(f"❌ Nie udało się pobrać: {name}")
            continue

        # Zapis
        out_file = f"{name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✔ Zapisano: {out_file}")

    print("\nGotowe!")
