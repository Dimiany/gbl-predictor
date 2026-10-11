// page: predictions — tabs: next round · logged history · hits · every game.

const HISTORY_WINNER_SHORT = {
  Olympiacos: 'ΟΣΦΠ', Panathinaikos: 'ΠΑΟ', AEK: 'ΑΕΚ', PAOK: 'ΠΑΟΚ', Aris: 'ΑΡΗΣ',
  'AS Karditsas Iaponiki': 'ΚΑΡΔ.', 'Doxa Lefkadas': 'ΔΟΞΑ', Iraklis: 'ΗΡΑΚ.',
  'Kolossos Rodou': 'ΚΟΛ.', Maroussi: 'ΜΑΡ.', Mykonos: 'ΜΥΚ.',
  Panionios: 'ΠΑΝ.', Peristeri: 'ΠΕΡ.', 'Promitheas Vikos Cola': 'ΠΡΟΜ.',
  'Vikos Falcons Ioanninon': 'ΒΙΚΟΣ',
};
const HISTORY_WINNER_SHORT_EN = {
  Olympiacos: 'OLY', Panathinaikos: 'PAO', AEK: 'AEK', PAOK: 'PAOK', Aris: 'ARIS',
  'AS Karditsas Iaponiki': 'KAR', 'Doxa Lefkadas': 'DOXA', Iraklis: 'IRA',
  'Kolossos Rodou': 'KOL', Maroussi: 'MAR', Mykonos: 'MYK',
  Panionios: 'PAN', Peristeri: 'PER', 'Promitheas Vikos Cola': 'PROM',
  'Vikos Falcons Ioanninon': 'VIKOS',
};
const winnerShort = t => (ENGLISH ? HISTORY_WINNER_SHORT_EN : HISTORY_WINNER_SHORT)[t] || tn(t);

