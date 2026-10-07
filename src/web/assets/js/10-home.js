// page: home — hero, latest results ticker, KPIs, next round, hall of fame, table, results.

function standingsTable(compact) {
  const cols = [
    {label: '#', num: true, sticky: 1, sort: r => r.pos, render: r => h('span', {class: 'pos' + (r.pos <= 8 ? ' top' : '')}, r.pos)},
    {label: 'Ομάδα', sticky: 2, sort: r => r.team, render: r => tlink(r.team)},
    {label: 'Αγ', num: true, title: 'Αγώνες', sort: r => r.gp, render: r => r.gp},
    {label: 'Ν', num: true, title: 'Νίκες', sort: r => r.w, render: r => r.w},
    {label: 'Η', num: true, title: 'Ήττες', sort: r => r.l, render: r => r.l},
  ];
  if (!compact) cols.push(
    {label: 'Έδρα', num: true, title: 'Νίκες-ήττες εντός', sort: r => r.hw - r.hl, render: r => `${r.hw}-${r.hl}`},
    {label: 'Εκτός', num: true, title: 'Νίκες-ήττες εκτός', sort: r => r.aw - r.al, render: r => `${r.aw}-${r.al}`},
    {label: 'Υπ', num: true, title: 'Πόντοι υπέρ', sort: r => r.pf, render: r => r.pf},
    {label: 'Κατ', num: true, title: 'Πόντοι κατά', sort: r => r.pa, render: r => r.pa});
  cols.push(
    {label: '+/-', num: true, sort: r => r.diff, render: r => signed(r.diff)},
    {label: '%', num: true, sort: r => r.pct, render: r => Math.round(r.pct * 100) + '%'},
    {label: 'Φόρμα', info: compact ? null : 'form', render: r => formChips(r.form)});
  if (!compact) cols.push({label: 'Σερί', num: true, render: r => streakGr(r.streak)});
  cols.push({label: 'Elo', num: true, info: 'elo', sort: r => r.elo, render: r => r.elo});
  return table(cols, D.standings, {sortIdx: 0, dir: 1, rowClass: r => r.team === state.focus ? 'is-focus' : null});
}

function nextRoundSection(link = true) {
  const nr = D.next;
  return h('section', null,
    sectionHead('Επόμενη αγωνιστική', nr.length ? `${dayLabel(nr[0].d)} – ${dayLabel(nr[nr.length - 1].d)} · προβλεπόμενο σκορ και πιθανότητα νίκης` : '',
      link ? h('a', {href: url('predictions')}, 'Όλες οι προβλέψεις →') : infoDot('prob')),
    nr.length ? h('div', {class: 'cards'}, nr.map(predCard)) : h('p', {class: 'empty'}, 'Δεν υπάρχουν προγραμματισμένοι αγώνες.'));
}

/** Confident (≥ HIT_THRESHOLD) correct calls, most confident first. */
function hitsSorted() {
  return played.filter(g => outcome(g)?.hit).sort((a, b) => favProb(b.pick) - favProb(a.pick) || b.d.localeCompare(a.d));
}

