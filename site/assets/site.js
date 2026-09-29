const search = document.querySelector('[data-archive-search]');
if (search) {
  const items = [...document.querySelectorAll('[data-archive-item]')];
  const counter = document.querySelector('[data-archive-count]');
  const normalize = value => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  search.addEventListener('input', () => {
    const query = normalize(search.value.trim());
    for (const item of items) item.hidden = !normalize(item.textContent).includes(query);
    counter.textContent = `${items.filter(item => !item.hidden).length} / ${items.length} zpráv`;
  });
}
const freshness = document.querySelector('[data-assessment-time]');
if (freshness) {
  const age = (Date.now() - Date.parse(freshness.dataset.assessmentTime)) / 3600000;
  if (age > 48) {
    freshness.hidden = false;
    freshness.textContent = `Poslední vyhodnocení je starší než ${Math.floor(age / 24)} dny. Údaje níže platí k uvedené uzávěrce.`;
  }
}