function historyTab() {
  const box = h('div');
  const st = {season: '', team: '', status: 'all', model: ''};
  const seasons = [...new Set(D.log.map(r => r.s))].sort().reverse();
  const versions = [...new Set(D.log.map(r => r.v))];
  const isHit = r => r.ok && Math.max(r.p, 1 - r.p) >= HIT_THRESHOLD;
  // Each round's record over all its logged predictions (not just the filtered rows:
  // filtering by "correct" would always show 100%).
  const roundRecord = {};
  D.log.forEach(r => {
    const rec = roundRecord[roundOf(r.d).key] ??= {ok: 0, graded: 0};
    if (r.ok !== null) { rec.graded++; if (r.ok) rec.ok++; }
  });
  const roundGroup = r => {
    const g = roundOf(r.d), rec = roundRecord[g.key];
    const note = rec.graded
      ? h('span', {class: 'g-note', title: T('Σωστές προβλέψεις νικητή στην αγωνιστική', 'Winners called correctly in this round')},
        h('b', null, `${rec.ok}/${rec.graded}`), ` · ${pct(rec.ok / rec.graded)}`)
      : h('span', {class: 'g-note muted'}, T('σε αναμονή', 'pending'));
    return {...g, note};
  };
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
        ? T(`${ok}/${graded.length} αγώνες με σωστή πρόβλεψη νικητή (${pct(ok / graded.length)}) · μέσο σφάλμα διαφοράς ${mae} πόντοι · ${rows.length - graded.length} σε αναμονή`,
          `${ok}/${graded.length} games with the winner called correctly (${pct(ok / graded.length)}) · average margin error ${mae} points · ${rows.length - graded.length} pending`)
        : T(`${rows.length} προβλέψεις σε αναμονή`, `${rows.length} predictions pending`)),
      h('p', {class: 'summary-line'}, totalMae == null ? '' : T(`Μέσο σφάλμα συνολικού σκορ: ${totalMae} πόντοι.`, `Average total-score error: ${totalMae} points.`)),
      table([
        {label: T('Ημέρα', 'Date'), area: 'date', sort: r => r.d, render: r => dayLabel(r.d)},
        {label: T('Αγώνας', 'Game'), area: 'match', sort: r => r.home, render: r => h('span', {class: 'match-cell'}, h('span', {class: 'm-home'}, tlink(r.home)), h('span', {class: 'muted'}, '–'), h('span', {class: 'm-away'}, tlink(r.away)))},
        {label: h('span', {class: 'history-heading'}, T('Πρόβλεψη', 'Prediction'), h('small', null, T('σκορ · νικητής', 'score · winner'))), area: 'pred', cap: T('Πρόβλεψη · σκορ και νικητής', 'Prediction · score and winner'), sort: r => Math.max(r.p, 1 - r.p), render: r => h('span', {class: 'history-detail'}, h('b', null, `${r.phs}–${r.pas}`), h('small', {title: tn(r.w)}, `${winnerShort(r.w)} · ${pctProb(r.w === r.home ? r.p : 1 - r.p)}`))},
        {label: h('span', {class: 'history-heading'}, T('Αποτέλεσμα', 'Result'), h('small', null, T('τελικό σκορ · απόκλιση', 'final score · margin error'))), area: 'result', cap: T('Αποτέλεσμα · τελικό σκορ και απόκλιση', 'Result · final score and margin error'), sort: r => r.ahs == null ? 999 : marginErr(r, r.ahs, r.aas), render: r => r.ahs == null ? h('span', {class: 'muted'}, '–') : h('span', {class: 'history-detail'}, h('b', null, `${r.ahs}–${r.aas}`), h('small', null, T(`Απόκλιση ${marginErr(r, r.ahs, r.aas)} π.`, `Off by ${marginErr(r, r.ahs, r.aas)} pts`)))},
        {label: h('span', {class: 'total-heading'}, h('span', null, T('Σύνολο πόντων', 'Total points')), h('small', null, T('πρόβλεψη → τελικό', 'predicted → final'))), area: 'total', cap: T('Σύνολο πόντων · πρόβλεψη → τελικό', 'Total points · predicted → final'), sort: r => r.ahs == null || r.phs == null ? 999 : Math.abs((r.phs + r.pas) - (r.ahs + r.aas)), render: r => {
          if (r.ahs == null || r.phs == null) return '';
          const predicted = r.phs + r.pas, actual = r.ahs + r.aas, error = Math.abs(predicted - actual);
          return h('span', {class: 'total-points'}, h('span', null, h('small', null, T('Πρόβλεψη', 'Predicted')), predicted), h('span', null, h('small', null, T('Τελικό', 'Final')), actual), h('small', null, T(`Διαφορά ${error} π.`, `Off by ${error} pts`)));
        }},
        {label: T('Κατάσταση', 'Status'), area: 'out', cap: true, render: r => h('span', {class: 'history-status'}, verdict(r.ok), isHit(r) ? hitBadge(Math.max(r.p, 1 - r.p)) : null,
          r.ok && r.ahs != null && marginErr(r, r.ahs, r.aas) <= SHARP_POINTS ? sharpBadge(marginErr(r, r.ahs, r.aas)) : null)},
        {label: T('Μοντέλο', 'Model'), hideSm: true, render: r => h('span', {class: 'badge', style: 'margin:0', title: T(`καταγράφηκε ${r.at}`, `recorded ${r.at}`)}, r.v)},
      ], rows, {sortIdx: 0, dir: -1, empty: T('Καμία πρόβλεψη με αυτά τα φίλτρα.', 'No predictions match these filters.'), cards: 'log', paged: true,
        group: {col: 0, of: roundGroup},
        rowClass: r => [isFocus(r.home, r.away) ? 'is-focus' : '', isHit(r) ? 'hit' : ''].join(' ').trim() || null}));
  };
  const filters = h('div', {class: 'filters'},
    selectEl([['', T('Όλες οι σεζόν', 'All seasons')], ...seasons.map(x => [x, x])], st.season, v => { st.season = v; draw(); }, T('Σεζόν', 'Season')),
    selectEl([['', T('Όλες οι ομάδες', 'All teams')], ...teamOptions()], st.team, v => { st.team = v; draw(); }, T('Ομάδα', 'Team')),
    segCtrl([['all', T('Όλες', 'All')], ['hit', T('🔥 Σίγουρες', '🔥 Confident')], ['ok', T('Σωστές', 'Correct')], ['bad', T('Λάθος', 'Wrong')], ['pending', T('Σε αναμονή', 'Pending')]], st.status, v => { st.status = v; draw(); }),
    versions.length > 1 ? selectEl([['', T('Όλα τα μοντέλα', 'All models')], ...versions.map(v => [v, v])], st.model, v => { st.model = v; draw(); }, T('Μοντέλο', 'Model')) : null);
  draw();
  return [h('section', {class: 'panel'}, sectionHead(T('Ιστορικό προβλέψεων', 'Prediction history'), T('καταγράφηκαν πριν από τους αγώνες', 'recorded before the games'), infoDot('record')), filters, box,
    h('p', {class: 'foot-note'}, T('Κάθε γραμμή δείχνει την πρόβλεψη και το τελικό σκορ. Η φλόγα 🔥 δείχνει ότι το φαβορί είχε πιθανότητα ≥80% και κέρδισε. 🎯 σημαίνει ότι η προβλεπόμενη διαφορά απείχε έως 3 πόντους από την πραγματική. Το «ensemble-v1» είναι το παλιό μοντέλο (μέχρι 05/10/2026).', 'Each row shows the prediction and the final score. The flame 🔥 means the favourite had a ≥80% chance and won. 🎯 means the predicted margin was within 3 points of the real one. "ensemble-v1" is the old model (until 5 Oct 2026).')))];
}

