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
