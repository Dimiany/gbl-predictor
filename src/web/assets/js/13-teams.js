// pages: teams grid · team page (tabs: overview · results · schedule).

function setFocus(team) {
  state.focus = team;
  localStorage.setItem('gbl-focus', team);
  document.getElementById('focus').value = team;
  route(false);
}

/** Teams ordered by Elo (the user's call, 12/10/2026): strength, not the league table. */
pages.teams = () => [
  pageBanner(T('Ομάδες', 'Teams'), T(`${TEAMS.length} ομάδες, με σειρά δύναμης (Elo) · κλικ σε μια ομάδα για τη σελίδα της`, `${TEAMS.length} teams, in order of strength (Elo) · click a team for its page`)),
  h('section', {class: 'panel howto elo-note'},
    sectionHead(T('Τι είναι το Elo;', 'What is Elo?'), null, infoDot('elo')),
    h('p', null, T('Ένας βαθμός δύναμης για κάθε ομάδα. Όλες ξεκινούν κοντά στο 1500. Μετά από κάθε αγώνα, η νικήτρια παίρνει πόντους από την ηττημένη: περισσότερους όταν κερδίζει μια ισχυρότερη ομάδα, λιγότερους όταν κερδίζει ένα αναμενόμενο παιχνίδι. Έτσι το Elo δείχνει ποια ομάδα είναι πραγματικά δυνατή, όχι μόνο ποια έχει τις περισσότερες νίκες.',
      'A strength rating for every team. All start near 1500. After each game the winner takes points from the loser: more for beating a stronger team, fewer for winning an expected game. So Elo shows which team is actually strong, not just which has the most wins.')),
    h('p', {class: 'foot-note'}, T('Οι ομάδες εδώ είναι ταξινομημένες κατά Elo. Δεν είναι η θέση τους στη βαθμολογία: αυτή φαίνεται με μικρά γράμματα σε κάθε κάρτα και στη σελίδα Βαθμολογία.',
      'The teams here are ranked by Elo. This is not their league position: that is shown in small print on each card and on the Standings page.'))),
  h('div', {class: 'team-grid'}, [...D.standings].sort((a, b) => b.elo - a.elo).map((r, i) => {
    const tile = h('a', {class: 'team-tile' + (r.team === state.focus ? ' is-focus' : ''), href: teamHref(r.team)},
      h('div', {class: 'tile-top'}, h('span', {class: 'tile-elo'}, h('small', null, `#${i + 1} Elo`), ' ', String(r.elo)),
        h('span', {class: 'muted small'}, T(`${ordinal(r.pos)} στη βαθμολογία`, `${ordinal(r.pos)} in the table`))),
      h('div', {class: 'tile-name'}, crest(r.team, 40), h('span', null, tn(r.team))),
      h('div', {class: 'tile-row'}, h('span', null, `${r.w}-${r.l} · ${signed(r.diff)}`), formChips(r.form)));
    tile.addEventListener('pointermove', e => { const b = tile.getBoundingClientRect(); tile.style.setProperty('--mx', `${e.clientX - b.left}px`); });
    return tile;
  })),
];

