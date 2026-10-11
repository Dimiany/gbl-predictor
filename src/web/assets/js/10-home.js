// page: home — hero, latest results ticker, KPIs, next round, hall of fame, table, results.

function standingsTable(compact) {
  const cols = [
    {label: '#', num: true, sticky: 1, sort: r => r.pos, render: r => h('span', {class: 'pos' + (r.pos <= 8 ? ' top' : '')}, r.pos)},
    {label: T('Ομάδα', 'Team'), sticky: 2, sort: r => r.team, render: r => tlink(r.team)},
    {label: T('Αγ', 'GP'), num: true, title: T('Αγώνες', 'Games played'), sort: r => r.gp, render: r => r.gp},
    {label: T('Ν', 'W'), num: true, title: T('Νίκες', 'Wins'), sort: r => r.w, render: r => r.w},
    {label: T('Η', 'L'), num: true, title: T('Ήττες', 'Losses'), sort: r => r.l, render: r => r.l},
  ];
  if (!compact) cols.push(
    {label: T('Έδρα', 'Home'), num: true, title: T('Νίκες-ήττες εντός', 'Home wins-losses'), sort: r => r.hw - r.hl, render: r => `${r.hw}-${r.hl}`},
    {label: T('Εκτός', 'Away'), num: true, title: T('Νίκες-ήττες εκτός', 'Away wins-losses'), sort: r => r.aw - r.al, render: r => `${r.aw}-${r.al}`},
    {label: T('Υπ', 'PF'), num: true, title: T('Πόντοι υπέρ', 'Points for'), sort: r => r.pf, render: r => r.pf},
    {label: T('Κατ', 'PA'), num: true, title: T('Πόντοι κατά', 'Points against'), sort: r => r.pa, render: r => r.pa});
  cols.push(
    {label: '+/-', num: true, sort: r => r.diff, render: r => signed(r.diff)},
    {label: '%', num: true, sort: r => r.pct, render: r => Math.round(r.pct * 100) + '%'},
    {label: T('Φόρμα', 'Form'), info: compact ? null : 'form', render: r => formChips(r.form)});
  if (!compact) cols.push({label: T('Σερί', 'Streak'), num: true, render: r => streakGr(r.streak)});
  cols.push({label: 'Elo', num: true, info: 'elo', sort: r => r.elo, render: r => r.elo});
  return table(cols, D.standings, {sortIdx: 0, dir: 1, center: true, rowClass: r => r.team === state.focus ? 'is-focus' : null});
}

function nextRoundSection(link = true) {
  const nr = D.next;
  return h('section', null,
    sectionHead(T('Επόμενη αγωνιστική', 'Next round'), nr.length ? `${nextRoundDates()} · ` + T('Προβλεπόμενο σκορ και πιθανότητα νίκης', 'Predicted score and win probability') : '',
      link ? h('a', {href: url('predictions')}, T('Όλες οι προβλέψεις →', 'All predictions →')) : infoDot('prob')),
    nr.length ? h('div', {class: 'cards'}, nr.map(predCard)) : h('p', {class: 'empty'}, T('Δεν υπάρχουν προγραμματισμένοι αγώνες.', 'No games scheduled.')));
}

/** Confident (≥ HIT_THRESHOLD) correct calls, most confident first. */
function hitsSorted() {
  return played.filter(g => outcome(g)?.hit).sort((a, b) => favProb(b.pick) - favProb(a.pick) || b.d.localeCompare(a.d));
}