function hitsTab() {
  const hits = hitsSorted();
  const conf = confidentPicks();
  const sharp = played.filter(g => outcome(g)?.sharp);
  return [
    h('section', {class: 'kpis'},
      kpi(T('🔥 Επιτυχίες ≥80%', '🔥 Hits ≥80%'), String(hits.length), T(`από ${conf.length} προβλέψεις με πιθανότητα ≥80% (${conf.length ? pct(hits.length / conf.length) : '–'})`, `of ${conf.length} predictions at ≥80% probability (${conf.length ? pct(hits.length / conf.length) : '–'})`), {gold: true, info: 'hit', count: {to: hits.length}}),
      kpi(T('🎯 Ακριβείς διαφορές', '🎯 Accurate margins'), String(sharp.length), T(`σωστός νικητής και διαφορά μέσα σε ±${SHARP_POINTS} πόντους`, `right winner and margin within ±${SHARP_POINTS} points`), {count: {to: sharp.length}, info: 'mae'}),
      kpi(T('Υψηλότερη πιθανότητα', 'Highest probability'), hits.length ? pctProb(favProb(hits[0].pick)) : '–', hits.length ? `${tn(hits[0].home)} – ${tn(hits[0].away)}, ${dayLabel(hits[0].d)}` : '')),
    hits.length ? h('div', {class: 'hof'}, hits.map(hofCard)) : h('p', {class: 'empty'}, T('Δεν υπάρχει ακόμη επιτυχία σε πρόβλεψη υψηλής πιθανότητας.', 'No high-confidence hits yet.')),
    sharp.length ? h('section', {class: 'panel'}, sectionHead(T('🎯 Μικρό σφάλμα διαφοράς', '🎯 Small margin error'), T(`ο νικητής προβλέφθηκε σωστά και η διαφορά απείχε έως ${SHARP_POINTS} πόντους`, `the winner was right and the margin was within ${SHARP_POINTS} points`)), resultsTable(sharp)) : null,
  ];
}

/** Banner box: which round is predicted next, and when. */
function nextRoundBox() {
  if (!D.next.length) return null;
  return h('a', {class: 'round-box', href: url('predictions')},
    h('small', null, T('Προβλέψεις επόμενης αγωνιστικής', 'Next round predictions')),
    h('b', null, T(`${roundNo}η αγωνιστική`, `Round ${roundNo}`)),
    h('span', null, `${nextRoundDates()} · ${nGames(D.next.length)}`));
}

pages.predictions = ({tab}) => [
  pageBanner(T('Προβλέψεις', 'Predictions'), T('Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα, με το ακριβές σκορ, και βαθμολογείται μόλις βγει το αποτέλεσμα.', 'Every prediction is recorded before the game, with an exact score, and graded as soon as the result is in.'), nextRoundBox()),
  tabs('predictions', [
    {key: 'next', label: T('Επόμενη αγωνιστική', 'Next round'), count: D.next.length, render: () => [nextRoundSection(false)]},
    {key: 'history', label: T('Ιστορικό', 'History'), count: D.log.length, render: historyTab},
    {key: 'hits', label: T('🔥 Επιτυχίες ≥80%', '🔥 Hits ≥80%'), count: hitsSorted().length, render: hitsTab},
    {key: 'all', label: T('Όλοι οι αγώνες', 'All games'), count: played.length, render: () => [h('section', {class: 'panel'},
      sectionHead(T('Όλοι οι αγώνες', 'All games'), T('με την πρόβλεψη του μοντέλου', 'with the model\'s prediction')), resultsTable(played))]},
  ], tab, k => url('predictions', k)),
];
