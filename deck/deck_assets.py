from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from scraping import CardIdToPicTile, CardIdToPicRender

MAX_DOWNLOAD_WORKERS = 10


class DeckAssets:
    def __init__(
        self,
        cards_photos_dir: Path,
        decks_dir: Path,
        cards_source_dir: Optional[Path] = None,
    ) -> None:
        self.cards_photos_dir = cards_photos_dir
        self.decks_dir = decks_dir
        self.cards_source_dir = cards_source_dir

    def _source_path(self, dbf_id: int) -> Optional[Path]:
        if self.cards_source_dir is None:
            return None
        return self.cards_source_dir / f"{dbf_id}.webp"

    def _render_filename(self, dbf_id: int) -> str:
        return f"card{dbf_id}.png"

    def _source_render_path(self, dbf_id: int) -> Optional[Path]:
        if self.cards_source_dir is None:
            return None
        return self.cards_source_dir / self._render_filename(dbf_id)

    def _download_image(self, dbf_id: int, output_dir: Path, image_kind: str) -> None:
        if image_kind == "tile":
            CardIdToPicTile(dbf_id, output_dir=output_dir)
        elif image_kind == "render":
            CardIdToPicRender(dbf_id, output_dir=output_dir, prefix="card")

    def ensure_image(
        self,
        dbf_id: Optional[int],
        output_dir: Optional[Path] = None,
        image_kind: str = "tile",
    ) -> bool:
        if dbf_id is None:
            return False
        if image_kind not in {"tile", "render"}:
            return False
        target_dir = output_dir or self.cards_photos_dir
        filename = f"{dbf_id}.webp" if image_kind == "tile" else self._render_filename(dbf_id)
        target = target_dir / filename
        if target.exists():
            return False
        source_path = self._source_path(dbf_id) if image_kind == "tile" else None
        if source_path is not None:
            if not source_path.exists():
                self._download_image(dbf_id, source_path.parent, image_kind)
            if not source_path.exists():
                print(
                    f"[assets] {image_kind} download failed: dbf_id={dbf_id} source={source_path}"
                )
            if source_path.exists() and source_path != target:
                try:
                    if source_path != target:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, target)
                    return target.exists()
                except OSError:
                    pass
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            self._download_image(dbf_id, target_dir, image_kind)
            if not target.exists():
                print(
                    f"[assets] {image_kind} download failed: dbf_id={dbf_id} target={target}"
                )
        return target.exists()

    def image_exists(
        self,
        dbf_id: Optional[int],
        output_dir: Optional[Path] = None,
        image_kind: str = "tile",
    ) -> bool:
        if dbf_id is None:
            return False
        if image_kind not in {"tile", "render"}:
            return False
        target_dir = output_dir or self.cards_photos_dir
        filename = f"{dbf_id}.webp" if image_kind == "tile" else self._render_filename(dbf_id)
        return (target_dir / filename).exists()
    
    def download_core_cards(self, card_ids: list[int]) -> tuple[int, Optional[str]]:
        """Downloads images for a list of card IDs into a shared 'opponent_core' folder."""
        try:
            # Używamy stałej nazwy "opponent_core" jako wirtualnego decku
            target_dir = self.decks_dir / "opponent_core" / "cards_photos"
            target_dir.mkdir(parents=True, exist_ok=True)
            
            unique_ids = {c for c in card_ids if c is not None}
            missing = [
                card_id
                for card_id in unique_ids
                if not self.image_exists(card_id, output_dir=target_dir)
                or not self.image_exists(card_id, output_dir=target_dir, image_kind="render")
            ]
            print(f"[assets] core_images missing={len(missing)} dir={target_dir}")
            if not missing:
                return 0, None

            downloaded = 0

            def _worker(card_id: int) -> int:
                downloaded = 1 if self.ensure_image(card_id, output_dir=target_dir) else 0
                self.ensure_image(card_id, output_dir=target_dir, image_kind="render")
                return downloaded

            max_workers = min(MAX_DOWNLOAD_WORKERS, len(missing))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for result in pool.map(_worker, missing):
                    downloaded += result
            return downloaded, None
        except Exception as e:
            return 0, str(e)

    def clear_card_photos(self) -> None:
        if not self.cards_photos_dir.exists():
            return
        try:
            for path in self.cards_photos_dir.glob("*.webp"):
                path.unlink(missing_ok=True)
            # Flush opponent render assets created during gameplay.
            for path in self.cards_photos_dir.glob("card*.png"):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def clear_opponent_core_photos(self) -> None:
        target_dir = self.decks_dir / "opponent_core" / "cards_photos"
        if not target_dir.exists():
            return
        try:
            for path in target_dir.glob("*.webp"):
                path.unlink(missing_ok=True)
            # Flush opponent-core render assets.
            for path in target_dir.glob("card*.png"):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def download_deck_images(self, deck_id: str) -> tuple[int, Optional[str]]:
        try:
            deck_path = self._find_deck_json(deck_id)
            if deck_path is None:
                return 0, "deck_not_found"

            card_ids = self._load_deck_card_ids(deck_path)
            deck_images_dir = self.decks_dir / deck_id / "cards_photos"

            unique_ids = sorted(set(card_ids))
            missing = [
                card_id
                for card_id in unique_ids
                if not self.image_exists(card_id, output_dir=deck_images_dir)
                or not self.image_exists(card_id, output_dir=deck_images_dir, image_kind="render")
            ]
            print(f"[assets] deck_images deck_id={deck_id} missing={len(missing)} dir={deck_images_dir}")
            if not missing:
                return 0, None

            downloaded = 0

            def _worker(card_id: int) -> int:
                downloaded = 1 if self.ensure_image(card_id, output_dir=deck_images_dir) else 0
                self.ensure_image(card_id, output_dir=deck_images_dir, image_kind="render")
                return downloaded

            max_workers = min(MAX_DOWNLOAD_WORKERS, len(missing))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for result in pool.map(_worker, missing):
                    downloaded += result
            return downloaded, None
        except Exception:
            return 0, "deck_load_failed"

    def _load_deck_card_ids(self, deck_path: Path) -> list[int]:
        with open(deck_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        cards = data.get("cards", []) if isinstance(data, dict) else []
        ids: list[int] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            raw_id = card.get("cardId") or card.get("dbfId")
            if raw_id is None:
                continue
            try:
                ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        return ids

    def _find_deck_json(self, deck_id: str) -> Optional[Path]:
        deck_dir = self.decks_dir / deck_id
        if deck_dir.is_dir():
            for name in ("deck.json", f"{deck_id}.json"):
                path = deck_dir / name
                if path.exists():
                    return path
            for path in deck_dir.glob("*.json"):
                return path
        legacy = self.decks_dir / f"{deck_id}.json"
        if legacy.exists():
            return legacy
        return None
