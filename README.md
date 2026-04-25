# Project  

## Aktualności
Aktualnie trwają prace konserwacyjne $\to$ szukanie bugów i ich naprawianie

## Overview
W ramach projektu tworzymy deck tracker do Hearthston'a z dodatkowymi funkcjonalnościami. 
Do śledzenia kart wykorzystujemy logi zapisywane przez silnik gry.

Na ten moment decktracker posiada:
### Śledzenie zagranych kart
W tym:
- możliwość podglądnięcia kart poprzez najechanie myszką na miniaturkę karty w nakładce
- informowanie użytkownika o kartach pozostałych w jego talii oraz kartach zagranych do tej pory przez przeciwnika

![alt text](/progress_photos/example_tracker.png)

### Zgadywanie decku przeciwnika
Wszystkie dane wykorzystywane podczas przewidywania zostały pożyczone ze strony [HSReplay](https://hsreplay.net/)

W tym:
- podgląd statystyk przewidywanej talii
- podgląd całej talii

![alt text](/progress_photos/example_guesser.png)

### Intergracja z HSReplay
Import z hsreplay poprzez skopiowanie decku ze strony i wklejenie w odpowiednie pole w kliencie moda.

![alt text](/progress_photos/example_menu.png)

## Instalacja i użycie

### Dodatkowe wymagania
1. NodeJs
2. python requests

### Uruchamianie
Na ten moment, decktracker musi być włączany ręcznie z linii poleceń w 2 katalogach:
1. w głównym katalogu `python app.py`
2. w electron_ui `npm start`

### Obsługa
* Ctrl + shift + D $\to$ zmiana między overaly/deck guessing
* Ctrl + shift + M $\to$ odpalenie menu gdzie mozna:
  * dodawać/modyfikować/usuwać decki
  * wybierać deck do rozgrywki

---
## assigments
### assigment 1
#### log analysis
* GithubKindaFun
* M1KKI47

#### enemy deck scraping
* Wlodarz03
* Jasiu Kamyk

### assigment 2

#### Frontend design + implementation
Plan polega na stworzeniu frontendu oraz połącznia go z działającym programem.
* GithubKindaFun
* Jasiu Kamyk

#### Deck Predicting + Pipeline
Połączone zostaną dwie wcześniej rozłączne części w jeden działający program.
* M1KKI47
* Wlodarz03

### assigment 3 
#### Testing & Consulting ;)
M1KKI47 błędów i potencjalnych usprawnień.
* Mikołaj
* GithubKindaFun
* Jasiu Kamyk
* Wlodarz03

#### Bug fixing
Wprowadzanie w życie poprawek wynikających z Testing & Consulting.
* M1KKI47 
* Wlodarz03 
* Jasiu Kamyk
* GithubKindaFun

#### Deck prediction
Łączenie segmentu deck prediction frontend + backend.
* Jasiu Kamyk
* Wlodarz03

