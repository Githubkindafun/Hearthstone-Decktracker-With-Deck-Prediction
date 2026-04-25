from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scraping import CardIdToPicTile
from deck.deck_assets import MAX_DOWNLOAD_WORKERS

DEFAULT_ALL_CARDS_PATH = PROJECT_ROOT / "electron_ui" / "data" / "all_cards.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "electron_ui" / "data" / "card_images"


def load_dbf_ids(path: Path) -> list[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("cards", [])
    ids: list[int] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("dbfId")
        if raw_id is None:
            continue
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


def download_tiles(card_ids: list[int], out_dir: Path, workers: int) -> tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    missing = [card_id for card_id in card_ids if not (out_dir / f"{card_id}.webp").exists()]
    if not missing:
        return 0, 0

    downloaded = 0
    failed = 0

    def _worker(card_id: int) -> int:
        try:
            return 1 if CardIdToPicTile(card_id, output_dir=out_dir) else 0
        except Exception:
            return -1

    max_workers = min(max(1, workers), len(missing))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for result in pool.map(_worker, missing):
            if result > 0:
                downloaded += 1
            else:
                failed += 1
    return downloaded, failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prefetch Hearthstone card tiles into the local source directory."
    )
    parser.add_argument("--all-cards", type=Path, default=DEFAULT_ALL_CARDS_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--workers", type=int, default=MAX_DOWNLOAD_WORKERS)
    args = parser.parse_args()

    if not args.all_cards.exists():
        print(f"all_cards.json not found: {args.all_cards}")
        return 1

    card_ids = load_dbf_ids(args.all_cards)
    if not card_ids:
        print(f"No card ids found in {args.all_cards}")
        return 1

    print(f"Cards: {len(card_ids)}")
    downloaded, failed = download_tiles(card_ids, args.out_dir, args.workers)
    print(f"Downloaded: {downloaded}")
    if failed:
        print(f"Failed: {failed}")
    print(f"Output: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
