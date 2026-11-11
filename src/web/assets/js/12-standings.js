// page: standings — tabs: table (sortable table, Elo bars, Elo over time) · season projections.

/** "<1%", "37%", ">99%": a simulated chance, never shown as a certainty. */
const fmtChance = p => p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : pct(p);

/** Season projections: the remaining games simulated (src/simulate.py, D.projection). */
function projectionsTab() {
  const P = D.projection;
  if (!P || !P.teams.length) return [h('p', {class: 'empty'}, T('Δεν υπάρχει προσομοίωση για αυτή τη σεζόν.', 'No simulation for this season.'))];
  const n = P.teams.length, spots = P.playoff_spots, releg = P.relegation_spots;
  const meter = (p, bad) => h('span', {class: 'pmeter'}, h('span', {class: 'pm-bar'}, h('span', {class: 'pm-fill' + (bad ? ' bad' : ''), 'data-w': `${Math.round(p * 100)}%`})), h('b', null, fmtChance(p)));
  const strip = r => h('span', {class: 'pos-strip', role: 'img', 'aria-label': T('Πιθανότητα ανά τελική θέση', 'Chance of each final position')},
    r.pos.map((p, k) => h('i', {class: k === spots - 1 ? 'cut' : null, style: `opacity:${(0.06 + 0.94 * p).toFixed(2)}`, title: T(`${ordinal(k + 1)} θέση: ${fmtChance(p)}`, `${ordinal(k + 1)} place: ${fmtChance(p)}`)})));
  return [
    h('section', {class: 'panel'},
      sectionHead(T('Πιθανότητες σεζόν', 'Season projections'),
        T(`${P.runs.toLocaleString('el-GR')} προσομοιώσεις των ${P.games_left} αγώνων που απομένουν`, `${P.runs.toLocaleString('en-GB')} simulations of the ${P.games_left} games left`), infoDot('sim')),
      table([
        {label: T('Ομάδα', 'Team'), sticky: 1, sort: r => r.team, render: r => tlink(r.team)},
        {label: T('Τίτλος', 'Title'), num: true, sort: r => r.title, render: r => meter(r.title)},
        {label: T(`Πλέι-οφ (${spots}άδα)`, `Playoffs (top ${spots})`), num: true, sort: r => r.playoffs, render: r => meter(r.playoffs)},
        {label: T('Υποβιβασμός', 'Relegation'), num: true, sort: r => r.relegation, render: r => meter(r.relegation, true)},
        {label: T('Αναμενόμενο ρεκόρ', 'Expected record'), num: true, hideSm: true, sort: r => r.exp_w, render: r => `${r.exp_w.toFixed(1)}-${r.exp_l.toFixed(1)}`},
        {label: T(`Θέσεις 1–${n}`, `Places 1–${n}`), render: strip},
      ], P.teams, {sortIdx: 1, dir: -1, rowClass: r => r.team === state.focus ? 'is-focus' : null}),
      h('p', {class: 'foot-note'}, T(`Υποθέσεις: στα πλέι-οφ περνούν οι ${spots} πρώτες ομάδες και ${releg === 1 ? 'υποβιβάζεται η τελευταία' : `υποβιβάζονται οι ${releg} τελευταίες`}. Οι ισοβαθμίες λύνονται με τη διαφορά πόντων, όχι με τα μεταξύ τους αποτελέσματα. Κάθε ομάδα κρατά για όλη τη σεζόν τη δύναμη που έχει σήμερα (Elo, φόρμα, ρεκόρ), γι' αυτό οι πιθανότητες αλλάζουν μετά από κάθε αγωνιστική. Στις θέσεις, όσο πιο έντονο το χρώμα, τόσο πιο πιθανή η θέση· η γραμμή δείχνει το όριο των πλέι-οφ.`,
        `Assumptions: the top ${spots} reach the playoffs and the bottom ${releg} ${releg === 1 ? 'team is' : 'teams are'} relegated. Ties are broken by point difference, not head-to-head. Every team keeps today's strength (Elo, form, record) for the rest of the season, so the chances move after every round. In the places strip, the deeper the colour, the likelier the place; the gap marks the playoff cut.`))),
  ];
}

function standingsTab() {
  return [
  h('section', {class: 'panel'}, sectionHead(T('Πίνακας', 'Table'), T(`${season} · σειρά με ποσοστό νικών, μετά διαφορά πόντων · Ν-Η = νίκες-ήττες`, `${season} · ranked by win percentage, then point difference · W-L = wins-losses`), infoDot('form')),
    standingsTable(false),
    h('p', {class: 'foot-note'}, T('Η σειρά καθορίζεται πρώτα από το ποσοστό νικών και έπειτα από τη διαφορά πόντων. Στην επίσημη βαθμολογία, οι ισοβαθμίες κρίνονται και από τα αποτελέσματα μεταξύ των ομάδων.', 'The order is set by win percentage first, then by point difference. In the official standings, ties are also decided by head-to-head results.'))),
  h('div', {class: 'grid-2-even'},
    h('section', {class: 'panel'}, sectionHead('Elo', T('δύναμη σε σχέση με το 1500', 'strength relative to 1500'), infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'bars'}),
      h('p', {class: 'foot-note'}, T('Κλικ σε μια μπάρα για τη σελίδα της ομάδας.', 'Click a bar for the team page.'))),
    h('section', {class: 'panel'}, sectionHead(T('Εξέλιξη Elo', 'Elo over time'), T(`${tn(state.focus)} με μπλε · οι υπόλοιπες με γκρι`, `${tn(state.focus)} in blue · the rest in grey`)), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': state.focus}),
      eloTable())),
  ];
}

pages.standings = ({tab}) => [
  pageBanner(T('Βαθμολογία', 'Standings'), T(`${roundNo - 1} ${roundNo === 2 ? 'αγωνιστική' : 'αγωνιστικές'} · κλικ στις επικεφαλίδες για ταξινόμηση`, `${roundNo - 1} round${roundNo === 2 ? '' : 's'} · click a heading to sort`)),
  tabs('standings', [
    {key: 'table', label: T('Πίνακας', 'Table'), render: standingsTab},
    {key: 'projections', label: T('Πιθανότητες σεζόν', 'Season projections'), count: D.projection?.teams.length || null, render: projectionsTab},
  ], tab, k => url('standings', k)),
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
