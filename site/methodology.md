# Odhad, který se dá zkontrolovat

Monitor eskalace je průběžný analytický projekt Josefa Šlerky s podporou AI. Sleduje ruskou eskalaci a její dopady na Ukrajinu, EU, NATO, Pobaltí, Bělorusko a Česko. Každý běh vychází z předchozího uloženého stavu a aktualizuje jen otázky, kterých se nové důkazy skutečně týkají.

## Co znamenají procenta

Jde o úsudkové pravděpodobnosti konkrétních událostí v uvedeném časovém horizontu. Pásma vyjadřují analytickou nejistotu, nikoli statistické intervaly spolehlivosti. Události se překrývají, proto se jejich pravděpodobnosti nesčítají do 100 %. Nejde o statisticky kalibrovaný model s prokázanou úspěšností.

Každá zpráva uvádí svůj prior, nový odhad, změnu, důvěru, podklady pro eskalaci i proti ní a pozorovatelné indikátory, které by vedly ke změně názoru. Pravděpodobnost se nemusí změnit při každém běhu. Uzavřené otázky zůstávají v historii; nezobrazují se jako budoucí rizika.

## Jak pracujeme se zdroji

- **Confirmed — potvrzené:** primární zdroj nebo silné nezávislé doložení. Potvrzení výroku úředníka nemusí znamenat potvrzení pravdivosti jeho neveřejného zpravodajského podkladu.
- **Reported — reportované:** informace kvalitního média, jejíž podklad není veřejný.
- **Unverified claim — neověřené tvrzení:** sociální sítě či nedostatečně doložená jednotlivá zpráva.
- **Analytical inference — analytický úsudek:** závěr odvozený z podkladů.
- **Scenario — scénář:** možný budoucí vývoj.

Přetisky jedné agenturní zprávy netvoří několik nezávislých potvrzení. Rozlišujeme čas události, zveřejnění a vlastního dohledání. Telegram slouží především k hledání prvních stop a primárních prohlášení. Schopnost něco provést sama neprokazuje rozhodnutí ani bezprostřední přípravu.

## Stupeň varování

- **GREEN:** aktivita poblíž výchozí úrovně, bez důvěryhodné přípravy významného scénáře.
- **YELLOW:** zvýšené riziko či varování, ale bez souběhu záměru, připravenosti, logistiky a účinku.
- **ORANGE:** nejméně dvě nezávislé vrstvy důkazů, včetně připravenosti či účinku, podporují závažný scénář.
- **RED:** silná konvergence ukazuje bezprostřední nebo již probíhající závažnou eskalaci se strategickými účinky.

Stupeň je kvalitativní syntéza. ORANGE sám o sobě neznamená, že hrozí bezprostřední válka NATO s Ruskem; konkrétní důvod musí být uveden ve zprávě.

## Tlak na západní rozhodování

WDPI měří konkurenci o zdroje, domácí náklady a sebeodstrašení. Výpočet je `round(0,35 × zdroje + 0,35 × domácí náklady + 0,30 × sebeodstrašení)`. Komponenty jsou analytická skóre 0–100 ukotvená v důkazech. WDPI není pravděpodobnost a neprokazuje ruské autorství každého tlaku.

Ruské úsilí se hodnotí odděleně jako RPE. Číslo se publikuje pouze s reprodukovatelnou metodou; jinak zůstává kvalitativní. Ruský vliv a skutečná změna západního chování se nesmějí zaměňovat.

## Archiv a opravy

Každá zpráva má trvalou adresu s datem a časem. Původní texty zůstávají dohledatelné; pozdější opravy jsou vysvětlené v novějších zprávách. Některé nejstarší texty obsahují souhrnná skóre, která dnešní metodika už nepřebírá. Graf vývoje nevytváříme z nesrovnatelných nebo chybějících historických stavů.

Od zavedení automatického publikování se ukládá také samostatný JSON snímek každého stavu. Starší úplné stavy zpětně nevymýšlíme. Veřejné kopie zpráv převádějí místní odkazy na odkazy v archivu; analytický obsah tím nemění.

[Aktuální stav](data/state.json), [evidence](data/evidence.jsonl) a [watchlist](data/watchlist.json) jsou dostupné ke stažení. Úplná pracovní pravidla a verzování jsou v [repozitáři projektu](https://github.com/josefslerka/russia-escalation-monitor).

## Aktualizace

Ranní rešerše je plánována na 7:00 v časovém pásmu Europe/Prague v místním Codexu. Dokončení a zveřejnění následuje po rešerši a kontrole. Počítač i aplikace musejí běžet a mít přístup k síti. Datum uzávěrky na webu vždy ukazuje poslední skutečně dokončené hodnocení.

Při selhání zůstává dostupná předchozí zpráva. Starý obsah se neoznačuje novým datem. Web upozorní, pokud je poslední hodnocení starší než 48 hodin.
