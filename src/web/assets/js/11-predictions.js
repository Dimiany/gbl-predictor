// page: predictions — tabs: next round · logged history · hits · every game.

function historyTab() {
  const box = h('div');
  const st = {season: '', team: '', status: 'all', model: ''};
  const seasons = [...new Set(D.log.map(r => r.s))].sort().reverse();
  const versions = [...new Set(D.log.map(r => r.v))];
  const isHit = r => r.ok && Math.max(r.p, 1 - r.p) >= HIT_THRESHOLD;
  const draw = () => {
    const rows = D.log.filter(r => (!st.season || r.s === st.season) && (!st.team || r.home === st.team || r.away === st.team)
      && (!st.model || r.v === st.model)
      && (st.status === 'all' || (st.status === 'ok' && r.ok === true) || (st.status === 'bad' && r.ok === false)
        || (st.status === 'pending' && r.ok === null) || (st.status === 'hit' && isHit(r))));
    const graded = rows.filter(r => r.ok !== null), ok = graded.filter(r => r.ok).length;
    const errs = graded.map(r => marginErr(r, r.ahs, r.aas));
    const totalErrs = graded.filter(r => r.phs != null && r.pas != null && r.ahs != null && r.aas != null)
      .map(r => Math.abs((r.phs + r.pas) - (r.ahs + r.aas)));
    const mae = errs.length ? (errs.reduce((a, b) => a + b, 0) / errs.length).toFixed(1) : null;
    const totalMae = totalErrs.length ? (totalErrs.reduce((a, b) => a + b, 0) / totalErrs.length).toFixed(1) : null;
    box.replaceChildren(
      h('p', {class: 'summary-line'}, graded.length
        ? `${ok}/${graded.length} αγώνες με σωστή πρόβλεψη νικητή (${pct(ok / graded.length)}) · μέσο σφάλμα διαφοράς ${mae} πόντοι · ${rows.length - graded.length} σε αναμονή`
        : `${rows.length} προβλέψεις σε αναμονή`),
      h('p', {class: 'summary-line'}, totalMae == null ? '' : `Μέσο σφάλμα συνολικού σκορ: ${totalMae} πόντοι.`),
      table([
        {label: 'Ημέρα', area: 'date', sort: r => r.d, render: r => dayLabel(r.d)},
        {label: 'Αγώνας', area: 'match', sort: r => r.home, render: r => h('span', {style: 'display:inline-flex;gap:8px;align-items:center'}, tlink(r.home), h('span', {class: 'muted'}, '–'), tlink(r.away))},
        {label: 'Πρόβλεψη', area: 'pred', cap: true, num: true, render: r => h('b', null, `${r.phs}–${r.pas}`)},
        {label: 'Νικητής πρόβλεψης · πιθανότητα', area: 'win', cap: 'Νικητής', info: 'prob', sort: r => Math.max(r.p, 1 - r.p), render: r => `${r.w} ${pctProb(r.w === r.home ? r.p : 1 - r.p)}`},
        {label: 'Αποτέλεσμα', area: 'result', cap: true, num: true, render: r => r.ahs == null ? h('span', {class: 'muted'}, '–') : h('span', {class: 'score-cell'}, `${r.ahs}–${r.aas}`)},
        {label: 'Σφάλμα διαφοράς', area: 'err', cap: true, num: true, info: 'mae', sort: r => r.ahs == null ? 999 : marginErr(r, r.ahs, r.aas), render: r => r.ahs == null ? '' : `${marginErr(r, r.ahs, r.aas)} π.`},
        {label: h('span', {class: 'total-heading'}, h('span', null, 'Σύνολο πόντων'), h('small', null, 'πρόβλεψη → τελικό')), area: 'total', cap: 'Σύνολο πόντων · πρόβλεψη → τελικό', num: true, info: 'totalmae', sort: r => r.ahs == null || r.phs == null ? 999 : Math.abs((r.phs + r.pas) - (r.ahs + r.aas)), render: r => {
          if (r.ahs == null || r.phs == null) return '';
          const predicted = r.phs + r.pas, actual = r.ahs + r.aas, error = Math.abs(predicted - actual);
          return h('span', {class: 'total-points'}, h('span', null, h('small', null, 'Πρόβλεψη'), predicted), h('span', null, h('small', null, 'Τελικό'), actual), h('small', null, `Διαφορά ${error} π.`));
        }},
        {label: 'Κατάσταση', area: 'out', cap: true, render: r => h('span', {class: 'history-status'}, verdict(r.ok), isHit(r) ? hitBadge(Math.max(r.p, 1 - r.p)) : null,
          r.ok && r.ahs != null && marginErr(r, r.ahs, r.aas) <= SHARP_POINTS ? sharpBadge(marginErr(r, r.ahs, r.aas)) : null)},
        {label: 'Μοντέλο', hideSm: true, render: r => h('span', {class: 'badge', style: 'margin:0', title: `καταγράφηκε ${r.at}`}, r.v)},
      ], rows, {sortIdx: 0, dir: -1, empty: 'Καμία πρόβλεψη με αυτά τα φίλτρα.', cards: 'log', paged: true,
        rowClass: r => [isFocus(r.home, r.away) ? 'is-focus' : '', isHit(r) ? 'hit' : ''].join(' ').trim() || null}));
  };
  const filters = h('div', {class: 'filters'},
    selectEl([['', 'Όλες οι σεζόν'], ...seasons.map(x => [x, x])], st.season, v => { st.season = v; draw(); }, 'Σεζόν'),
    selectEl([['', 'Όλες οι ομάδες'], ...TEAMS.slice().sort().map(t => [t, t])], st.team, v => { st.team = v; draw(); }, 'Ομάδα'),
    segCtrl([['all', 'Όλες'], ['hit', '🔥 Σίγουρες'], ['ok', 'Σωστές'], ['bad', 'Λάθος'], ['pending', 'Σε αναμονή']], st.status, v => { st.status = v; draw(); }),
    versions.length > 1 ? selectEl([['', 'Όλα τα μοντέλα'], ...versions.map(v => [v, v])], st.model, v => { st.model = v; draw(); }, 'Μοντέλο') : null);
  draw();
  return [h('section', {class: 'panel'}, sectionHead('Ιστορικό προβλέψεων', 'καταγράφηκαν πριν από τους αγώνες', infoDot('record')), filters, box,
    h('p', {class: 'foot-note'}, 'Κάθε γραμμή δείχνει την πρόβλεψη και το τελικό σκορ. Η φλόγα 🔥 δείχνει ότι το φαβορί είχε πιθανότητα ≥80% και κέρδισε. 🎯 σημαίνει ότι η προβλεπόμενη διαφορά απείχε έως 3 πόντους από την πραγματική. Το «ensemble-v1» είναι το παλιό μοντέλο (μέχρι 05/10/2026).'))];
}

