// page: schedule — every remaining game, by month or by team.

pages.schedule = () => {
  const box = h('div');
  const months = [...new Set(D.upcoming.map(u => u.d.slice(0, 7)))];
  const st = {team: '', month: months[0] || ''};
  const draw = () => {
    const rows = D.upcoming.filter(u => st.team ? (u.home === st.team || u.away === st.team) : (!st.month || u.d.startsWith(st.month)));
    const byDay = {};
    rows.forEach(u => (byDay[u.d] = byDay[u.d] || []).push(u));
    box.replaceChildren(...(rows.length ? Object.entries(byDay).map(([d, us]) => h('div', {class: 'sched-day'}, h('div', {class: 'sched-date'}, fullDate(d)),
      us.map(u => {
        const p = u.pi >= 0 ? D.next[u.pi] : null;
        return h('div', {class: 'sched-game' + (isFocus(u.home, u.away) ? ' is-focus' : '')}, h('span', {class: 'muted'}, u.t || ''),
          h('span', {class: 'vs'}, tlink(u.home), h('span', {class: 'muted'}, '–'), tlink(u.away)),
          p ? h('span', {class: 'pchip', title: 'Πρόβλεψη μοντέλου'}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${p.w} ${pct(Math.max(p.p, 1 - p.p))}`) : h('span', {class: 'pchip'}));
      }))) : [h('p', {class: 'empty'}, 'Κανένας αγώνας.')]));
  };
  const monthCtrl = segCtrl(months.map(mo => [mo, `${MONTHS[+mo.slice(5) - 1]} '${mo.slice(2, 4)}`]), st.month, v => { st.month = v; draw(); });
  const filters = h('div', {class: 'filters'},
    selectEl([['', 'Όλες οι ομάδες'], ...TEAMS.slice().sort().map(t => [t, t])], st.team, v => { st.team = v; monthCtrl.style.display = v ? 'none' : ''; draw(); }, 'Ομάδα'),
    monthCtrl);
  draw();
  return [pageBanner('Πρόγραμμα', `${D.upcoming.length} αγώνες μέχρι το τέλος της κανονικής περιόδου`),
    h('section', {class: 'panel'}, sectionHead('Αγώνες ανά ημέρα', 'δεξιά: η πρόβλεψη του μοντέλου (σκορ · φαβορί και πιθανότητα), μόνο για την επόμενη αγωνιστική', infoDot('prob')),
      filters, box,
      h('p', {class: 'foot-note'}, 'Το μοντέλο προβλέπει μόνο την επόμενη αγωνιστική. Για αγώνες πιο μακριά, η φόρμα και τα ρόστερ θα έχουν αλλάξει μέχρι τότε.'))];
};
