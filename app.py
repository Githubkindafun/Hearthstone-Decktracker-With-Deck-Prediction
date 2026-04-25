from __future__ import annotations

import time
from pathlib import Path

from frontend import FrontendBridge
from game import GameSession
from log_analysis import find_hearthstone_install, resolve_player_log
from logs import iter_player_log

# CONFIGURATION
# - bridge
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 49777

# - directories
DATA_DIR = Path(__file__).resolve().parent / "electron_ui" / "data"
CARDS_PHOTOS_DIR = DATA_DIR / "cards_photos"
CARD_IMAGES_SOURCE_DIR = DATA_DIR / "card_images"
DECKS_DIR = DATA_DIR / "decks"

# - flags
INSTANT_UPDATES = True

LOG_CONFIG_CONTENT = (
    "[Power]\n"
    "LogLevel=1\n"
    "FilePrinting=true\n"
    "ConsolePrinting=true\n"
    "Verbose=false\n"
    "\n"
    "[Zone]\n"
    "LogLevel=1\n"
    "FilePrinting=true\n"
    "ConsolePrinting=true\n"
    "Verbose=false\n"
    "\n"
)


def ensure_log_config() -> None:
    install_dir = find_hearthstone_install()
    if not install_dir:
        print("Hearthstone install not found; log.config not updated.")
        return
    target = install_dir / "log.config"
    try:
        target.write_text(LOG_CONFIG_CONTENT, encoding="utf-8")
        print(f"log.config updated at {target}")
    except OSError as exc:
        print(f"Failed to update log.config at {target}: {exc}")


def prefetch_card_images() -> None:
    try:
        from scraping import prefetch_card_images as prefetch
    except Exception as exc:
        print(f"Prefetch disabled: {exc}")
        return

    try:
        if not prefetch.DEFAULT_ALL_CARDS_PATH.exists():
            print(
                f"Prefetch skipped: all_cards.json not found at {prefetch.DEFAULT_ALL_CARDS_PATH}"
            )
            return
        card_ids = prefetch.load_dbf_ids(prefetch.DEFAULT_ALL_CARDS_PATH)
        if not card_ids:
            print(f"Prefetch skipped: no card ids in {prefetch.DEFAULT_ALL_CARDS_PATH}")
            return
        downloaded, failed = prefetch.download_tiles(
            card_ids,
            prefetch.DEFAULT_OUT_DIR,
            prefetch.MAX_DOWNLOAD_WORKERS,
        )
        print(f"Prefetch tiles: downloaded={downloaded} failed={failed}")
    except Exception as exc:
        print(f"Prefetch tiles failed: {exc}")


# Main loop
def run() -> None:
    prefetch_card_images()
    ensure_log_config()
    # Initialize game session
    session = GameSession(
        CARDS_PHOTOS_DIR,
        DECKS_DIR,
        cards_source_dir=CARD_IMAGES_SOURCE_DIR,
        instant_updates=INSTANT_UPDATES,
    )
    session.set_catching_up(True)
    print(f"Game stage: {session._get_stage()}")

    # Connect to frontend bridge
    try:
        bridge = FrontendBridge(
            FRONTEND_HOST, FRONTEND_PORT, session.handle_frontend_message
        )
        session.set_bridge(bridge)
        bridge.start()
        print(f"Frontend bridge listening on {FRONTEND_HOST}:{FRONTEND_PORT}")
    except OSError as exc:
        print(f"Frontend bridge disabled: {exc}")
        session.set_bridge(None)

    # Locate Player.log (poll until available)
    player_log = resolve_player_log()
    while not player_log:
        print(
            "Waiting for Hearthstone Player.log. Check AppData\\LocalLow or set HEARTHSTONE_PLAYER_LOG."
        )
        time.sleep(2.0)
        player_log = resolve_player_log()

    print(f"Watching {player_log} ...")

    # Process log lines
    for source, line in iter_player_log(player_log, emit_catch_up=True):
        if source == "catch_up":
            session.catch_up_complete()
            continue
        if source not in {"power", "zone"}:
            continue
        if source == "power":
            update = session.handle_power_line(line)
        else:
            update = session.handle_zone_line(line)
        if update:
            print(update, end="")


if __name__ == "__main__":
    run()
