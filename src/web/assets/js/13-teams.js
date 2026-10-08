// pages: teams grid · team page (tabs: overview · results · schedule).

function setFocus(team) {
  state.focus = team;
  localStorage.setItem('gbl-focus', team);
  document.getElementById('focus').value = team;
  route(false);
}

pages.teams = () => [
  pageBanner('Ομάδες', `${TEAMS.length} ομάδες · κλικ σε μια ομάδα για τη σελίδα της`),
  h('div', {class: 'team-grid'}, D.standings.map(r => {
    const tile = h('a', {class: 'team-tile' + (r.team === state.focus ? ' is-focus' : ''), href: teamHref(r.team)},
      h('div', {class: 'tile-top'}, h('span', {class: 'tile-pos'}, `${r.pos}ος`), h('span', {class: 'muted small'}, `Elo ${r.elo}`)),
      h('div', {class: 'tile-name'}, crest(r.team, 40), h('span', null, r.team)),
      h('div', {class: 'tile-row'}, h('span', null, `${r.w}-${r.l} · ${signed(r.diff)}`), formChips(r.form)));
    tile.addEventListener('pointermove', e => { const b = tile.getBoundingClientRect(); tile.style.setProperty('--mx', `${e.clientX - b.left}px`); });
    return tile;
  })),
];

