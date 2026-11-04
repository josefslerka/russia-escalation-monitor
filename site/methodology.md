# Metodika předpovědi

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

## Mapa a geografické údaje

[Mapa a signály](signals.html) propojuje úplnou uloženou evidenci s mapou, časovou osou a filtry. Čísla označují záznamy evidence, nikoli počet útoků, nezávislých potvrzení nebo velikost hrozby. Zahrnují také opravy, aktualizace, plánované kroky a důkazy proti eskalaci. Směr signálu přebíráme z původního záznamu; sám neznamená změnu pravděpodobnosti.

Geografické anotace jsou uloženy [samostatně](data/geography.json) pod stálými ID důkazů. Ruční klasifikace označuje geografický předmět záznamu na úrovni zemí nebo regionů. Není novým důkazem, automatickou ruskou atribucí ani ověřenou souřadnicí incidentu. Sídlo zpravodajské služby či média neurčuje místo varovaného útoku. Obecná varování pro NATO nebo EU nerozdělujeme mezi jednotlivé státy. Výlučnou ekonomickou zónu nepovažujeme za teritoriální vody; neurčené námořní případy zůstávají u mořského regionu.

Záznam může zahrnovat několik zemí: započítá se jednou v seznamu a jednou u každé přiřazené země. Součet čísel v mapě proto nemusí odpovídat počtu záznamů. Regionální a neurčené údaje se neumisťují do smyšleného bodu; stránka uvádí jejich počet zvlášť. Chybějící nová anotace zůstane označena jako neurčená geografie. Kartografické hranice jsou orientační; mapový podklad pochází z [Natural Earth](https://www.naturalearthdata.com/) prostřednictvím [d3-maps atlas](https://github.com/d3-maps/atlas).

Časová osa odděluje událost či plán, zveřejnění a zařazení do monitoru. Časové značky s pásmem převádíme na kalendářní den Europe/Prague; původní údaj zůstává v detailu. Intervaly filtrujeme podle překryvu, do sloupců je řadíme jednou podle začátku. Měsíční přesnost nevytváří domnělý den: v denním či týdenním zobrazení ji uvádíme mimo sloupce. Nejednoznačné popisy a rozporné termíny zůstávají neurčené. Jejich zahrnutí do seznamu lze zapnout zvlášť. Datum události označuje předmět daného záznamu, který může být například novým závěrem vyšetřování staršího útoku; původní formulace je vždy dostupná v detailu.

Mapová stránka používá stejné datum uzávěrky jako poslední skutečně dokončená rešerše. Doplnění geografie ani změna vzhledu nevytváří nové analytické hodnocení a nemění archivní zprávy či snímky.

## Pokrytí a stáří podkladů

[Pokrytí](coverage.html) má vlastní protokol kontrol. Plán obsahuje všech 36 zemí
EU nebo NATO, ale zápis zdroje do registru neznamená, že byl přečten. Denně se
kontrolují naléhavé případy a prioritní novinky, týdně rotující hloubkové audity
zemí a měsíčně mezery zdrojů. Provedená kontrola uvádí zdroj, období, rozsah,
výsledek a omezení. Stav „bez strukturované kontroly“ označuje chybějící nový
auditní záznam, nevymazává starší rešerše popsané v archivních zprávách.

Mapa nabízí samostatný pohled **Pokrytí zdrojů**. Barvy nejsou stupně nebezpečí.
Kontrola staršího dokumentu je jen část pokrytí; úplný audit zahrnuje oficiální
hodnocení, incidenty, připravenost a politické či společenské účinky. Časové a
tematické filtry evidence se na pohled pokrytí nevztahují. Nedostupnost zdroje
ani neúspěšné hledání není důkazem absence hrozby. V interaktivní mapě stáří
poslední úspěšné kontroly průběžně stárne i bez nové publikace.

Datum předpovědi, datum kontroly a datum pozorované události jsou tři různé údaje.
Roční a měsíční časová přesnost se zachovává; roční údaje se nepřevádějí na
domnělý lednový incident v časovém grafu. Částečně provedený plán zůstává označen
jako částečný. Nově doplněné starší podklady mají dnešní datum dohledání a původní
datum publikace; jejich dopad na prognózu čeká na výslovnou analytickou revizi.

## Události, zdrojové linie a následné kontroly

[Přehled kvality](quality.html) propojuje záznamy k událostem nebo hodnocením a
odlišuje první zprávu, nezávislé potvrzení, další vývoj, atribuci, vyvrácení,
opravu a překryv tvrzení. Shodná URL je podnět k ruční kontrole; živý index může
obsahovat různé události. Počet zdrojových rodin u případu není počet nezávislých
potvrzení každé jeho části. Záchrana posádky například nepotvrzuje původce útoku.

Dva záznamy výročního hodnocení BIS z 27. srpna jsou zachovány, ale sdílejí jednu
zdrojovou rodinu. Oprava netvrdí, že dřívější pravděpodobnost byla dvakrát navýšena.
Nerevidované záznamy jsou viditelné jako nepřiřazené; počet propojených případů
proto zatím není úplný počet událostí. U otevřených případů zůstává původní termín
kontroly v historii a neúspěšné načtení nemůže případ uzavřít.

Negativní zjištění vyžaduje pozorovatelný očekávaný projev, zdrojově doložený běžný
stav a dostatečný rozsah skutečně provedené kontroly. Neznámý stav se nenahrazuje
závěrem „nic se nestalo“. Cvičení, počasí, sezónnost a změny monitorovacího systému
jsou samostatná alternativní vysvětlení.

## Měření účinků a metodický zlom WDPI

[Dopady](society.html) rozlišují slib, závazek, dodávku, platbu a pozorované chování.
U průzkumů uchováváme otázku, terénní období, velikost a složení vzorku i způsob
sběru; rozdílné otázky nespojujeme do jedné řady. Členství v NATO, podpora konkrétní
pomoci a ochota nést náklady jsou odlišné postoje. České společenské odolnosti
nepřidělujeme nepodložené celkové skóre.

Pro další plnou rekalibraci je připravena metoda **WDPI anchored-v2** s kotvami
0, 25, 50, 75 a 100 pro každou komponentu a zachovanými váhami 35/35/30.
[Definice a kotvy](data/metrics.json) uvádějí, jaké chování musí být doloženo.
Analytik zvolí nejvyšší plně podloženou kotvu a odkáže konkrétní pozorování.
Výpočet používá zaokrouhlení poloviny nahoru. Chybí-li komponenta, nový index se
nevyčíslí; nula také vyžaduje důkazy. Dosavadní hodnoty zůstávají původní metodou.
První použití v2 musí být označeno jako metodický zlom v nové zprávě, ne jako
historický přepočet. Ruská příčinná účast se vyhodnocuje samostatně.

## Vyhodnocování předpovědí

Od **31. října 2026** používáme [pevná 7denní a 30denní okna](forecasts.html).
Každé vydání musí být uloženo před začátkem období; obě meze se při dalších
denních zprávách nemění. Zmeškaný termín zůstává zobrazený jako nevydaná prognóza.
Počítáme uplynulé dny v UTC, takže délku okna nemění přechod na letní čas.

[Protokol](data/forecast-protocol.json) uchovává devět konkrétních definic,
podmínky naplnění, výluky, potřebnou sílu zdrojů a dobu na doběh hlášení.
U oznámení sabotáže předpovídáme první kvalifikující oficiální zveřejnění v
přesně uvedeném panelu; datum skutečného incidentu zůstává zvlášť. U ozbrojeného
útoku, vstupu Běloruska a jaderné události rozhoduje skutečný čas události.
Úmyslné použití zbraně se škodou je ověřitelnější otázka než domněnka o cíli
„otestovat soudržnost NATO“. Nová mobilizační otázka se týká zveřejněného
závazného příkazu pro nejméně 100 000 osob. Nové definice se nepoužívají zpětně
ke skórování starých procent.

„Ne“ vyžaduje skončené okno, 3 nebo 7 dnů na doběh hlášení a úspěšný audit celého
období všech předepsaných zdrojových skupin. Částečná rešerše či neuzavřená
atribuce znamená neznámý výsledek s termínem další kontroly. Časově neurčitý
případ nelze zařadit do okna pomocí vymyšlené hodiny. „Ano“ může být doloženo
už během období. Každé kritérium musí mít konkrétní podklad a případ vlastní
provenienci. Pozdější opravy zachovávají předchozí rozhodnutí.

[Vydané odhady](data/forecast-rounds.jsonl) i [výsledky](data/forecast-outcomes.jsonl)
jsou neměnné protokoly. Skóre ukazujeme zvlášť pro 7 a 30 dnů a pro jednotlivé
otázky; celkový počet zahrnuje i chybějící vydání a nevyhodnocené výsledky.
Česká sabotážní a pobaltská podotázka jsou diagnostické a nezvyšují souhrnný
počet skórovaných hlavních otázek. Další závislosti mezi událostmi přetrvávají.

Brier je průměr **(p − výsledek)²**. Na stejném souboru uzavřených výsledků
ukazujeme i předem zvolenou strategii „vždy nenastane“ a stálých 50 %.
U vzácných událostí samotné velké množství správných záporných výsledků
nedokládá prognostickou schopnost. Neznámé výsledky se nenahrazují nulou a
**1 − Brier není procento přesnosti**. Skóre z malého či provázaného souboru
neprokazuje statistickou kalibraci.

Původní dlouhé prognózy jsou vedeny samostatně. Při další aktualizaci si
zachovají původní začátek z registru; starší již uložená vydání se nepřepisují.

[Registr](data/forecast-register.jsonl) uchovává neměnnou definici, kritéria,
pravděpodobnost a obě meze časového okna. Výsledek je ano, ne nebo neznámý;
„ne“ vyžaduje skončený horizont a dostatečné pozorování, „ano“ událost ve
zmrazeném okně. Pozdější oprava adjudikace odkazuje původní rozhodnutí.

Brier skóre je průměr **(p − výsledek)²**, kde ano = 1 a ne = 0; nižší hodnota
je lepší. Počítáme jen první způsobilou registraci každé kohorty otázka × verze
definice × konec horizontu. Denní revize stejné otázky nezvětšují počet vzorků.
Neznámé výsledky a zpětně importované již vyřešené otázky jsou vyloučeny.
Překrývající se otázky navíc nejsou nezávislé konflikty. Z malého souboru výsledků
nelze prohlašovat model za kalibrovaný.

## Změna metodiky 4. listopadu 2026 — fixed-v2

Metodický audit vedl k nové [verzi pravidel](data/forecast-protocol-v2.json)
a [politice kontroly výsledků](data/forecast-review-policy.json).
**Původních 18 vydání fixed-v1, jejich procenta, okna, definice i dosavadní
rozhodnutí zůstávají zachována.** V1 a v2 se vykazují samostatně.
Změna metodiky není novou analytickou zprávou: uzávěrka posledního odhadu
zůstává 4. listopadu v 08:16 CET.

První 7denní okno v2 začíná **7. listopadu 2026 v 08:00 CET**, první 30denní
**30. listopadu v 08:00 CET**. Vydávání se otevírá 24 hodin předem. Nová okna
navazují na původní UTC rozvrh; již běžící období se neposouvají.

### Datum známé pouze dnem

Přesný čas se nadále posuzuje podle intervalu **(začátek, konec]**. Známe-li
jen datum, v2 přiřadí **celý kalendářní den v časovém pásmu zdroje** tomu oknu,
s nímž má největší časový překryv; při přesné shodě pozdějšímu oknu. Uchováváme
původní datum, pásmo i celý interval nejistoty. Jde o předem zvolenou klasifikaci,
nikoli zjištění hodiny události. Známý přesný čas nelze nahradit pouhým datem.
Neznámé pásmo nevyplňujeme odhadem. Hranice o půlnoci by sama problém neřešila:
celý den začíná přesně na dolní, otevřené mezi a zdroj může mít jiné pásmo.

Ve v1 musí celý nejistý interval ležet uvnitř okna. Hraniční den proto může
zůstat nevyhodnotitelný v obou sousedních obdobích. Tuto slabinu zveřejňujeme;
novou konvencí nepřiřazujeme staré výsledky. Starý kontrolní toleranční posun
14 hodin při porovnávání dne incidentu se zveřejněním pokrývá možné rozdíly
kalendářního dne mezi časovými pásmy. Neopravňuje k posunu události do okna
a není tolerancí pro samotné splnění prognózy.

### Kdy výsledek uzavřeme

V2 má konečný termín **14 dní po původním 72hodinovém či 168hodinovém doběhu
hlášení**. Do něj může být výsledek průběžně unknown; potom musí následovat
ano, ne nebo **void — konečně nevyhodnotitelné**, s důvodem a doloženou závěrečnou
kontrolou. Chybějící rozhodnutí po termínu zůstává viditelně po termínu a vrací
se do pracovní fronty. Samotné uplynutí času nevytvoří „ne“.
V1 nový konečný termín ani stav void zpětně nedostává.

Při novém záporném rozhodnutí se seznam otevřených tvrzení porovnává s případy
a časově relevantní evidencí. Kandidát potřebuje posouzení vůči konkrétní otázce
a jejím původním kritériím. Obecně uzavřené vyšetřování nestačí. Relevantní nález
použitý při auditu pro „ne“ musí mít doložené vysvětlení, proč nevyhovuje.
Tato kontrola zpřesňuje dokládání již platných pravidel i u dosud otevřených v1;
jejich definice a časové podmínky nemění.

Opravy konečného ano/ne dostanou výslovnou kategorii příčiny: nový důkaz,
oprava zdroje, věcná chyba nebo chyba posouzení. Připojí se nový záznam s odkazem
na předchozí; původní rozhodnutí se nemaže. Historie oprav je veřejná.

### Co vstupuje do skóre

Skóre jednotlivého rozhodnutého případu a původní průběžný Brier zůstávají
dohledatelné. Hlavní souhrn navíc čeká na **dospění celé kohorty**: sady hlavních
otázek se stejnou verzí, délkou a počátkem okna, včetně nejdelšího doběhu hlášení.
Tím dřívější potvrzená „ano“ nepředbíhají ve hlavním souhrnu pozdější „ne“.
Ani dospění sady nezaručuje vyřešení všech otázek; vedle skóre vždy ukazujeme
počet vyřešených, nevyřešených, nevydaných odhadů a zdržení se odhadu.

Pro všechny vydané číselné odhady v dospělých kohortách počítáme citlivost:
všechny unknown/void jako ano, všechny jako ne a také skutečné nejlepší
a nejhorší možné Brierovo skóre, **volené pro každý nevyřešený případ zvlášť**.
Scénáře „vše ano“ a „vše ne“ nejsou obecně krajní meze. Jde o hypotetické
výsledky, nikoli náhradu chybějícího pozorování. Ve zvláštní citlivosti
hodnotíme zdržení se odhadu jako p = 0,5 se ztrátou 0,25; primární skóre se
nemění. Nevydanému odhadu pravděpodobnost nedoplňujeme.

Počet smluv, skupin závislosti a různých oken ukazujeme zvlášť. Skupiny nejsou
prokázaně nezávislé a jejich násobení počtem oken **nedává efektivní velikost
vzorku**. Tu zatím neodhadujeme. Verze ani 7denní a 30denní výsledky neslučujeme.

### Jak vzniknou nová procenta

Číselný odhad v2 musí obsahovat **3–5 samostatně zaznamenaných postupů**:
referenční třídu, současné indikátory a alternativní scénář. U referenční třídy
uvedeme měřený počet případů a zdroje, nebo výslovně přiznáme, že spolehlivá
základní četnost chybí. Publikované p je medián původních hodnot; viditelné je
i jejich minimum a maximum. Rozpětí není interval spolehlivosti a stejné zdroje
či model z těchto postupů nedělají nezávislé prognostiky.

Vlastní číslo se nejprve uloží. Až potom hledáme srovnatelný externí odhad.
Srovnávací benchmark potřebuje shodné definice i obě meze okna, záznam před
začátkem okna a nejvýše hodinu po vlastním vydání. Jinak jde pouze o kontext;
nenalezený benchmark se přizná. Režim blind/informed a případný vliv dříve
viděných externích hodnot jsou výslovně uvedeny. Lokální čas vydání není
nezávislé časové razítko; veřejnou stopou jsou commity a nasazení webu.

Kontrolujeme logické vztahy, například pobaltský ozbrojený útok ≤ útok na NATO
při stejném okně a uzávěrce. Hodnota **1 − (1 − P7)^(30/7)** slouží pouze jako
srovnání s konstantním rizikem. P7 = 55 % a P30 = 80 % není logický rozpor:
znamená 55 % v prvním týdnu, dalších 25 % ve zbytku měsíce a 20 % bez události.
V2 ukládá vysvětlení časového profilu. Různě definované dlouhé a krátké otázky
se mechanicky nepřepočítávají. Kalibrační korekci z voleb na geopolitické
události nepřenášíme; případná budoucí kalibrace vyžaduje vlastní výsledky.

Energetická otázka v2 nyní předpovídá **potvrzení skutečně zavedených nouzových
omezení po ruských útocích přímo Ukrenergem**, bez podmínky tří jmenovaných
oblastí. [Primární zprávy Ukrenerga](https://t.me/s/Ukrenergo) takové skutečné
zavedení popisují i bez seznamu oblastí. Plánovaná či běžná harmonogramová omezení
nestačí. Jde o novou otázku; původní přísnější v1 se podle ní nevyhodnocuje.

### Dlouhé prognózy a čas

Od dalšího analytického běhu se změna dlouhého p rozloží na **časovou složku
a složku nových důkazů**. Každá má důvod; součet musí reprodukovat nové p.
Konstantní riziko je volitelný model, použitelný jen tehdy, když je nenastání
dostatečně pozorovatelné a skutečně ověřené. Jinak se časová složka neaplikuje
a uvede se důvod. „Beze změny důkazů“ tedy samo neurčuje časovou složku.

Před další revizí se konkrétní kandidátní případy porovnají s původní definicí
a původním začátkem dlouhého okna. Samotná přítomnost říjnové sabotáže v evidenci
neříká, že nastala po 28. říjnu nebo splnila všechna kritéria. Nástroj nabízí
kandidáty, nikoli automaticky kladné výsledky. Denní revize zůstávají v historii,
ale do skóre vstupuje jen první způsobilá registrace otázky a verze.

Starší konvenční otázky už probíhaly nebo byly naplněné před způsobilou
registrací; do prospektivního skóre nepatří. Původní mobilizační otázka v1
(60 %) byla nahrazena jinou definicí v2 (20 %) a zůstává **neskórovanou historickou
prognózou**, nikoli opraveným odhadem stejné události. Nezměněné archivní zprávy
a snímky uchovávají i tyto starší hodnoty.
