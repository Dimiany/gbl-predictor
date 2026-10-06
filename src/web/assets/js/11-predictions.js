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
        || (st.status === 'pending' && r.ok === null) || (st.status === 'hit' && isHit(r)) || (st.status === 'retro' && r.retro)));
    const graded = rows.filter(r => r.ok !== null), ok = graded.filter(r => r.ok).length;
    const errs = graded.map(r => marginErr(r, r.ahs, r.aas));
    const mae = errs.length ? (errs.reduce((a, b) => a + b, 0) / errs.length).toFixed(1) : null;
    box.replaceChildren(
      h('p', {class: 'summary-line'}, graded.length
        ? `${ok}/${graded.length} σωστοί νικητές (${pct(ok / graded.length)}) · μέση απόκλιση διαφοράς ${mae} πόντοι · ${rows.length - graded.length} σε αναμονή`
        : `${rows.length} προβλέψεις σε αναμονή`),
      table([
        {label: 'Ημέρα', sort: r => r.d, render: r => dayLabel(r.d)},
        {label: 'Αγώνας', sort: r => r.home, render: r => h('span', {style: 'display:inline-flex;gap:8px;align-items:center'}, tlink(r.home), h('span', {class: 'muted'}, '–'), tlink(r.away))},
        {label: 'Πρόβλεψη', num: true, render: r => h('b', null, `${r.phs}–${r.pas}`)},
        {label: 'Νικητής (πιθ.)', info: 'prob', sort: r => Math.max(r.p, 1 - r.p), render: r => `${r.w} ${pctProb(r.w === r.home ? r.p : 1 - r.p)}`},
        {label: 'Αποτέλεσμα', num: true, render: r => r.ahs == null ? h('span', {class: 'muted'}, '–') : h('span', {class: 'score-cell'}, `${r.ahs}–${r.aas}`)},
        {label: 'Απόκλιση', num: true, info: 'mae', sort: r => r.ahs == null ? 999 : marginErr(r, r.ahs, r.aas), render: r => r.ahs == null ? '' : `${marginErr(r, r.ahs, r.aas)} π.`},
        {label: '', render: r => h('span', {style: 'display:inline-flex;gap:6px;align-items:center'}, verdict(r.ok), r.retro ? retroBadge() : null, isHit(r) ? hitBadge(Math.max(r.p, 1 - r.p)) : null,
          r.ok && r.ahs != null && marginErr(r, r.ahs, r.aas) <= SHARP_POINTS ? sharpBadge(marginErr(r, r.ahs, r.aas)) : null)},
        {label: 'Μοντέλο', render: r => h('span', {class: 'badge', style: 'margin:0', title: `καταγράφηκε ${r.at}`}, r.v)},
      ], rows, {sortIdx: 0, dir: -1, empty: 'Καμία πρόβλεψη με αυτά τα φίλτρα.',
        rowClass: r => [isFocus(r.home, r.away) ? 'is-focus' : '', isHit(r) ? 'hit' : ''].join(' ').trim() || null}));
  };
  const filters = h('div', {class: 'filters'},
    selectEl([['', 'Όλες οι σεζόν'], ...seasons.map(x => [x, x])], st.season, v => { st.season = v; draw(); }, 'Σεζόν'),
    selectEl([['', 'Όλες οι ομάδες'], ...TEAMS.slice().sort().map(t => [t, t])], st.team, v => { st.team = v; draw(); }, 'Ομάδα'),
    segCtrl([['all', 'Όλες'], ['hit', '🔥 Σίγουρες'], ['ok', 'Σωστές'], ['bad', 'Λάθος'], ['pending', 'Σε αναμονή'],
      ...(D.log.some(r => r.retro) ? [['retro', 'Αναδρομικές']] : [])], st.status, v => { st.status = v; draw(); }),
    versions.length > 1 ? selectEl([['', 'Όλα τα μοντέλα'], ...versions.map(v => [v, v])], st.model, v => { st.model = v; draw(); }, 'Μοντέλο') : null);
  draw();
  return [h('section', {class: 'panel'}, sectionHead('Ιστορικό προβλέψεων', 'καταγράφηκαν πριν από τους αγώνες', infoDot('record')), filters, box,
    h('p', {class: 'foot-note'}, 'Κάθε γραμμή είναι πρόβλεψη που καταγράφηκε πριν από τον αγώνα, με το ακριβές σκορ που έδωσε το μοντέλο. Χρυσό = σίγουρη πρόβλεψη (≥ 80%) που βγήκε. 🎯 = η διαφορά έπεσε μέσα σε 3 πόντους. Το «ensemble-v1» είναι το παλιό μοντέλο (μέχρι 05/10/2026). «Αναδρομική» = βγήκε μετά τον αγώνα από μοντέλο που είδε μόνο τους προηγούμενους αγώνες (1η αγωνιστική 2026/27). Φαίνεται εδώ, αλλά δεν μετράει στο ρεκόρ.'))];
}

function hitsTab() {
  const hits = hitsSorted();
  const conf = confidentPicks();
  const sharp = played.filter(g => outcome(g)?.sharp);
  return [
    h('section', {class: 'kpis'},
      kpi('🔥 Σίγουρες επιτυχίες', String(hits.length), `από ${conf.length} σίγουρες προβλέψεις (${conf.length ? pct(hits.length / conf.length) : '–'})`, {gold: true, info: 'hit', count: {to: hits.length}}),
      kpi('🎯 Ακριβείς διαφορές', String(sharp.length), `σωστός νικητής και διαφορά μέσα σε ±${SHARP_POINTS} πόντους`, {count: {to: sharp.length}, info: 'mae'}),
      kpi('Πιο σίγουρη', hits.length ? pctProb(favProb(hits[0].pick)) : '–', hits.length ? `${hits[0].home} – ${hits[0].away}, ${dayLabel(hits[0].d)}` : '')),
    hits.length ? h('div', {class: 'hof'}, hits.map(hofCard)) : h('p', {class: 'empty'}, 'Καμία σίγουρη επιτυχία ακόμα.'),
    sharp.length ? h('section', {class: 'panel'}, sectionHead('🎯 Ακριβείς διαφορές', `η προβλεπόμενη διαφορά απείχε ≤ ${SHARP_POINTS} πόντους`), resultsTable(sharp)) : null,
  ];
}

pages.predictions = ({tab}) => [
  pageBanner('Προβλέψεις', 'Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα, με το ακριβές σκορ, και βαθμολογείται μόλις βγει το αποτέλεσμα.'),
  tabs('predictions', [
    {key: 'next', label: 'Επόμενη αγωνιστική', count: D.next.length, render: () => [nextRoundSection(false)]},
    {key: 'history', label: 'Ιστορικό', count: D.log.length, render: historyTab},
    {key: 'hits', label: '🔥 Επιτυχίες', count: hitsSorted().length, render: hitsTab},
    {key: 'all', label: 'Όλοι οι αγώνες', count: played.length, render: () => [h('section', {class: 'panel'},
      sectionHead('Όλοι οι αγώνες', 'με την πρόβλεψη του μοντέλου'), resultsTable(played),
      h('p', {class: 'foot-note'}, '«Πριν τον αγώνα»: καταγεγραμμένη πρόβλεψη. «Αναδρομική»: βγήκε μετά, από μοντέλο που είδε μόνο τους αγώνες πριν από την αγωνιστική. «Walk-forward»: πρόβλεψη από μοντέλο εκπαιδευμένο μόνο σε προηγούμενους αγώνες, άρα κι αυτή εκτός δείγματος.'))]},
  ], tab, 'predictions'),
];
