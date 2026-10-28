/* Linked map, timeline and evidence list. Data are generated from the saved ledger. */
(() => {
  'use strict';
  const root = document.getElementById('signals-app');
  if (!root) return;
  const loading = root.querySelector('.signals-loading');
  const html = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const day = value => value ? `${Number(value.slice(8, 10))}. ${Number(value.slice(5, 7))}. ${value.slice(0, 4)}` : 'Neurčeno';
  const sourceLink = (url, label) => url && /^https?:\/\//.test(url) ? `<a href="${html(url)}" target="_blank" rel="noopener noreferrer">${html(label)} ↗</a>` : '';

  async function start() {
    if (!window.d3 || !window.EscalationSignals) throw new Error('Mapová knihovna se nenačetla.');
    const responses = await Promise.all([fetch(root.dataset.signalsSource), fetch(root.dataset.signalsMap)]);
    if (responses.some(response => !response.ok)) throw new Error('Data mapy nejsou dostupná.');
    const [data, world] = await Promise.all(responses.map(response => response.json()));
    const core = window.EscalationSignals;
    const monitoring = data.monitoring || { countries: {}, states: {}, events: [] };
    const coverageColors = { checked: '#5e9eaf', partial: '#ebcd92', unavailable: '#cfb8ce', stale: '#d6b9a8', not_checked: '#e5e4df' };
    const coverageStatus = country => core.coverageState(country, new Date().toISOString());
    const controls = [...root.querySelectorAll('.signals-controls select, .signals-controls input')];
    const size = 8;
    const ids = new Set(data.records.map(record => record.id));
    const basisNames = { publication: 'zveřejnění', event: 'událostí a plánů', discovery: 'zařazení do monitoru' };
    const defaults = () => ({ area: 'all', topic: 'all', status: 'all', direction: 'all', basis: 'publication', from: data.default_from, to: data.default_to, undated: false, record: null, page: 0, view: 'europe', mode: 'evidence' });
    let state;
    let filtered = [];

    function readQuery() {
      const params = new URLSearchParams(location.search);
      const result = defaults();
      for (const [key, allowed] of Object.entries({
        area: ['all', 'unknown', 'baltics_all', ...Object.keys(data.areas)],
        topic: ['all', ...Object.keys(data.topics)], status: ['all', ...Object.keys(data.statuses)],
        direction: ['all', ...Object.keys(data.directions)], basis: Object.keys(basisNames), view: ['europe', 'world'], mode: ['evidence', 'coverage']
      })) if (allowed.includes(params.get(key))) result[key] = params.get(key);
      for (const key of ['from', 'to']) {
        const value = params.get(key);
        if (value === '' || (core.validDay(value) && value >= data.minimum_date && value <= data.maximum_date)) result[key] = value;
      }
      if (result.from && result.to && result.from > result.to) [result.from, result.to] = [result.to, result.from];
      result.undated = params.get('undated') === '1';
      if (ids.has(params.get('record'))) result.record = params.get('record');
      const page = Number(params.get('page'));
      if (Number.isSafeInteger(page) && page >= 0) result.page = page;
      if (result.record && !params.has('from') && !params.has('to')) {
        const time = data.records.find(record => record.id === result.record).times[result.basis];
        if (time.start) {
          result.from = time.start < result.from ? time.start : result.from;
          result.to = time.end > result.to ? time.end : result.to;
        } else result.undated = true;
      }
      if (result.record && !params.has('page')) {
        const index = core.filterRecords(data.records, result).findIndex(record => record.id === result.record);
        if (index >= 0) result.page = Math.floor(index / size);
      }
      return result;
    }
    function saveQuery() {
      const params = new URLSearchParams();
      for (const key of ['area', 'topic', 'status', 'direction', 'basis', 'view', 'mode']) if (state[key] !== defaults()[key]) params.set(key, state[key]);
      params.set('from', state.from); params.set('to', state.to);
      if (state.undated) params.set('undated', '1');
      if (state.record) params.set('record', state.record);
      if (state.page) params.set('page', state.page);
      history.replaceState(null, '', `${location.pathname}?${params}${location.hash}`);
    }
    function timeLabel(time) {
      if (!time.start) return time.raw || 'Datum neurčeno';
      const range = `${day(time.start)}${time.end !== time.start ? ' – ' + day(time.end) : ''}`;
      return `${range}${time.precision === 'year' ? ' · přesnost na rok' : time.precision === 'month' ? ' · přesnost na měsíc' : ''}${time.planned ? ' · plán' : ''}`;
    }
    function chooseArea(area) {
      state.area = state.area === area ? 'all' : area;
      state.page = 0; state.record = null;
      render(); saveQuery();
    }
    function chooseRecord(id) {
      state.record = id; render(); saveQuery();
    }
    function drawMap() {
      const coverage = state.mode === 'coverage';
      const svg = d3.select(root.querySelector('.signals-map'));
      const width = svg.node().getBoundingClientRect().width;
      if (!width) return;
      const height = parseFloat(getComputedStyle(svg.node()).height);
      svg.attr('viewBox', `0 0 ${width} ${height}`).selectAll('*').remove();
      svg.append('title').text(coverage ? 'Rozsah kontroly zdrojů podle zemí. Barva označuje pokrytí rešerše, nikoli bezpečnost země.' : 'Přiřazení záznamů evidence k zemím; regionální a neurčené údaje nejsou rozdělovány mezi státy.');
      const projection = state.view === 'world' ?
        d3.geoNaturalEarth1().fitExtent([[12, 12], [width - 12, height - 12]], { type: 'Sphere' }) :
        d3.geoMercator().fitExtent([[12, 14], [width - 12, height - 14]], { type: 'MultiPoint', coordinates: [[-8, 42], [48, 64]] });
      projection.clipExtent([[0, 0], [width, height]]);
      const path = d3.geoPath(projection);
      const counts = coverage ? new Map(Object.keys(monitoring.countries).map(id => [id, 0])) : core.countryCounts(filtered, data.areas);
      const group = svg.append('g');
      group.append('path').datum(d3.geoGraticule().step(state.view === 'world' ? [30, 30] : [10, 10])()).attr('class', 'signals-graticule').attr('aria-hidden', 'true').attr('d', path);
      const paths = group.selectAll('.signals-country').data(world.features).join('path').attr('d', path)
        .attr('aria-hidden', 'true')
        .attr('class', feature => `signals-country${counts.has(feature.properties.id) ? ' has-evidence' : ''}${state.area === feature.properties.id ? ' is-selected' : ''}`)
        .style('fill', feature => coverage && monitoring.countries[feature.properties.id] ? coverageColors[coverageStatus(monitoring.countries[feature.properties.id])] : null);
      paths.append('title').text(feature => `${data.areas[feature.properties.id]?.label || feature.properties.name}: ${coverage ? monitoring.countries[feature.properties.id] ? monitoring.states[coverageStatus(monitoring.countries[feature.properties.id])] : 'Mimo plán zemí EU/NATO' : 'záznamy ve výběru ' + (counts.get(feature.properties.id) || 0)}`);
      paths.filter(feature => data.areas[feature.properties.id]?.kind === 'country').on('click', (_, feature) => chooseArea(feature.properties.id)).classed('is-interactive', true);
      const visible = new Set();
      const occupied = [];
      let suppressed = 0;
      const priority = id => id === state.area ? 100 : ['EST', 'LVA', 'LTU'].includes(id) && state.view === 'europe' ? 50 : 0;
      const features = world.features.filter(feature => counts.has(feature.properties.id)).sort((a, b) =>
        priority(b.properties.id) - priority(a.properties.id) || counts.get(b.properties.id) - counts.get(a.properties.id));
      for (const feature of features) {
        const [x, y] = path.centroid(feature);
        if (!Number.isFinite(x) || !Number.isFinite(y) || x < 8 || y < 8 || x > width - 8 || y > height - 8) continue;
        const id = feature.properties.id;
        visible.add(id);
        const narrowBaltic = width < 500 && state.view === 'europe' && ['EST', 'LVA', 'LTU'].includes(id);
        const offset = narrowBaltic ? { EST: [-32, -18], LVA: [-32, 1], LTU: [-32, 22] }[id] : [0, 0];
        const px = x + offset[0], py = y + offset[1];
        const leader = narrowBaltic ? group.append('line').attr('x1', x).attr('y1', y).attr('x2', px).attr('y2', py).attr('class', 'signals-map-leader') : null;
        const marker = group.append('g').attr('transform', `translate(${px},${py})`).attr('class', 'signals-map-marker')
          .attr('role', 'button').attr('tabindex', 0).attr('aria-label', `${data.areas[id].label}: ${coverage ? monitoring.states[coverageStatus(monitoring.countries[id])] : counts.get(id) + ' záznamů'}. Vybrat zemi.`)
          .on('click', event => { event.stopPropagation(); chooseArea(id); })
          .on('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); chooseArea(id); } });
        marker.append('circle').attr('r', 11).attr('class', 'signals-count').style('fill', coverage ? coverageColors[coverageStatus(monitoring.countries[id])] : null).style('stroke', coverage ? '#566364' : null);
        marker.append('text').attr('class', 'signals-count-value').attr('text-anchor', 'middle').attr('dy', '.35em').style('fill', coverage ? '#172728' : null).text(coverage ? ({checked: '✓', partial: '◐', unavailable: '×', stale: '!', not_checked: '?'})[coverageStatus(monitoring.countries[id])] : counts.get(id));
        if (state.view === 'world') marker.append('text').attr('class', 'signals-map-name').attr('text-anchor', 'middle').attr('y', 25).text(id);
        else {
          const desktopBaltic = !narrowBaltic && ['EST', 'LVA', 'LTU'].includes(id);
          const nameX = narrowBaltic ? -16 : desktopBaltic ? 24 : 0;
          const nameY = narrowBaltic ? 4 : desktopBaltic ? 4 : 27;
          if (desktopBaltic) marker.append('line').attr('x1', 12).attr('y1', 0).attr('x2', 21).attr('y2', 0).attr('class', 'signals-map-leader');
          if (width >= 500 || !['BLR', 'DEU', 'ROU', 'BGR', 'CZE', 'DNK'].includes(id)) marker.append('text')
            .attr('class', 'signals-map-name').attr('x', nameX).attr('y', nameY)
            .attr('text-anchor', narrowBaltic ? 'end' : desktopBaltic ? 'start' : 'middle').text(data.areas[id].label);
        }
        const bounds = () => { const box = marker.node().getBBox(); return { x: px + box.x, y: py + box.y, width: box.width, height: box.height }; };
        const collides = box => box.x < 2 || box.y < 2 || box.x + box.width > width - 2 || box.y + box.height > height - 2 || occupied.some(other =>
          box.x < other.x + other.width + 3 && box.x + box.width + 3 > other.x && box.y < other.y + other.height + 3 && box.y + box.height + 3 > other.y);
        let box = bounds();
        if (collides(box)) { marker.select('.signals-map-name').remove(); box = bounds(); }
        if (collides(box)) { marker.remove(); leader?.remove(); suppressed++; }
        else occupied.push(box);
      }
      if (coverage) {
        root.querySelector('[data-map-summary]').textContent = `Plán zahrnuje ${counts.size} zemí EU/NATO. Zobrazeno v tomto výřezu: ${visible.size}. Regionální rešerše se nerozděluje mezi členské státy. ${suppressed ? `Překryté značky (${suppressed}) lze vybrat filtrem Oblast.` : ''}`;
        return;
      }
      let inView = 0, offMap = 0, regional = 0, unknown = 0;
      for (const record of filtered) {
        const countries = record.areas.filter(area => data.areas[area]?.kind === 'country');
        if (countries.some(area => visible.has(area))) inView++;
        else if (countries.length) offMap++;
        else if (record.areas.length) regional++;
        else unknown++;
      }
      root.querySelector('[data-map-summary]').textContent = `Záznamy v zobrazených zemích: ${inView} · pouze regionální dosah: ${regional} · mimo výřez: ${offMap} · geografie neurčena: ${unknown}.${suppressed ? ` Překrývající se značky (${suppressed}) jsou skryté; země lze vybrat filtrem Oblast.` : ''}`;
    }
    function drawTimeline() {
      const svg = d3.select(root.querySelector('.signals-timeline'));
      const width = svg.node().getBoundingClientRect().width;
      if (!width) return;
      const starts = filtered.map(record => record.times[state.basis].start).filter(Boolean).sort();
      const ends = filtered.map(record => record.times[state.basis].end).filter(Boolean).sort();
      const first = state.from || starts[0] || data.default_from;
      const last = state.to || ends.at(-1) || data.default_to;
      const start = new Date(first + 'T00:00:00Z');
      const end = new Date(last + 'T00:00:00Z');
      const days = (end - start) / 86400000;
      const unit = days > 180 ? d3.utcMonth : days > 45 ? d3.utcMonday : d3.utcDay;
      const unitName = days > 180 ? 'měsíc' : days > 45 ? 'týden' : 'den';
      const bins = unit.range(unit.floor(start), unit.offset(unit.floor(end), 1)).map(date => ({ date, up: 0, down: 0, neutral: 0, unknown: 0 }));
      const byDate = new Map(bins.map(bin => [+bin.date, bin]));
      let missing = 0, imprecise = 0, outside = 0;
      for (const record of filtered) {
        const time = record.times[state.basis];
        if (!time.start) { missing++; continue; }
        if (time.precision === 'year' || time.precision === 'month' && unit !== d3.utcMonth) { imprecise++; continue; }
        const bin = byDate.get(+unit.floor(new Date(time.start + 'T00:00:00Z')));
        if (bin) bin[record.direction]++;
        else outside++;
      }
      const height = 134;
      svg.attr('viewBox', `0 0 ${width} ${height}`).selectAll('*').remove();
      svg.append('title').text('Počty záznamů podle začátku datovaného intervalu; bez odhadu chybějících dnů.');
      const x = d3.scaleBand().domain(bins.map(bin => +bin.date)).range([14, width - 14]).padding(.3);
      const maximum = d3.max(bins, bin => bin.up + bin.down + bin.neutral + bin.unknown) || 1;
      const y = d3.scaleLinear().domain([0, maximum]).range([92, 20]);
      svg.append('line').attr('class', 'signals-time-axis').attr('x1', 14).attr('x2', width - 14).attr('y1', 93).attr('y2', 93);
      const labelEvery = Math.max(1, Math.ceil(bins.length / (width < 420 ? 4 : 8)));
      bins.forEach((bin, index) => {
        let cumulative = 0;
        for (const direction of ['down', 'neutral', 'unknown', 'up']) {
          const value = bin[direction];
          if (value) svg.append('rect').attr('x', x(+bin.date)).attr('width', x.bandwidth()).attr('y', y(cumulative + value))
            .attr('height', y(cumulative) - y(cumulative + value)).attr('class', `signals-time-bar ${direction}`);
          cumulative += value;
        }
        if (index % labelEvery === 0) svg.append('text').attr('x', x(+bin.date) + x.bandwidth() / 2).attr('y', 120)
          .attr('text-anchor', 'middle').text(unit === d3.utcMonth ? d3.utcFormat('%m/%Y')(bin.date) : `${bin.date.getUTCDate()}. ${bin.date.getUTCMonth() + 1}.`);
        if (cumulative && bins.length <= 16) svg.append('text').attr('x', x(+bin.date) + x.bandwidth() / 2).attr('y', y(cumulative) - 5).attr('text-anchor', 'middle').text(cumulative);
        svg.append('rect').attr('x', x(+bin.date)).attr('width', x.bandwidth()).attr('y', 0).attr('height', 94).attr('fill', 'transparent')
          .append('title').text(`${day(d3.utcFormat('%Y-%m-%d')(bin.date))}: počet záznamů ${cumulative}; pro eskalaci ${bin.up}, proti ${bin.down}, bez směrového dopadu ${bin.neutral}, směr neurčen ${bin.unknown}.`);
      });
      root.querySelector('[data-time-unit]').textContent = `Počet záznamů / ${unitName}`;
      root.querySelector('[data-time-note]').textContent = `Intervaly jsou řazeny podle začátku. Mimo sloupce: neurčené datum ${missing}, nedostatečná přesnost ${imprecise}, začátek před vybraným obdobím ${outside}.`;
    }
    function renderDetail(record) {
      const target = root.querySelector('[data-detail]');
      if (!record) {
        const count = data.records.filter(r => core.matchesArea(r, state.area)).length;
        target.innerHTML = `<p class="signals-detail-label">Detail záznamu</p><h2>Výběru neodpovídá žádný podklad.</h2><p>Upravte oblast, období nebo další filtry. Prázdný výběr nevypovídá o celkovém riziku.</p>${count ? `<p>Počet záznamů pro tuto oblast mimo aktuální výběr: ${count}.</p><button type="button" data-all-dates>Zobrazit veškerou evidenci oblasti</button>` : '<p><a href="coverage.html">Prověřit rozsah kontroly zdrojů →</a></p>'}`;
        target.querySelector('[data-all-dates]')?.addEventListener('click', () => { Object.assign(state, {from:'',to:'',undated:true,topic:'all',status:'all',direction:'all',page:0}); render(); saveQuery(); });
        return;
      }
      const areas = record.areas.map(area => data.areas[area].label).join(' · ') || 'Geografie neurčena';
      target.innerHTML = `<p class="signals-detail-label">Detail záznamu · ${html(areas)}</p><h2>${html(record.title)}</h2>
        <div class="signals-tags"><span>${html(data.statuses[record.status])}</span><span>${html(data.directions[record.direction])}</span>${record.times.event.planned ? '<span>Oznámený plán</span>' : ''}</div>
        <dl class="signals-dates"><dt>Událost / interval</dt><dd>${html(timeLabel(record.times.event))}</dd><dt>Zveřejnění</dt><dd>${html(timeLabel(record.times.publication))}</dd><dt>Zařazení do monitoru</dt><dd>${html(timeLabel(record.times.discovery))}</dd></dl>
        <p class="signals-detail-summary">${html(record.summary)}</p>
        ${record.intake_type === 'retrospective_backfill' ? `<p class="archive-notice">Retrospektivní doplnění. Původní datum události a publikace zachováno.${monitoring.pending_backfill?.includes(record.id) ? ' Dopad na prognózu čeká na analytickou revizi.' : ''}</p>` : ''}
        ${record.event_links?.length ? `<details><summary>Propojená událost a zdrojová rodina</summary><ul>${record.event_links.map(link => `<li><a href="quality.html#${html(link.event_id)}">${html(link.event_title)}</a><br>${html(monitoring.roles[link.role])} · ${html(link.line_id)}<p>${html(link.independence_basis)}</p></li>`).join('')}</ul></details>` : '<p class="note">Přiřazení ke kanonické události dosud nebylo revidováno.</p>'}
        ${record.status_scope ? `<div class="signals-scope"><h3>Co označení doložení znamená</h3><p>${html(record.status_scope)}</p></div>` : ''}
        <details><summary>Alternativní vysvětlení</summary><p>${html(record.alternative_explanation || 'V tomto historickém záznamu není vyplněno.')}</p></details>
        <details><summary>Původ a geografické přiřazení</summary><p>${html(record.independence_note || 'Opakované publikace nejsou automaticky nezávislá potvrzení.')}</p>
        <dl><dt>Zdrojová linie</dt><dd>${html(record.independent_source_line || 'Neuvedena')}</dd><dt>Kořen původu</dt><dd>${html(record.provenance_root || 'Neuveden')}</dd><dt>Geografie</dt><dd>${html(record.geography_note || 'Ruční klasifikace geografického předmětu uloženého záznamu. Neurčuje původce ani přesné místo incidentu.')}</dd><dt>Původní časový údaj události</dt><dd>${html(record.times.event.raw || 'Neuveden')}</dd><dt>Původní časový údaj zveřejnění</dt><dd>${html(record.times.publication.raw || 'Neuveden')}</dd></dl></details>
        <div class="signals-source">${sourceLink(record.source_url, 'Otevřít hlavní zdroj')}<p>${html(record.source)}</p>
        ${record.source_urls.filter(url => url !== record.source_url).length ? `<details><summary>Další odkazy v záznamu (${record.source_urls.filter(url => url !== record.source_url).length})</summary><ul>${record.source_urls.filter(url => url !== record.source_url).map((url, index) => `<li>${sourceLink(url, `Zdroj ${index + 2}`)}</li>`).join('')}</ul></details>` : ''}</div>
        <p class="signals-record-id">${html(record.id)}</p>`;
    }
    function renderCoverage() {
      const target = root.querySelector('[data-detail]');
      const country = monitoring.countries[state.area];
      if (!country) {
        target.innerHTML = `<p class="signals-detail-label">Pokrytí rešerše</p><h2>Vyberte zemi v mapě nebo filtru.</h2><p>Plán obsahuje všechny země EU a NATO. Záznamy o regionech se nepřipisují automaticky jednotlivým státům.</p><p>Poslední audit: ${html(monitoring.as_of)}. Stáří poslední úspěšné kontroly se počítá k dnešku.</p><p><a href="coverage.html">Zdroje, provedené kontroly a mezery →</a></p>`;
        return;
      }
      const status = coverageStatus(country);
      const checks = country.checks.slice(0, 5);
      target.innerHTML = `<p class="signals-detail-label">Pokrytí zdrojů</p><h2>${html(country.label)}</h2><p class="coverage-state ${html(status)}">${html(monitoring.states[status])}</p><dl class="signals-dates"><dt>Poslední pokus</dt><dd>${html(country.last_attempt || 'Bez strukturované kontroly')}</dd><dt>Poslední dostupný obsah</dt><dd>${html(country.last_success || 'Bez záznamu')}</dd></dl><p>Chybějící rozsah: ${html(country.domains_missing.map(d => monitoring.domains[d]).join(', ') || 'dle uvedeného auditu')}.</p><p class="note">Kontrola jednoho staršího dokumentu neznamená úplnou kontrolu země. Nepřítomnost nálezu není důkazem bezpečí.</p>${checks.map(c => `<details><summary>${html(monitoring.outcomes[c.outcome])} · ${day(c.checked_at)}</summary><p>${html(c.scope)}</p><p>Období: ${html(c.period_start)} – ${html(c.period_end)}</p><p>${html(c.limitations)}</p>${c.urls.map(url => sourceLink(url, 'Kontrolovaný zdroj')).join('<br>')}</details>`).join('')}<p><a href="coverage.html">Celý protokol a plán zdrojů →</a></p>`;
    }
    function render() {
      const coverage = state.mode === 'coverage';
      root.classList.toggle('coverage-mode', coverage);
      filtered = core.filterRecords(data.records, state);
      if (!filtered.some(record => record.id === state.record)) state.record = filtered[0]?.id || null;
      const pages = Math.max(1, Math.ceil(filtered.length / size));
      state.page = Math.min(state.page, pages - 1);
      controls.forEach(control => { if (control.type === 'checkbox') control.checked = state[control.name]; else control.value = state[control.name]; control.disabled = coverage && control.name !== 'area'; control.closest('label').hidden = coverage && control.name !== 'area'; });
      root.querySelector('.signals-time-controls').hidden = coverage;
      root.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === state.mode)));
      root.querySelectorAll('[data-basis]').forEach(button => { button.disabled = coverage; });
      root.querySelector('[data-coverage-legend]').hidden = !coverage;
      root.querySelector('.signals-timeline-panel').hidden = coverage;
      root.querySelector('.signals-events').hidden = coverage;
      root.querySelector('#signals-map-title').textContent = coverage ? 'Pokrytí zdrojů podle zemí' : 'Územní vztah evidence';
      root.querySelector('.signals-map').setAttribute('aria-label', coverage ? 'Mapa pokrytí zdrojů podle zemí' : 'Mapa přiřazení evidence k zemím');
      root.querySelector('[data-map-note]').textContent = coverage ? 'Barvy vyjadřují rozsah provedené rešerše, nikoli riziko. Časové a tematické filtry evidence se v tomto pohledu neuplatňují.' : 'Přiřazení k zemi neoznačuje přesné místo incidentu ani jeho původce. Jeden záznam může zahrnovat více zemí.';
      root.querySelectorAll('[data-basis]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.basis === state.basis)));
      root.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === state.view)));
      const undated = data.records.filter(record => core.matchesCategories(record, state) && !record.times[state.basis].start).length;
      root.querySelector('[data-undated-count]').textContent = `(${undated})`;
      const counts = core.provenanceCounts(filtered);
      root.querySelector('[data-results]').innerHTML = coverage ? `<strong>${Object.keys(monitoring.countries).length} zemí v plánu</strong> · poslední audit ${html(monitoring.as_of)}` : `<strong>${filtered.length} z ${data.total} záznamů</strong> · ${html(state.area === 'all' ? 'všechny oblasti' : state.area === 'baltics_all' ? 'Pobaltí společně' : state.area === 'unknown' ? 'neurčená geografie' : data.areas[state.area].label)}`;
      root.querySelector('[data-count-note]').textContent = coverage ? 'Kontrola zdrojů není hodnocení bezpečnosti.' : `Propojené události či hodnocení: ${counts.events} · záznamy bez propojení: ${counts.unlinked}. Počet záznamů není počet útoků.`;
      root.querySelector('#signals-time-title').textContent = `Časová osa ${basisNames[state.basis]}`;
      root.querySelector('[data-order]').textContent = 'Od nejnovějšího začátku intervalu';
      const list = root.querySelector('[data-event-list]');
      const records = filtered.slice(state.page * size, state.page * size + size);
      list.innerHTML = records.length ? records.map(record => `<button type="button" class="signals-event" aria-pressed="${record.id === state.record}" data-record="${html(record.id)}"><span class="signals-event-dot" data-direction="${record.direction}" aria-hidden="true"></span><span><span class="signals-event-title">${html(record.title)}</span><span class="signals-event-meta">${html(timeLabel(record.times[state.basis]))} · ${html(record.areas.map(area => data.areas[area].label).join(', ') || 'Geografie neurčena')}</span><span class="signals-event-meta">${html(data.statuses[record.status])} · ${html(data.directions[record.direction])}</span></span></button>`).join('') : '<p class="signals-empty">Žádný záznam ve vybraném období a filtrech. Můžete také zahrnout záznamy bez určeného data.</p>';
      list.querySelectorAll('[data-record]').forEach(button => button.addEventListener('click', () => chooseRecord(button.dataset.record)));
      root.querySelector('[data-page]').textContent = `Strana ${state.page + 1} z ${pages}`;
      root.querySelector('[data-previous]').disabled = state.page === 0;
      root.querySelector('[data-next]').disabled = state.page >= pages - 1;
      if (coverage) renderCoverage(); else renderDetail(filtered.find(record => record.id === state.record));
      drawMap(); if (!coverage) drawTimeline();
    }
    state = readQuery();
    controls.forEach(control => control.addEventListener('change', () => {
      if (['from', 'to'].includes(control.name) && control.value && !core.validDay(control.value)) return;
      state[control.name] = control.type === 'checkbox' ? control.checked : control.value;
      if (state.from && state.to && state.from > state.to) {
        if (control.name === 'from') state.to = state.from;
        else state.from = state.to;
      }
      state.page = 0; state.record = null;
      render(); saveQuery();
    }));
    root.querySelectorAll('[data-basis]').forEach(button => button.addEventListener('click', () => { state.basis = button.dataset.basis; state.page = 0; state.record = null; render(); saveQuery(); }));
    root.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { state.view = button.dataset.view; render(); saveQuery(); }));
    root.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => { state.mode = button.dataset.mode; render(); saveQuery(); }));
    for (const [selector, delta] of [['[data-previous]', -1], ['[data-next]', 1]]) root.querySelector(selector).addEventListener('click', () => {
      state.page += delta; state.record = filtered[state.page * size]?.id || null; render(); saveQuery();
    });
    root.querySelector('[data-reset]').addEventListener('click', () => { state = defaults(); render(); saveQuery(); });
    window.addEventListener('popstate', () => { state = readQuery(); render(); });
    root.querySelector('.signals-controls').hidden = false;
    root.querySelector('.signals-main').hidden = false;
    render();
    loading.hidden = true;
    const observer = new ResizeObserver(() => { drawMap(); drawTimeline(); });
    observer.observe(root.querySelector('.signals-map'));
    observer.observe(root.querySelector('.signals-timeline'));
  }
  start().catch(error => {
    root.querySelector('.signals-main').hidden = true;
    root.querySelector('.signals-controls').hidden = true;
    loading.hidden = false;
    loading.setAttribute('role', 'alert');
    loading.textContent = `${error.message} Úplná evidence a textový přehled jsou dostupné níže.`;
  });
})();
