/* Presentation filters only: these functions never calculate a forecast. */
((scope) => {
  'use strict';
  function matchesArea(record, area) {
    if (area === 'all') return true;
    if (area === 'unknown') return record.areas.length === 0;
    if (area === 'baltics_all') return record.areas.some(value => ['EST', 'LVA', 'LTU', 'BALTICS'].includes(value));
    return record.areas.includes(area);
  }
  function matchesCategories(record, state) {
    return matchesArea(record, state.area) &&
      (state.topic === 'all' || record.topics.includes(state.topic)) &&
      (state.status === 'all' || record.status === state.status) &&
      (state.direction === 'all' || record.direction === state.direction);
  }
  function matchesTime(record, state) {
    const time = record.times[state.basis];
    if (!time.start || !time.end) return state.undated;
    return (!state.from || time.end >= state.from) && (!state.to || time.start <= state.to);
  }
  function filterRecords(records, state) {
    return records.filter(record => matchesCategories(record, state) && matchesTime(record, state)).sort((a, b) =>
      (b.times[state.basis].start || '').localeCompare(a.times[state.basis].start || '') || b.id.localeCompare(a.id));
  }
  function countryCounts(records, areas) {
    const counts = new Map();
    for (const record of records) {
      for (const area of new Set(record.areas)) {
        if (areas[area]?.kind === 'country') counts.set(area, (counts.get(area) || 0) + 1);
      }
    }
    return counts;
  }
  function validDay(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(value + 'T00:00:00Z');
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }
  function provenanceCounts(records) {
    const events = new Set();
    let unlinked = 0;
    for (const record of records) {
      if (!record.event_links?.length) unlinked++;
      for (const link of record.event_links || []) events.add(link.event_id);
    }
    return { events: events.size, unlinked };
  }
  function coverageState(country, now) {
    if (!country || !country.last_success) return country?.status || 'not_checked';
    // A failed recent attempt cannot refresh the last successful review.
    if (Date.parse(now) - Date.parse(country.last_success) > country.review_days * 86400000) return 'stale';
    return country.status;
  }
  const api = { matchesArea, matchesCategories, matchesTime, filterRecords, countryCounts, validDay, provenanceCounts, coverageState };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else scope.EscalationSignals = api;
})(typeof window === 'undefined' ? globalThis : window);