pages.home = () => {
  const graded = preGameLog.filter(r => r.ok !== null), pending = preGameLog.length - graded.length;
  const correct = graded.filter(r => r.ok).length;
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  const hits = hitsSorted();
  const fs = STANDING[state.focus];
  const focusNext = D.upcoming.find(u => isFocus(u.home, u.away));
  const focusPred = focusNext && focusNext.pi >= 0 ? D.next[focusNext.pi] : null;
  const feat = D.next.find(p => isFocus(p.home, p.away)) || D.next[0];
  return [
    hero(feat),
    played.length ? h('section', null,
      sectionHead('Αποτελέσματα vs Πρόβλεψη', null, h('a', {href: url('predictions', 'all')}, 'Όλοι οι αγώνες →')),
      resultsTicker(played.slice(0, 14))) : null,
    h('section', null, sectionHead('Πώς τα πάει το μοντέλο', null, h('a', {href: url('model')}, 'Λεπτομέρειες →')),
      h('div', {class: 'kpis'},
      kpi('Ακρίβεια μοντέλου', pct(M.acc), `σε ${M.n_test} αγώνες εκτός δείγματος · Elo μόνο ${pct(M.elo_acc)}`, {info: 'acc', count: {to: Math.round(M.acc * 100), fmt: 'pct'}}),
      kpi('🔥 Σίγουρες προβλέψεις', conf.length ? `${confOk}/${conf.length}` : '–', conf.length ? `${pct(confOk / conf.length)} σωστές όταν το μοντέλο λέει ≥ ${HIT_THRESHOLD * 100}%` : 'καμία ακόμα', {info: 'hit', gold: true}),
      kpi('Ρεκόρ προβλέψεων', graded.length ? `${correct}/${graded.length}` : '–', graded.length ? `${pct(correct / graded.length)} σωστοί · ${pending} σε αναμονή` : `${pending} σε αναμονή`, {info: 'record'}),
      kpi('Σφάλμα διαφοράς', `±${M.margin_mae}`, `πόντοι κατά μέσο όρο · σύνολο ±${M.total_mae}`, {info: 'mae', count: {to: M.margin_mae, dec: 1, fmt: 'pm'}}))),
    nextRoundSection(),
    hits.length ? h('section', null,
      sectionHead('🔥 Hall of Fame', `${hits.length} σίγουρες προβλέψεις που βγήκαν`, h('a', {href: url('predictions', 'hits')}, 'Όλες →')),
      h('div', {class: 'hof'}, hits.slice(0, 6).map(hofCard))) : null,
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Βαθμολογία', season, h('a', {href: url('standings')}, 'Πλήρης →')), standingsTable(true)),
      h('div', {class: 'stack'},
        fs ? h('section', {class: 'panel'}, sectionHead(h('span', {style: 'display:inline-flex;gap:10px;align-items:center'}, crest(state.focus, 24), state.focus), `η ομάδα σου · ${fs.pos}ος · ${fs.w}-${fs.l}`, h('a', {href: teamHref(state.focus)}, 'Σελίδα ομάδας →')),
          h('div', {class: 'tile-row'}, h('span', null, 'Φόρμα'), formChips(fs.form)),
          h('div', {class: 'tile-row'}, h('span', null, 'Elo'), h('b', null, fs.elo)),
          h('div', {class: 'tile-row'}, h('span', null, 'Πόντοι / αγώνα'), h('span', null, `${(fs.pf / fs.gp).toFixed(1)} υπέρ · ${(fs.pa / fs.gp).toFixed(1)} κατά`)),
          focusNext ? h('div', {class: 'tile-row'}, h('span', null, 'Επόμενος'), h('span', null, `${dayLabel(focusNext.d)} · ${focusNext.home === state.focus ? 'vs ' + focusNext.away : '@ ' + focusNext.home}`)) : null,
          focusPred ? h('div', {class: 'tile-row'}, h('span', null, 'Πρόβλεψη'), h('b', null, `${focusPred.phs}–${focusPred.pas} · ${state.focus} ${pct(focusPred.home === state.focus ? focusPred.p : 1 - focusPred.p)}`)) : null) : null,
        h('section', {class: 'panel'}, sectionHead('Elo', 'δύναμη σε σχέση με το 1500', infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'bars'})))),
    h('section', {class: 'panel'}, sectionHead('Πρόβλεψη και αποτέλεσμα, αναλυτικά', 'οι 10 τελευταίοι αγώνες · 🔥 = σίγουρη επιτυχία · 🎯 = διαφορά μέσα σε ±3', h('a', {href: url('predictions', 'all')}, 'Όλοι οι αγώνες →')),
      resultsTable(played.slice(0, 10))),
  ];
};
