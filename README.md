# Monitor eskalace

Průběžná OSINT předpověď ruské eskalace s veřejným archivem.

- Web: https://josefslerka.github.io/russia-escalation-monitor/
- Pracovní metodika: [AGENTS.md](AGENTS.md)
- Aktuální stav a úplné zdroje: [russia-escalation/](russia-escalation/)

## Jak funguje ranní aktualizace

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
