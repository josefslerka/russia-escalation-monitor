"""Public forecast evaluation, with separate protocol versions and missingness diagnostics."""
from html import escape as e
from zoneinfo import ZoneInfo

import forecasting as f
import forecast_methods as fm


def content(bundle,data):
    from monitoring import table
    def time(value,compact=False):
        dt=f.instant(value).astimezone(ZoneInfo('Europe/Prague'))
        day=f'{dt.day}. {dt.month}. {dt.year}'; clock=f'{dt:%H:%M} {dt.tzname()}'
        return (f'<time datetime="{e(value,quote=True)}"><span class="forecast-time">{day}</span><br><span class="forecast-time">{clock}</span></time>' if compact else day+' '+clock)
    def score(value):return '—' if value is None else f'{value:.4f}'
    def pct(value):return f'{value*100:g}'.replace('.',',')+' %'
    def links(urls):return ' · '.join(f'<a href="{e(u,quote=True)}">Zdroj</a>' for u in urls)
    def version_days(row):return e(row['protocol'])+'<br>'+str(row['horizon_days'])+' dnů'
    states={'awaiting_issue':'Čeká na vydání','missed':'Nevydáno před začátkem','abstained':'Zdržení se odhadu',
            'open':'Otevřeno','settling':'Čeká na doběh hlášení','awaiting_resolution':'Splatné vyhodnocení',
            'awaiting_final_resolution':'Po konečném termínu — vyžaduje rozhodnutí',
            'yes':'Ano','no':'Ne','unknown':'Neznámé – další kontrola','void':'Nevyhodnotitelné – konečný stav'}
    issued={r['id']:r for r in bundle[f.ROUNDS]}
    source_names={s['id']:s['name'] for s in bundle['sources.json']['sources']}
    questions={q['id']:q for p in fm.protocols(bundle) for q in p['questions']}
    def result(row):
        original=issued.get(row['id'])
        if original is None:return e(states[row['status']])
        detail=f'<p>Vydáno {e(time(original["issued_at"]))}; uzávěrka zdrojů {e(time(original["source_cutoff"]))}.</p><p>{e(original["rationale"])}</p><p>Alternativa: {e(original["alternative"])}</p><p>{links(original["source_urls"])}</p>'
        if original.get('abstention_reason'):
            detail+='<p>Důvod zdržení: '+e(original['abstention_reason'])+'</p>'
        if original.get('estimation_mode'):
            detail+='<p>Režim: '+e(original['estimation_mode'])+'. '+e(original.get('external_influence_note','Vlastní odhad zmrazen před hledáním externího benchmarku.'))+'</p>'
            detail+='<p>Vztah k příbuzným otázkám: '+e(original['related_question_note'])+'</p>'
        if original.get('estimation_passes'):
            raw=original['estimation_passes']
            detail+='<p>Medián samostatných postupů; rozpětí '+e('–'.join(pct(x) for x in original['estimate_spread']))+'. Rozpětí není interval spolehlivosti.</p>'
            detail+='<ul>'+''.join('<li>'+e(p['approach'])+': '+e(pct(p['p']))+' — '+e(p['rationale'])+'</li>' for p in raw)+'</ul>'
            detail+='<p>'+e(original['dependence_note'])+'</p><p>Časový profil: '+e(original['temporal_profile']['shape'])+' — '+e(original['temporal_profile']['rationale'])+'</p>'
        decision=row['outcome']
        if decision:
            detail+='<p>Posouzeno '+e(time(decision['resolved_at']))+': '+e(decision['rationale'])+'</p><p>'+e(decision.get('coverage_basis',''))+'</p><p>'+links(decision['source_urls'])+'</p>'
            if decision.get('date_assignment'):
                detail+='<p>Zdroj uvádí pouze datum. Přiřazení source-day-majority-v2; původní časová neurčitost zachována. Nejde o zjištěnou hodinu události.</p>'
        if row.get('final_adjudication_by'):
            detail+='<p>Konečné rozhodnutí ano / ne / nevyhodnotitelné do '+e(time(row['final_adjudication_by']))+'.</p>'
        for benchmark in bundle.get(fm.BENCHMARKS,[]):
            if benchmark['forecast_id']==row['id'] and f.instant(benchmark['recorded_at'])<=f.instant(data['as_of']):
                detail+='<p>Externí srovnání '+e(benchmark['provider'])+' — '+e(benchmark['status'])+(': '+e(pct(benchmark['p'])) if benchmark['p'] is not None else '')+'. '+e(benchmark['rationale'])+' '+links(benchmark['source_urls'])+'</p>'
        return e(states[row['status']])+'<details><summary>Podklady a posouzení</summary>'+detail+'</details>'
    summaries=[];sensitivities=[];dependence=[]
    for s in data['summaries']:
        summaries.append([version_days(s),f'{s["planned"]} / {s["issued"]}',f'{s["counts"]["yes"]} / {s["counts"]["no"]}',
                          f'{s["counts"]["unknown"]} / {s["counts"]["void"]}',f'{s["matured_resolved"]} / {s["matured_numeric"]}',
                          score(s['matured_brier']),score(s['matured_always_no_brier'])])
        bounds=s['sensitivity'];a=s['abstention_sensitivity']
        sensitivities.append([version_days(s),str(s['matured_numeric']),str(s['matured_unresolved']),
                              score(bounds['best']['brier'])+' / '+score(bounds['worst']['brier']),
                              score(bounds['all_yes']['brier'])+' / '+score(bounds['all_no']['brier']),
                              score(a['brier']['best'])+' / '+score(a['brier']['worst'])+f'<br>{a["abstentions"]} zdržení',
                              str(s['counts']['missed'])+' / '+str(s['counts']['abstained'])])
        dependence.append([version_days(s),str(s['scored']),str(s['dependency_groups']),str(s['distinct_windows']),
                           score(s['brier'])+'<br>všechny dosud rozhodnuté', 'Nelze určit'])
    parts=[f'''<div class="hero"><div><p class="eyebrow">Pevná prognostická okna · {e(time(data['as_of']))}</p><h1>Krátké prognózy a jejich výsledky</h1><p class="lede">Vydané pravděpodobnosti zůstávají uložené se svými pravidly. Nová metodika platí pro další dosud nevydaná okna.</p></div></div>''']
    successor=bundle.get(fm.V2)
    if successor and 'fixed-v2' in data['protocols']:
        parts.append(f'''<div class="archive-notice"><strong>Metodika v2 — záznam změny {e(time(successor['introduced_at']))}.</strong> První nové 7denní okno začíná {e(time(successor['transition']['7']))}, první nové 30denní {e(time(successor['transition']['30']))}. Původních 18 odhadů a jejich pravidla fixed-v1 se nemění. Výsledky obou verzí se vykazují samostatně. <a href="methodology.html#metodika-v2">Změny a přesná pravidla →</a></div>''')
    parts.append('<section class="section"><h2>Výsledky dospělých kohort</h2><p>Kohorta je sada otázek stejné verze, délky a počátku okna. Souhrnné skóre níže počká na konec okna a nejdelší doběh hlášení celé sady. Dříve potvrzené ano zůstává viditelné. Sedm hlavních otázek vstupuje do souhrnu; česká a pobaltská podotázka jsou diagnostické.</p>'+table(['Verze / horizont','Plán / vydáno','Ano / ne','Unknown / void','Dospělé: vyřešeno / odhadů','Brier dospělých','Vždy ne'],summaries)+'<p>Brier = průměr (p − výsledek)², ano = 1 a ne = 0; nižší je lepší. Srovnání „vždy ne“ používá stejné vyřešené otázky. Stálých 50 % má Brier 0,25. Pomlčka znamená chybějící výsledek, nikoli nulové riziko.</p></section>')
    parts.append('<section class="section"><h2>Citlivost na nevyřešené výsledky</h2><p>Po dospění kohorty ukazujeme také meze, které zahrnují každý vydaný číselný odhad s neznámým výsledkem nebo stavem void. Nejlepší a nejhorší možnost se volí pro každý případ zvlášť. „Vše ano“ a „vše ne“ jsou další scénáře, nejsou to obecné krajní meze. Jde o hypotetickou citlivost, nikoli zjištěné výsledky.</p>'+table(['Verze / horizont','Dospělé odhady','Nevyřešené','Nejlepší / nejhorší Brier','Vše ano / vše ne','Se zdržením za 0,5: meze','Nevydáno / zdržení'],sensitivities)+'<p>Ve zvláštní citlivosti dostává zdržení se odhadu hodnotu 0,5 a ztrátu 0,25. Primární skóre se tím nemění. Nevydané odhady zůstávají ve veřejném počtu plánovaných úloh; nedoplňujeme jim smyšlenou pravděpodobnost.</p></section>')
    parts.append('<section class="section"><h2>Počet výsledků a jejich závislost</h2>'+table(['Verze / horizont','Rozhodnuté prognózy','Skupiny závislosti','Různá okna','Průběžný Brier','Efektivní velikost vzorku'],dependence)+'<p>Skupiny nejsou prokázaně nezávislá pozorování. Efektivní velikost vzorku nelze získat násobením počtu skupin a oken. Překrývající se horizonty a různé verze se neslučují. Malý soubor nedokládá kalibraci.</p></section>')
    external=[[version_days(s),e(s['provider']),str(s['n']),score(s['own_brier']),score(s['external_brier'])] for s in data['external_comparisons']]
    parts.append('<section class="section"><h2>Externí srovnání</h2><p>Nejprve se uloží vlastní odhad, potom externí hodnota. Srovnáváme první vyhovující záznam každého poskytovatele na přesně stejné podmnožině vyřešených dospělých případů. Odlišné definice nebo pozdější hodnoty slouží jen jako kontext.</p>'+
                 (table(['Verze / horizont','Poskytovatel','Společné případy','Vlastní Brier','Externí Brier'],external) if external else '<p>Dosud není skórovatelný společný soubor s externím benchmarkem.</p>')+'</section>')
    for protocol in fm.protocols(bundle):
        if protocol['id'] not in data['protocols']:continue
        rows=[]
        for r in data['rows']:
            if r['protocol']!=protocol['id']:continue
            rows.append([e(r['label'])+('<br><small>Diagnostická podotázka</small>' if not r['primary_score'] else ''),
                         str(r['horizon_days'])+' dnů',time(r['window_start'],True)+'<br>→ '+time(r['window_end'],True),
                         'Dosud nevydáno' if r['issued_at'] is None else 'Bez odhadu' if r['p'] is None else pct(r['p']),
                         result(r),time(r['settle_after'],True),score(r['brier'])])
        body=table(['Otázka','Horizont','Pevné okno','Odhad','Stav','Nejdříve ne','Brier případu'],rows) if rows else '<p>V této verzi ještě nebyl vydán žádný odhad. Vydávání se otevírá 24 hodin před začátkem každého okna.</p>'
        parts.append('<section class="section"><h2>Odhady '+e(protocol['id'])+'</h2>'+body+'</section>')
    diagnostics=[]
    for c in data['coherence']:
        diagnostics.append([e(questions[c['question_id']]['label']),pct(c['p7']),pct(c['p30']),pct(c['constant_hazard_p30']),
                            e(c['explanation'] or 'Původní v1 neukládalo strukturovaný časový profil.')])
    if diagnostics:
        parts.append('<section class="section"><h2>Srovnání s konstantním rizikem</h2><p>Hodnota 1 − (1 − P7)^(30/7) je diagnostický model. Odchylka sama neznamená rozpor. U v2 musí být vysvětlen časový profil; logické podmnožiny a vnořené horizonty se kontrolují zvlášť, pouze pro stejnou uzávěrku a odpovídající okna.</p>'+table(['Otázka','P7','P30','P30 při konstantním riziku','Vysvětlení'],diagnostics)+'</section>')
    related=[]
    for c in data['related_forecasts']:
        related.append([e(questions[c['question_id']]['label']),time(c['window_start'],True)+' → '+time(c['window_end'],True),
                        'Bez odhadu' if c['p'] is None else pct(c['p']),e(c['long_definition'])+'<br>Uzávěrka '+e(time(c['long_as_of']))+'; do '+e(time(c['long_window_end'])),
                        pct(c['long_p']),e(c['explanation'] or 'Původní v1 neukládalo zvláštní poznámku k tomuto vztahu. Definice a časová období se liší.')])
    if related:
        parts.append('<section class="section"><details><summary>Související dlouhé a krátké prognózy</summary><p>Porovnání používá poslední dlouhý odhad dostupný při uzávěrce krátkého. Příbuznost neznamená logickou podmnožinu. Zejména dlouhá nátlaková jaderná demonstrace a krátká otázka skutečné neútočné jaderné detonace či zkoušky mají rozdílná kritéria. Otevřená válka může v dlouhé definici vzniknout eskalací omezených incidentů; nejde automaticky o stejnou událost jako větší konvenční útok.</p>'+table(['Krátká otázka','Okno','Krátké p','Původní dlouhá definice','Dlouhé p','Vysvětlení'],related)+'</details></section>')
    question_scores=[]
    for s in data['by_question']:
        q=questions[s['question_id']]
        question_scores.append([e(q['label'])+f'<br>v{q["version"]} · {s["horizon_days"]} dnů',
                                f'{s["planned"]} / {s["issued"]}',f'{s["counts"]["yes"]} / {s["counts"]["no"]}',
                                f'{s["counts"]["unknown"]} / {s["counts"]["void"]}',
                                f'{s["counts"]["missed"]} / {s["counts"]["abstained"]}',score(s['brier']),score(s['matured_brier'])])
    parts.append('<section class="section"><details><summary>Skóre po jednotlivých otázkách a verzích</summary>'+table(['Otázka','Plán / vydáno','Ano / ne','Unknown / void','Nevydáno / zdržení','Průběžný Brier','Brier dospělých'],question_scores)+'</details></section>')
    for protocol in fm.protocols(bundle):
        if protocol['id'] not in data['protocols']:continue
        definitions=[]
        for q in protocol['questions']:
            criteria='<ul>'+''.join('<li>'+e(v)+'</li>' for v in q['criteria'].values())+'</ul>'
            exclusions='<ul>'+''.join('<li>'+e(v)+'</li>' for v in q['exclusions'])+'</ul>'
            groups='<br>'.join('Alespoň '+str(g['min_sources'])+' z '+str(len(g['source_ids']))+': '+e(', '.join(source_names[s] for s in g['source_ids'])) for g in q['source_groups'])
            extra='<br>Konečné rozhodnutí: dalších 14 dní po doběhu, pak ano / ne / void.' if protocol['id']=='fixed-v2' else '<br>V1 nemělo konečný termín unknown; pravidlo zpětně nedoplňujeme.'
            definitions.append([e(q['label']),e(q['definition'])+criteria+'<details><summary>Výluky</summary>'+exclusions+'</details>',
                                'První kvalifikující zveřejnění' if q['time_basis']=='publication' else 'Skutečná událost',
                                str(q['settlement_delay_hours'])+' hodin'+extra+'<br>'+groups])
        parts.append('<section class="section"><details><summary>Definice a pravidla '+e(protocol['id'])+'</summary>'+table(['Otázka','Podmínky ano','Rozhodný čas','Doběh a povinné zdroje'],definitions)+'</details></section>')
    changes=''.join('<li>'+e(r['forecast_id'])+' · '+e(r['correction_reason_class'])+' · '+e(r['correction_note'])+' '+links(r['source_urls'])+'</li>' for r in data['corrections'])
    parts.append('<section class="section" id="opravy"><h2>Opravy konečných závěrů</h2>'+('<ul>'+changes+'</ul>' if changes else '<p>Dosud nejsou zaznamenány opravy konečného ano/ne podle nové politiky.</p>')+'<p>Oprava se připojuje s důvodem a odkazem na předchozí rozhodnutí. Původní záznam zůstává dostupný; nevzniká tím další nezávislý vzorek.</p></section>')
    parts.append('''<section class="section"><h2>Časová neurčitost a konečný stav</h2><p>V1 vyžaduje celý nejistý čas uvnitř okna. Datum na hraničním dni proto může zůstat nerozhodnutelné; tento limit zveřejňujeme a staré výsledky nepřiřazujeme podle nové konvence. V2 přiřadí celý kalendářní den zdroje oknu s největším časovým překryvem, při shodě pozdějšímu. Původní datum, jeho časové pásmo a neurčitost zůstávají uložené. Známý přesný čas má přednost.</p><p>Unknown je průběžná nejistota. Void ve v2 je konečný nevyhodnotitelný výsledek s důvodem po předepsaném termínu; do Brierova skóre se nemění na nulu. Zmeškané konečné rozhodnutí zůstane viditelně po termínu. Nový důkaz může vyvolat výslovnou opravu.</p><p>Před výsledkem ne se nově porovnává seznam otevřených tvrzení s případy a evidencí. Potenciální kandidát potřebuje posouzení vůči konkrétním kritériím otázky; obecné uzavření vyšetřování nestačí. Relevantní nález použitý v záporném auditu musí mít vysvětlení, proč nevyhověl.</p></section>''')
    parts.append('<p><a href="data/forecast-protocol.json">Pravidla v1</a> · <a href="data/forecast-protocol-v2.json">Pravidla v2</a> · <a href="data/forecast-review-policy.json">Politika kontroly výsledků</a> · <a href="data/forecast-rounds.jsonl">Neměnná vydání</a> · <a href="data/forecast-outcomes.jsonl">Výsledky a opravy</a> · <a href="data/forecast-candidate-reviews.jsonl">Posouzení kandidátů</a> · <a href="data/forecast-benchmarks.jsonl">Externí srovnání</a> · <a href="data/fixed-evaluation.json">Výpočty</a></p>')
    return '\n'.join(parts)
