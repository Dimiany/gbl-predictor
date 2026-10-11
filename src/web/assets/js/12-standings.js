// page: standings — full sortable table, Elo bars, Elo over time.

pages.standings = () => [
  pageBanner(T('Βαθμολογία', 'Standings'), T(`${roundNo - 1} αγωνιστικές · κλικ στις επικεφαλίδες για ταξινόμηση`, `${roundNo - 1} rounds · click a heading to sort`)),
  h('section', {class: 'panel'}, sectionHead(T('Πίνακας', 'Table'), T(`${season} · σειρά με ποσοστό νικών, μετά διαφορά πόντων · Ν-Η = νίκες-ήττες`, `${season} · ranked by win percentage, then point difference · W-L = wins-losses`), infoDot('form')),
    standingsTable(false),
    h('p', {class: 'foot-note'}, T('Η σειρά καθορίζεται πρώτα από το ποσοστό νικών και έπειτα από τη διαφορά πόντων. Στην επίσημη βαθμολογία, οι ισοβαθμίες κρίνονται και από τα αποτελέσματα μεταξύ των ομάδων.', 'The order is set by win percentage first, then by point difference. In the official standings, ties are also decided by head-to-head results.'))),
  h('div', {class: 'grid-2-even'},
    h('section', {class: 'panel'}, sectionHead('Elo', T('δύναμη σε σχέση με το 1500', 'strength relative to 1500'), infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'bars'}),
      h('p', {class: 'foot-note'}, T('Κλικ σε μια μπάρα για τη σελίδα της ομάδας.', 'Click a bar for the team page.'))),
    h('section', {class: 'panel'}, sectionHead(T('Εξέλιξη Elo', 'Elo over time'), T(`${tn(state.focus)} με μπλε · οι υπόλοιπες με γκρι`, `${tn(state.focus)} in blue · the rest in grey`)), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': state.focus}),
      eloTable())),
];

/** Text twin of the Elo charts: start / peak / low / now for the current season. */
function eloTable() {
  const rows = TEAMS.map(team => {
    const segs = D.elo_history[team] || [], vals = (segs[segs.length - 1] || []).map(p => p[1]);
    return vals.length ? {team, start: vals[0], hi: Math.max(...vals), lo: Math.min(...vals), now: vals[vals.length - 1]} : null;
  }).filter(Boolean);
  return h('details', null, h('summary', null, T('Πίνακας Elo σεζόν', 'Season Elo table')), table([
    {label: T('Ομάδα', 'Team'), sticky: 1, sort: r => r.team, render: r => tlink(r.team)},
    {label: T('Αρχή', 'Start'), num: true, sort: r => r.start, render: r => Math.round(r.start)},
    {label: T('Υψηλό', 'High'), num: true, sort: r => r.hi, render: r => Math.round(r.hi)},
    {label: T('Χαμηλό', 'Low'), num: true, sort: r => r.lo, render: r => Math.round(r.lo)},
    {label: T('Τώρα', 'Now'), num: true, sort: r => r.now, render: r => Math.round(r.now)},
  ], rows, {sortIdx: 4, dir: -1}));
}