function upcomingList(name, limit) {
  const list = D.upcoming.filter(u => u.home === name || u.away === name).slice(0, limit);
  if (!list.length) return h('p', {class: 'empty'}, T('Κανένας προγραμματισμένος αγώνας.', 'No games scheduled.'));
  return h('div', null, list.map(u => {
    const p = u.pi >= 0 ? D.next[u.pi] : null, home = u.home === name;
    return h('div', {class: 'sched-game'}, h('span', {class: 'muted small'}, dayLabel(u.d)),
      h('span', {class: 'vs'}, h('span', {class: 'muted small'}, home ? T('εντός έδρας με', 'home vs') : T('εκτός έδρας με', 'away at')), tlink(home ? u.away : u.home), u.t ? h('span', {class: 'muted small'}, u.t) : null),
      p ? h('span', {class: 'pchip'}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${tn(name)} ${pct(p.home === name ? p.p : 1 - p.p)}`) : h('span', {class: 'pchip'}));
  }));
}

function compareTeamPanel(name, tab) {
  if (tab && tab !== 'overview') return null;
  const box = h('div', {class: 'team-compare'});
  const draw = opponent => {
    if (!opponent) { box.replaceChildren(h('p', {class: 'empty'}, T('Επίλεξε δεύτερη ομάδα για σύγκριση.', 'Choose a second team to compare.'))); return; }
    const teams = [name, opponent].map(team => [team, STANDING[team]]);
    const meetings = played.filter(g => (g.home === name && g.away === opponent) || (g.home === opponent && g.away === name)).slice(0, 6);
    box.replaceChildren(
      h('div', {class: 'grid-2'}, ...teams.map(([team, row]) => h('div', {class: 'panel'},
        h('h3', null, crest(team, 24), ' ', tn(team)),
        h('p', null, T(`${row.pos}η θέση · ${row.w}-${row.l} · διαφορά ${signed(row.diff)}`, `${ordinal(row.pos)} place · ${row.w}-${row.l} · point difference ${signed(row.diff)}`)),
        h('p', null, T(`${row.gp ? (row.pf / row.gp).toFixed(1) : '—'} πόντοι υπέρ · ${row.gp ? (row.pa / row.gp).toFixed(1) : '—'} κατά ανά αγώνα`, `${row.gp ? (row.pf / row.gp).toFixed(1) : '—'} points for · ${row.gp ? (row.pa / row.gp).toFixed(1) : '—'} against per game`)),
        h('p', null, T(`Elo ${row.elo} · φόρμα ${row.form.map(streakGr).join(' ') || '—'}`, `Elo ${row.elo} · form ${row.form.join(' ') || '—'}`))))),
      h('p', {class: 'foot-note'}, meetings.length ? T('Πρόσφατες μεταξύ τους αναμετρήσεις: ', 'Recent head-to-head games: ') + meetings.map(g => `${tn(g.home)} ${g.hs}–${g.as} ${tn(g.away)}`).join(' · ') : T('Δεν υπάρχουν μεταξύ τους αποτελέσματα στο διαθέσιμο ιστορικό.', 'No head-to-head results in the available history.')));
  };
  const select = selectEl([['', T('Διάλεξε αντίπαλο', 'Choose an opponent')], ...teamOptions(TEAMS.filter(t => t !== name))], '', draw, T('Σύγκριση με ομάδα', 'Compare with team'));
  draw('');
  return h('section', {class: 'panel'}, sectionHead(T('Σύγκριση ομάδων', 'Compare teams'), T('Σύγκρινε θέση, πόντους, Elo, φόρμα και πρόσφατα μεταξύ τους αποτελέσματα.', 'Compare position, points, Elo, form and recent head-to-head results.')),
    h('div', {class: 'team-compare-select'}, select), box);
}

pages.team = ({name, tab}) => {
  const r = STANDING[name];
  if (!r) return [pageBanner(T('Δεν βρέθηκε η ομάδα', 'Team not found'), null, h('a', {class: 'btn btn-ghost', href: url('teams')}, T('← Όλες οι ομάδες', '← All teams')))];
  const games = played.filter(g => g.home === name || g.away === name);
  const thisSeason = games.filter(g => g.s === season), lastSeason = games.filter(g => g.s !== season);
  const withPick = games.filter(g => g.pick), okN = withPick.filter(g => outcome(g).ok).length;
  const hitsN = withPick.filter(g => outcome(g).hit).length;
  const remaining = D.upcoming.filter(u => u.home === name || u.away === name).length;
  return [
    h('section', {class: 'banner'}, h('div', {class: 'banner-inner'},
      h('div', null,
        h('div', {class: 'crumb'}, h('a', {href: url('teams')}, T('Ομάδες', 'Teams')), ' / ', tn(name)),
        h('div', {class: 'team-banner-row'}, crest(name, 68),
          h('div', null, h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${season}`), h('h1', null, tn(name)),
            h('p', {class: 'hero-sub'}, T(`${r.pos}ος στη βαθμολογία · ${r.w}-${r.l} · σερί ${streakGr(r.streak)}`, `${ordinal(r.pos)} in the standings · ${r.w}-${r.l} · streak ${r.streak}`))))),
      h('button', {class: 'btn btn-outline', type: 'button', onclick: () => setFocus(name), disabled: name === state.focus},
        name === state.focus ? T('★ Η ομάδα μου', '★ My team') : T('☆ Ορισμός ως η ομάδα μου', '☆ Make this my team')))),
    h('section', null, sectionHead(T('Η εικόνα της ομάδας', 'Team overview'), T(`${season} · δύναμη, επίθεση και άμυνα, έδρα και πόσο εύστοχα προβλέπει το μοντέλο τους αγώνες της`, `${season} · strength, offence and defence, home record, and how well the model predicts its games`)),
      h('div', {class: 'kpis'},
      kpi('Elo', String(r.elo), T(`${signed(r.elo - 1500)} από τον μέσο όρο`, `${signed(r.elo - 1500)} from the average`), {info: 'elo', count: {to: r.elo}}),
      kpi(T('Πόντοι / αγώνα', 'Points / game'), r.gp ? (r.pf / r.gp).toFixed(1) : '–', r.gp ? T(`δέχεται ${(r.pa / r.gp).toFixed(1)}`, `allows ${(r.pa / r.gp).toFixed(1)}`) : '', r.gp ? {count: {to: r.pf / r.gp, dec: 1}} : {}),
      kpi(T('Έδρα · Εκτός', 'Home · Away'), `${r.hw}-${r.hl} · ${r.aw}-${r.al}`, T('νίκες-ήττες', 'wins-losses')),
      kpi(T('Προβλέψεις για την ομάδα', 'Predictions for this team'), withPick.length ? `${okN}/${withPick.length}` : '–', T(`σωστοί νικητές · 🔥 ${hitsN} επιτυχίες σε προβλέψεις υψηλής πιθανότητας`, `winners called · 🔥 ${hitsN} high-confidence hits`), {info: 'acc'}))),
    compareTeamPanel(name, tab),
    tabs('team', [
      {key: 'overview', label: T('Επισκόπηση', 'Overview'), render: () => [h('div', {class: 'grid-2'},
        h('section', {class: 'panel'}, sectionHead(T('Επόμενοι αγώνες', 'Upcoming games'), null, h('a', {href: teamHref(name, 'schedule')}, T('Όλοι →', 'All →'))), upcomingList(name, 6)),
        h('section', {class: 'panel'}, sectionHead(T('Εξέλιξη Elo', 'Elo over time'), T(`${tn(name)} με μπλε · οι υπόλοιπες με γκρι`, `${tn(name)} in blue · the rest in grey`), infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': name})))]},
      {key: 'results', label: T('Αποτελέσματα', 'Results'), count: games.length, render: () => [
        h('section', {class: 'panel'}, sectionHead(T('Αποτελέσματα ', 'Results ') + season, T('με την πρόβλεψη του μοντέλου', 'with the model\'s prediction')), resultsTable(thisSeason, {empty: T('Κανένας αγώνας ακόμα.', 'No games yet.')})),
        lastSeason.length ? h('details', {class: 'panel'}, h('summary', null, T('Προηγούμενη σεζόν', 'Previous season') + ` · ${nGames(lastSeason.length)}`), resultsTable(lastSeason)) : null]},
      {key: 'schedule', label: T('Πρόγραμμα', 'Schedule'), count: remaining, render: () => [h('section', {class: 'panel'}, sectionHead(T('Όλο το πρόγραμμα', 'Full schedule')), upcomingList(name, 99))]},
    ], tab, k => teamHref(name, k)),
  ];
};