pages.home = () => {
  const seasonOk = seasonLog.filter(r => r.ok).length;
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  const hits = hitsSorted();
  const fs = STANDING[state.focus];
  const focusNext = D.upcoming.find(u => isFocus(u.home, u.away));
  const focusPred = focusNext && focusNext.pi >= 0 ? D.next[focusNext.pi] : null;
  const feat = D.next.find(p => isFocus(p.home, p.away)) || D.next[0];
  return [
    hero(feat),
    played.length ? h('section', null,
      sectionHead(T('Αποτέλεσμα και πρόβλεψη', 'Result and prediction'), null, h('a', {href: url('predictions', 'all')}, T('Όλοι οι αγώνες →', 'All games →'))),
      resultsTicker(played.slice(0, 14))) : null,
    h('section', null, sectionHead(T('Πώς τα πάει το μοντέλο', 'How the model is doing'), null, h('a', {href: url('model')}, T('Λεπτομέρειες →', 'Details →'))),
      h('div', {class: 'kpis'},
      kpi(T('Ακρίβεια μοντέλου', 'Model accuracy'), pct(M.acc), T(`σε ${M.n_test} αγώνες που δεν είχε δει · Elo μόνο ${pct(M.elo_acc)}`, `over ${M.n_test} games it hadn't seen · Elo alone ${pct(M.elo_acc)}`), {info: 'acc', count: {to: Math.round(M.acc * 100), fmt: 'pct'}}),
      kpi(T('🔥 Υψηλή πιθανότητα', '🔥 High confidence'), conf.length ? `${confOk}/${conf.length}` : '–', conf.length ? T(`${pct(confOk / conf.length)} σωστές προβλέψεις με πιθανότητα ≥ ${HIT_THRESHOLD * 100}%`, `${pct(confOk / conf.length)} correct at ≥ ${HIT_THRESHOLD * 100}% probability`) : T('καμία ακόμα', 'none yet'), {info: 'hit', gold: true}),
      kpi(T(`Τρέχουσα σεζόν ${seasonFull}`, `Season ${seasonFull}`), seasonLog.length ? `${seasonOk}/${seasonLog.length}` : '–', seasonLog.length ? T('Σωστές προβλέψεις', 'Correct predictions') : T('η σεζόν μόλις ξεκίνησε', 'the season has just started'), {info: 'season', count: seasonLog.length ? {to: seasonOk, of: seasonLog.length} : null}),
      kpi(T('Μέσο σφάλμα διαφοράς', 'Average margin error'), `${M.margin_mae}`, T(`πόντοι · συνολικού σκορ: ${M.total_mae} πόντοι`, `points · total score: ${M.total_mae} points`), {info: 'mae', count: {to: M.margin_mae, dec: 1}}))),
    nextRoundSection(),
    hits.length ? h('section', null,
      sectionHead(T('🔥 Επιτυχίες υψηλής πιθανότητας', '🔥 High-confidence hits'), T(`${hits.length} επιτυχημένες προβλέψεις με πιθανότητα ≥80%`, `${hits.length} successful predictions at ≥80% probability`), h('a', {href: url('predictions', 'hits')}, T('Όλες →', 'All →'))),
      h('div', {class: 'hof'}, hits.slice(0, 6).map(hofCard))) : null,
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead(T('Βαθμολογία', 'Standings'), season, h('a', {href: url('standings')}, T('Πλήρης →', 'Full table →'))), standingsTable(true)),
      h('div', {class: 'stack'},
        fs ? h('section', {class: 'panel'}, sectionHead(h('span', {style: 'display:inline-flex;gap:10px;align-items:center'}, crest(state.focus, 24), tn(state.focus)), T(`η ομάδα σου · ${fs.pos}ος · ${fs.w}-${fs.l}`, `your team · ${ordinal(fs.pos)} · ${fs.w}-${fs.l}`), h('a', {href: teamHref(state.focus)}, T('Σελίδα ομάδας →', 'Team page →'))),
          h('div', {class: 'tile-row'}, h('span', null, T('Φόρμα', 'Form')), formChips(fs.form)),
          h('div', {class: 'tile-row'}, h('span', null, 'Elo'), h('b', null, fs.elo)),
          h('div', {class: 'tile-row'}, h('span', null, T('Πόντοι / αγώνα', 'Points / game')), h('span', null, T(`${(fs.pf / fs.gp).toFixed(1)} υπέρ · ${(fs.pa / fs.gp).toFixed(1)} κατά`, `${(fs.pf / fs.gp).toFixed(1)} for · ${(fs.pa / fs.gp).toFixed(1)} against`))),
          focusNext ? h('div', {class: 'tile-row'}, h('span', null, T('Επόμενος αγώνας', 'Next game')), h('span', null, `${dayLabel(focusNext.d)} · ${focusNext.home === state.focus ? T('εντός έδρας με ', 'home vs ') + tn(focusNext.away) : T('εκτός έδρας με ', 'away at ') + tn(focusNext.home)}`)) : null,
          focusPred ? h('div', {class: 'tile-row'}, h('span', null, T('Πρόβλεψη', 'Prediction')), h('b', null, `${focusPred.phs}–${focusPred.pas} · ${tn(state.focus)} ${pct(focusPred.home === state.focus ? focusPred.p : 1 - focusPred.p)}`)) : null) : null,
        h('section', {class: 'panel'}, sectionHead('Elo', T('δύναμη σε σχέση με το 1500', 'strength relative to 1500'), infoDot('elo')), h('div', {class: 'chart', 'data-chart': 'bars'})))),
    h('section', {class: 'panel'}, sectionHead(T('Πρόβλεψη και αποτέλεσμα, αναλυτικά', 'Predictions and results in detail'), T('οι 10 τελευταίοι αγώνες · 🔥 = επιτυχία με πιθανότητα ≥80% · 🎯 = σφάλμα διαφοράς έως 3 πόντους', 'the last 10 games · 🔥 = a hit at ≥80% probability · 🎯 = margin error of 3 points or less'), h('a', {href: url('predictions', 'all')}, T('Όλοι οι αγώνες →', 'All games →'))),
      resultsTable(played.slice(0, 10))),
  ];
};
