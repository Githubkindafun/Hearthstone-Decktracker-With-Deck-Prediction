from __future__ import annotations

from typing import Optional, Any
from log_analysis import Card, PLAYER

# Importujemy DeckPopularity oraz DeckIDtoName ze Scrap.py
from scraping.Scrap import (
    CardRealIdToId, CardToClass, DeckPredictor, DeckIDtoName, DeckPopularity
)
from formatting import format_predictions

class DeckGuessing:
    def __init__(self, predictions_to_show: int = 5) -> None:
        self.predictions_to_show = predictions_to_show
        self.opponent_class: Optional[str] = None
        self.deck_predictor: Optional[DeckPredictor] = None
        self.last_deck_guess: Optional[str] = None

    def reset(self) -> None:
        self.opponent_class = None
        self.deck_predictor = None
        self.last_deck_guess = None

    def update_guess(self, card: Card, debug: bool = False) -> Optional[list[dict[str, Any]]]:
        # 1. Sprawdź czy to karta przeciwnika
        if card.owner != PLAYER.OPPOSING:
            return None
        
        # 2. Inicjalizacja predictora
        predictor = self._ensure_deck_predictor(card)
        if not predictor:
            return None
        
        if not card.card_id:
            return None

        # 3. Obserwacja karty
        try:
            predictor.observe_card(card.card_id)
        except Exception as e:
            print(f"[DEBUG] Error observing card: {e}")
            return None

        # 4. Generowanie predykcji
        predictions = predictor.predict(self.predictions_to_show)
        if not predictions:
            return None

        top_arch_id = predictions[0].deck.get('archetype_id', -1)
        top_name = DeckIDtoName(top_arch_id)

        if debug:
            print(format_predictions(predictions))

        # 5. Formatowanie na JSON
        output = []
        for p in predictions:
            arch_id = p.deck.get('archetype_id', -1)
            deck_name = DeckIDtoName(arch_id)
            
            try:
                popularity = DeckPopularity(deck_name)
            except Exception:
                popularity = 0.0

            turns = p.deck.get('avg_num_player_turns', 0.0)

            output.append({
                "name": deck_name,
                "score": p.score,
                "archetype_id": arch_id,
                "deck_id": p.deck.get('deck_id'),  # <--- DODANO TĘ LINIJKĘ
                "win_rate": p.deck.get('win_rate', 0.0),
                "popularity": popularity,
                "total_games": p.deck.get('total_games', 0),
                "turns_per_game": turns
            })
            #print(p.deck.get('deck_id'))
        return output

    def _ensure_deck_predictor(self, card: Card) -> Optional[DeckPredictor]:
        if self.deck_predictor:
            return self.deck_predictor
        if card.card_id:
            try:
                self.opponent_class = CardToClass(CardRealIdToId(card.card_id))
            except Exception:
                self.opponent_class = None
        if self.opponent_class:
            try:
                self.deck_predictor = DeckPredictor(self.opponent_class)
            except Exception:
                self.deck_predictor = None
        return self.deck_predictor