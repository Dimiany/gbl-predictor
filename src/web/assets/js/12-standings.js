// page: standings — full sortable table, Elo bars, Elo over time.

pages.standings = () => [
  pageBanner('Βαθμολογία', `${roundNo - 1} αγωνιστικές · κλικ στις επικεφαλίδες για ταξινόμηση`),
  h('section', {class: 'panel'}, sectionHead('Πίνακας', `${season} · σειρά με ποσοστό νικών, μετά διαφορά πόντων · Ν-Η = νίκες-ήττες`, infoDot('form')),
    standingsTable(false),
    h('p', {class: 'foot-note'}, 'Η σειρά βγαίνει από το ποσοστό νικών και μετά τη διαφορά πόντων, όπως στο feature του μοντέλου. Η επίσημη ΕΣΑΚΕ λύνει ισοβαθμίες με τα μεταξύ τους.')),
  h('div', {class: 'grid-2-even'},
    h('section', {class: 'panel'}, sectionHead('Elo', 'δύναμη σε σχέση με το 1500', infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'bars'}),
      h('p', {class: 'foot-note'}, 'Κλικ σε μια μπάρα για τη σελίδα της ομάδας.')),
    h('section', {class: 'panel'}, sectionHead('Εξέλιξη Elo', `${state.focus} με μπλε · οι υπόλοιπες με γκρι`), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': state.focus}),
      eloTable())),
];

/** Text twin of the Elo charts: start / peak / low / now for the current season. */
function eloTable() {
  const rows = TEAMS.map(team => {
    const segs = D.elo_history[team] || [], vals = (segs[segs.length - 1] || []).map(p => p[1]);
    return vals.length ? {team, start: vals[0], hi: Math.max(...vals), lo: Math.min(...vals), now: vals[vals.length - 1]} : null;
  }).filter(Boolean);
  return h('details', null, h('summary', null, 'Πίνακας Elo σεζόν'), table([
    {label: 'Ομάδα', sticky: 1, sort: r => r.team, render: r => tlink(r.team)},
    {label: 'Αρχή', num: true, sort: r => r.start, render: r => Math.round(r.start)},
    {label: 'Υψηλό', num: true, sort: r => r.hi, render: r => Math.round(r.hi)},
    {label: 'Χαμηλό', num: true, sort: r => r.lo, render: r => Math.round(r.lo)},
    {label: 'Τώρα', num: true, sort: r => r.now, render: r => Math.round(r.now)},
  ], rows, {sortIdx: 4, dir: -1}));
}