function hitsTab() {
  const hits = hitsSorted();
  const conf = confidentPicks();
  const sharp = played.filter(g => outcome(g)?.sharp);
  return [
    h('section', {class: 'kpis'},
      kpi('🔥 Επιτυχίες ≥80%', String(hits.length), `από ${conf.length} προβλέψεις με πιθανότητα ≥80% (${conf.length ? pct(hits.length / conf.length) : '–'})`, {gold: true, info: 'hit', count: {to: hits.length}}),
      kpi('🎯 Ακριβείς διαφορές', String(sharp.length), `σωστός νικητής και διαφορά μέσα σε ±${SHARP_POINTS} πόντους`, {count: {to: sharp.length}, info: 'mae'}),
      kpi('Υψηλότερη πιθανότητα', hits.length ? pctProb(favProb(hits[0].pick)) : '–', hits.length ? `${hits[0].home} – ${hits[0].away}, ${dayLabel(hits[0].d)}` : '')),
    hits.length ? h('div', {class: 'hof'}, hits.map(hofCard)) : h('p', {class: 'empty'}, 'Δεν υπάρχει ακόμη επιτυχία σε πρόβλεψη υψηλής πιθανότητας.'),
    sharp.length ? h('section', {class: 'panel'}, sectionHead('🎯 Μικρό σφάλμα διαφοράς', `ο νικητής προβλέφθηκε σωστά και η διαφορά απείχε έως ${SHARP_POINTS} πόντους`), resultsTable(sharp)) : null,
  ];
}

/** Banner box: which round is predicted next, and when. */
function nextRoundBox() {
  if (!D.next.length) return null;
  return h('a', {class: 'round-box', href: url('predictions')},
    h('small', null, 'Προβλέψεις επόμενης αγωνιστικής'),
    h('b', null, `${roundNo}η αγωνιστική`),
    h('span', null, `${nextRoundDates()} · ${D.next.length} αγώνες`));
}

pages.predictions = ({tab}) => [
  pageBanner('Προβλέψεις', 'Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα, με το ακριβές σκορ, και βαθμολογείται μόλις βγει το αποτέλεσμα.', nextRoundBox()),
  tabs('predictions', [
    {key: 'next', label: 'Επόμενη αγωνιστική', count: D.next.length, render: () => [nextRoundSection(false)]},
    {key: 'history', label: 'Ιστορικό', count: D.log.length, render: historyTab},
    {key: 'hits', label: '🔥 Επιτυχίες ≥80%', count: hitsSorted().length, render: hitsTab},
    {key: 'all', label: 'Όλοι οι αγώνες', count: played.length, render: () => [h('section', {class: 'panel'},
      sectionHead('Όλοι οι αγώνες', 'με την πρόβλεψη του μοντέλου'), resultsTable(played))]},
  ], tab, k => url('predictions', k)),
];