function upcomingList(name, limit) {
  const list = D.upcoming.filter(u => u.home === name || u.away === name).slice(0, limit);
  if (!list.length) return h('p', {class: 'empty'}, 'Κανένας προγραμματισμένος αγώνας.');
  return h('div', null, list.map(u => {
    const p = u.pi >= 0 ? D.next[u.pi] : null, home = u.home === name;
    return h('div', {class: 'sched-game'}, h('span', {class: 'muted small'}, dayLabel(u.d)),
      h('span', {class: 'vs'}, h('span', {class: 'muted small'}, home ? 'vs' : '@'), tlink(home ? u.away : u.home), u.t ? h('span', {class: 'muted small'}, u.t) : null),
      p ? h('span', {class: 'pchip'}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${name} ${pct(p.home === name ? p.p : 1 - p.p)}`) : h('span', {class: 'pchip'}));
  }));
}

function compareTeamPanel(name, tab) {
  if (tab && tab !== 'overview') return null;
  const box = h('div', {class: 'team-compare'});
  const draw = opponent => {
    if (!opponent) { box.replaceChildren(h('p', {class: 'empty'}, 'Επίλεξε δεύτερη ομάδα για σύγκριση.')); return; }
    const teams = [name, opponent].map(team => [team, STANDING[team]]);
    const meetings = played.filter(g => (g.home === name && g.away === opponent) || (g.home === opponent && g.away === name)).slice(0, 6);
    box.replaceChildren(
      h('div', {class: 'grid-2'}, ...teams.map(([team, row]) => h('div', {class: 'panel'},
        h('h3', null, crest(team, 24), ' ', team),
        h('p', null, `${row.pos}η θέση · ${row.w}-${row.l} · διαφορά ${signed(row.diff)}`),
        h('p', null, `${row.gp ? (row.pf / row.gp).toFixed(1) : '—'} πόντοι υπέρ · ${row.gp ? (row.pa / row.gp).toFixed(1) : '—'} κατά ανά αγώνα`),
        h('p', null, `Elo ${row.elo} · φόρμα ${row.form.join(' ') || '—'}`)))),
      h('p', {class: 'foot-note'}, meetings.length ? 'Πρόσφατες μεταξύ τους αναμετρήσεις: ' + meetings.map(g => `${g.home} ${g.hs}–${g.as} ${g.away}`).join(' · ') : 'Δεν υπάρχουν μεταξύ τους αποτελέσματα στο διαθέσιμο ιστορικό.'));
  };
  const select = selectEl([['', 'Διάλεξε αντίπαλο'], ...TEAMS.filter(t => t !== name).sort().map(t => [t, t])], '', draw, 'Σύγκριση με ομάδα');
  draw('');
  return h('section', {class: 'panel'}, sectionHead('Σύγκριση ομάδων', 'Σύγκρινε θέση, πόντους, Elo, φόρμα και πρόσφατα μεταξύ τους αποτελέσματα.'),
    h('div', {class: 'team-compare-select'}, select), box);
}

pages.team = ({name, tab}) => {
  const r = STANDING[name];
  if (!r) return [pageBanner('Δεν βρέθηκε η ομάδα', null, h('a', {class: 'btn btn-ghost', href: url('teams')}, '← Όλες οι ομάδες'))];
  const games = played.filter(g => g.home === name || g.away === name);
  const thisSeason = games.filter(g => g.s === season), lastSeason = games.filter(g => g.s !== season);
  const withPick = games.filter(g => g.pick), okN = withPick.filter(g => outcome(g).ok).length;
  const hitsN = withPick.filter(g => outcome(g).hit).length;
  const remaining = D.upcoming.filter(u => u.home === name || u.away === name).length;
  return [
    h('section', {class: 'banner'}, h('div', {class: 'banner-inner'},
      h('div', null,
        h('div', {class: 'crumb'}, h('a', {href: url('teams')}, 'Ομάδες'), ' / ', name),
        h('div', {class: 'team-banner-row'}, crest(name, 68),
          h('div', null, h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${season}`), h('h1', null, name),
            h('p', {class: 'hero-sub'}, `${r.pos}ος στη βαθμολογία · ${r.w}-${r.l} · σερί ${streakGr(r.streak)}`)))),
      h('button', {class: 'btn btn-outline', type: 'button', onclick: () => setFocus(name), disabled: name === state.focus},
        name === state.focus ? '★ Η ομάδα μου' : '☆ Ορισμός ως η ομάδα μου'))),
    h('section', null, sectionHead('Η σεζόν με μια ματιά', `${season} · δύναμη, επίθεση/άμυνα, έδρα και πόσο καλά την «διαβάζει» το μοντέλο`),
      h('div', {class: 'kpis'},
      kpi('Elo', String(r.elo), `${signed(r.elo - 1500)} από τον μέσο όρο`, {info: 'elo', count: {to: r.elo}}),
      kpi('Πόντοι / αγώνα', r.gp ? (r.pf / r.gp).toFixed(1) : '–', r.gp ? `δέχεται ${(r.pa / r.gp).toFixed(1)}` : '', r.gp ? {count: {to: r.pf / r.gp, dec: 1}} : {}),
      kpi('Έδρα · Εκτός', `${r.hw}-${r.hl} · ${r.aw}-${r.al}`, 'νίκες-ήττες'),
      kpi('Το μοντέλο στους αγώνες της', withPick.length ? `${okN}/${withPick.length}` : '–', `σωστοί νικητές · 🔥 ${hitsN} σίγουρες επιτυχίες`, {info: 'acc'}))),
    compareTeamPanel(name, tab),
    tabs('team', [
      {key: 'overview', label: 'Επισκόπηση', render: () => [h('div', {class: 'grid-2'},
        h('section', {class: 'panel'}, sectionHead('Επόμενοι αγώνες', null, h('a', {href: teamHref(name, 'schedule')}, 'Όλοι →')), upcomingList(name, 6)),
        h('section', {class: 'panel'}, sectionHead('Εξέλιξη Elo', `${name} με μπλε · οι υπόλοιπες με γκρι`, infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': name})))]},
      {key: 'results', label: 'Αποτελέσματα', count: games.length, render: () => [
        h('section', {class: 'panel'}, sectionHead('Αποτελέσματα ' + season, 'με την πρόβλεψη του μοντέλου'), resultsTable(thisSeason, {empty: 'Κανένας αγώνας ακόμα.'})),
        lastSeason.length ? h('details', {class: 'panel'}, h('summary', null, `Προηγούμενη σεζόν · ${lastSeason.length} αγώνες`), resultsTable(lastSeason)) : null]},
      {key: 'schedule', label: 'Πρόγραμμα', count: remaining, render: () => [h('section', {class: 'panel'}, sectionHead('Όλο το πρόγραμμα'), upcomingList(name, 99))]},
    ], tab, k => teamHref(name, k)),
  ];
};
