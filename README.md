# Monitor eskalace

Průběžná OSINT předpověď ruské eskalace s veřejným archivem.

- Web: https://josefslerka.github.io/russia-escalation-monitor/
- Pracovní metodika: [AGENTS.md](AGENTS.md)
- Aktuální stav a úplné zdroje: [russia-escalation/](russia-escalation/)

## Mapa a signály

[Mapa a signály](https://josefslerka.github.io/russia-escalation-monitor/signals.html)
propojuje úplnou evidenci s mapou Evropy a světa, časovou osou a filtry podle oblasti,
tématu, doložení a směru signálu. Výběr včetně konkrétního záznamu lze sdílet URL.
Detail zachovává zdroje, alternativní vysvětlení, rozsah potvrzení a původní časové
údaje. Stránka má také textový přehled pro případ nedostupného JavaScriptu.

Geografie je anotována podle ID v `russia-escalation/geography.json`; původní
append-only evidence zůstává beze změny. Země označují geografický předmět, regiony
se nerozmisťují do domnělých bodů a chybějící anotace zůstávají neurčené. Mapa
počítá záznamy, nikoli útoky nebo nezávislá potvrzení. Nový důkaz má při ranní
aktualizaci dostat také geografickou anotaci podle `AGENTS.md`.

Generátor vytváří `data/signals.json` ze všech záznamů a anotací; nejde o další
úložiště prognóz. Knihovna D3 a mapová geometrie jsou připnuté místní soubory
v `site/assets/` s původními licencemi. Prohlížeč při čtení mapy nekontaktuje
externí mapové nebo analytické služby.

## Jak funguje ranní aktualizace

Od 28. října 2026 má web také [pokrytí zdrojů](https://josefslerka.github.io/russia-escalation-monitor/coverage.html),
[provenanci a vyhodnocování](https://josefslerka.github.io/russia-escalation-monitor/quality.html)
a [účinky a české scénáře](https://josefslerka.github.io/russia-escalation-monitor/society.html).
Mapa přepíná evidenci a pokrytí. Registr všech zemí EU/NATO neznamená kompletní
rešerši: skutečně provedené kontroly a mezery jsou doložené zvlášť.

Od 31. října 2026 se [krátké prognózy](https://josefslerka.github.io/russia-escalation-monitor/forecasts.html)
vydávají před začátkem pevných 7denních a 30denních oken. První začínají
31. října v 08:00 CET. Devět otázek má předem uložená kritéria, zdrojový panel
a termín vyhodnocení; dvě související podotázky jsou pouze diagnostické.
Stránka ukazuje také nevydané odhady, neznámé výsledky a negativní výsledky po
úplném auditu okna. Skóre se počítá samostatně podle horizontu a srovnává se
se strategií „vždy nenastane“. Číselné odhady vytváří skutečná ranní rešerše.

Každý den v 7:00 Europe/Prague proběhne rešerše v místním Codexu podle `AGENTS.md`.
Počítač a aplikace musejí být spuštěné a mít přístup k síti. Automatizace navazuje
na předchozí stav, uloží novou zprávu, doplní skutečně nové důkazy a aktualizuje
watchlist. Nezměněné pravděpodobnosti jsou platný výsledek.

Po úspěšné kontrole publikační skript uloží neměnný JSON snímek, commitne pouze
forecast data a odešle je do tohoto repozitáře. GitHub Actions vygeneruje a nasadí
statický web. GitHub samotnou rešerši nespouští; pro tuto variantu není potřeba
OpenAI API klíč. Čas 7:00 je začátek práce, nikoli garantovaný čas dokončení.

Při chybě se stávající web zachová a chyba se oznámí v Codexu nebo GitHub Actions.
Publikace nikdy nevytváří nové datum pro staré hodnocení. Zdrojové zprávy a evidence
se nepřepisují; opravy patří do nového hodnocení. Úplné JSON snímky jsou k dispozici
od zavedení webu, nikoli zpětně pro všechny starší zprávy.

## Dvě jazykové verze zpráv

Od **22. října 2026** vzniká každá zpráva česky i anglicky. Na stránce zprávy
je přepínač **Čeština / English**, který vede na stejnou uzávěrku v druhém jazyce
a funguje i bez JavaScriptu. Odkazy na obě verze jsou také v archivu; u aktuální
zprávy je anglický odkaz dostupný přímo z přehledu.

Český soubor `reports/YYYY-MM-DD-HHMM.md` si zachovává adresu. Úplný anglický
překlad je uložen jako `reports/YYYY-MM-DD-HHMM.en.md`. Sdílejí jeden stav,
snímek a položku archivu. Generátor nepřekládá text automaticky; obě verze připraví
a významově porovná ranní analytický běh podle `AGENTS.md`.

Publikace od tohoto data vyžaduje oba soubory a kontroluje shodu tabulek,
pravděpodobností, důvěry, uzávěrky, horizontu, WDPI a zdrojových odkazů.
Při chybě se nová verze nenasadí. Starší české zprávy zůstávají beze změny;
přehled, obecný archiv a metodika zatím zůstávají česky.

## Místní spuštění

Vyžaduje Python 3.10+ s databází časových pásem.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-site.txt
.venv/bin/python scripts/build_site.py
.venv/bin/python scripts/check_site.py
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory _site
```

Náhled: http://127.0.0.1:8765

Po dokončení nové rešerše:

```sh
.venv/bin/python scripts/publish_update.py --push
```

Bez `--push` se provede pouze kontrola, vytvoření JSON snímku a místní sestavení.

Pro samotnou údržbu geografie, pokrytí a označené retrospektivní doplnění:

```sh
.venv/bin/python scripts/publish_update.py --metadata-only --push
```

Tento režim nemění stav, uzávěrku, zprávy ani snímky a může publikovat i při starší
prognóze. Historická evidence čeká na samostatné analytické začlenění. Publikace
hlídá neměnnou historii evidence, reportů, snímků a všech auditních JSONL protokolů.

Pracovní fronta, validace a bezpečné doplnění auditního protokolu:

```sh
.venv/bin/python scripts/monitor.py due
.venv/bin/python scripts/monitor.py validate
.venv/bin/python scripts/monitor.py origins
.venv/bin/python scripts/forecast.py plan
.venv/bin/python scripts/forecast.py issue --input /tmp/researched-fixed-forecasts.json
.venv/bin/python scripts/forecast.py resolve --input /tmp/fixed-outcomes.json
.venv/bin/python scripts/forecast.py evaluate
.venv/bin/python scripts/monitor.py append coverage.jsonl --input /tmp/check.json
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

`sources.json` určuje denní kontroly, týdenní rotaci a měsíční audit.
`monitoring-runs.jsonl` uchovává zamýšlené úkoly; `coverage.jsonl` skutečné výsledky.
Události a jejich linie jsou v `events.json`, následné kontroly v
`case-reviews.jsonl`, pozorovatelné indikátory v `indicators.json`. Měření účinků
a jejich verze jsou v `metrics.json` a `metric-observations.jsonl`.
`forecast-register.jsonl` zmrazuje otázky a `forecast-resolutions.jsonl`
uchovává jejich adjudikace v původním dlouhém registru.
`forecast-protocol.json` stanovuje neměnná krátká okna a kritéria;
`forecast-rounds.jsonl` a `forecast-outcomes.jsonl` uchovávají skutečná vydání a
výsledky. `plan` nabízí prázdné vstupní šablony, neodhaduje pravděpodobnosti.
Zpětné vydání, posun okna, změna staré definice nebo nepodložené „ne“ zablokují
validaci. Podrobné schéma, pravidla příčinného hodnocení,
WDPI v2 a integrace do ranního běhu jsou v [AGENTS.md](AGENTS.md).

Nová registrace a důkazy nevznikají samotným zobrazením fronty nebo sestavením webu.
Nezměřené hodnoty zůstávají neznámé; historické skóre se nepřepočítává novou metodou.
Opakovaný běh se stejným stavem nevytváří duplicitní commit. Pokud vzdálená větev
obsahuje nezahrnuté změny, publikace se zastaví; neprovádí force push ani automatické
přepisování. Jiné lokální commity se automaticky neposílají.

## GitHub Pages

V Settings → Pages je zdrojem **GitHub Actions**. Workflow `.github/workflows/pages.yml`
reaguje na změny forecast dat, generátoru a vzhledu ve větvi `main` nebo `master`.
Publikuje pouze obsah `_site/`, nikoli celý pracovní adresář. Zdrojový repozitář je
veřejný; `defensive-threat-intel/`, lokální prostředí a soubory s tajnými hodnotami
nejsou součástí tohoto projektu.

Dokumentace: [místní plánované úlohy](https://learn.chatgpt.com/docs/automations),
[GitHub Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
