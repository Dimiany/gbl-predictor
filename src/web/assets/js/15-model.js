// page: model — tabs: performance · metrics guide · how it works.

function performanceTab() {
  const wf = played.filter(g => g.pick && g.pick.src === 'wf');
  const bins = calibrationBins(wf);
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  return [
    h('section', {class: 'kpis'},
      kpi('Σωστή πρόβλεψη νικητή', pct(M.acc), `${M.n_test} αγώνες · αν κέρδιζε πάντα ο γηπεδούχος: ${pct(M.home_rate)}`, {info: 'acc', count: {to: Math.round(M.acc * 100), fmt: 'pct'}}),
      kpi('🔥 Υψηλή πιθανότητα (≥80%)', conf.length ? `${confOk}/${conf.length}` : '–', conf.length ? `${pct(confOk / conf.length)} σωστές` : '', {info: 'hit', gold: true}),
      kpi('Log-loss', fx(M.ll), `χαμηλότερο = καλύτερο · Elo μόνο ${fx(M.elo_ll)}`, {info: 'logloss', count: {to: M.ll, dec: 3}}),
      kpi('Brier', fx(M.brier), `0.25 = κορόνα-γράμματα · Elo ${fx(M.elo_brier)}`, {info: 'brier', count: {to: M.brier, dec: 3}}),
      kpi('Μέσο σφάλμα διαφοράς', `${M.margin_mae}`, `πόντοι · R² ${fx(M.margin_r2, 2)}`, {info: 'mae', count: {to: M.margin_mae, dec: 1}})),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel'}, sectionHead('Βαθμονόμηση', 'αληθεύουν τα ποσοστά;', infoDot('calibration')), h('div', {class: 'chart', 'data-chart': 'cal'}),
        h('p', {class: 'foot-note'}, 'Κάθε σημείο ομαδοποιεί αγώνες όπου το φαβορί είχε παρόμοια πιθανότητα νίκης· ο αριθμός δείχνει πόσοι αγώνες περιλαμβάνονται. Για παράδειγμα, σε αγώνες με πιθανότητα 70%, το φαβορί θα πρέπει να κερδίζει περίπου 7 στους 10. Όσο πιο κοντά βρίσκονται τα σημεία στη διαγώνιο, τόσο καλύτερα ταιριάζουν οι πιθανότητες του μοντέλου με τα αποτελέσματα.')),
      h('section', {class: 'panel'}, sectionHead('Επιτυχίες ανά πιθανότητα', 'Πόσο συχνά κερδίζει το φαβορί σε κάθε εύρος πιθανότητας;'),
        table([
          {label: 'Πιθανότητα φαβορί', render: b => `${pct(b.a)}–${pct(Math.min(1, b.b))}`},
          {label: 'Αγώνες', num: true, render: b => b.n},
          {label: 'Μέση πρόβλεψη', num: true, render: b => pct(b.sp / b.n)},
          {label: 'Νίκες φαβορί', num: true, render: b => h('b', null, pct(b.won / b.n))},
          {label: '', hideSm: true, render: b => h('div', {class: 'meter', style: 'width:120px'}, h('i', {'data-w': pct(b.won / b.n)}))},
        ], bins, {rowClass: b => b.a >= HIT_THRESHOLD ? 'hit' : null}),
        h('p', {class: 'foot-note'}, 'Σε κάθε αγώνα, η πρόβλεψη έγινε μόνο με βάση όσα αποτελέσματα ήταν γνωστά μέχρι τότε.'))),
  ];
}

function metricsTab() {
  return [
    h('p', {class: 'lede'}, 'Τι σημαίνει κάθε νούμερο του site, με απλά λόγια, και πού βρίσκεται τώρα το μοντέλο. Σε όλο το site, το κουμπί ⓘ σε φέρνει εδώ.'),
    h('div', {class: 'grid-3'}, Object.entries(METRICS).map(([key, m]) => h('article', {class: 'metric-card', id: `metric-${key}`},
      h('div', {class: 'm-icon', 'aria-hidden': 'true'}, m.icon), h('h3', null, m.title), h('p', null, m.long),
      h('div', {class: 'm-good'}, m.good),
      h('div', {class: 'm-now'}, h('span', null, 'Τώρα'), h('b', null, m.now()))))),
  ];
}

function howTab() {
  return [
    h('div', {class: 'timeline'},
      [['📡', 'Δεδομένα', 'Συγκεντρώνουμε τα αποτελέσματα και το πρόγραμμα των αγώνων.'],
        ['🏆', 'Elo & φόρμα', 'Η βαθμολογία Elo δείχνει τη δυναμικότητα κάθε ομάδας και αλλάζει μετά από κάθε αγώνα. Στις προβλέψεις υπολογίζουμε επίσης τη φόρμα της στα 5 τελευταία παιχνίδια και το ποσοστό νικών της στη σεζόν.'],
        ['🧠', 'Μοντέλο', `Μία γραμμική εξίσωση προβλέπει τη διαφορά πόντων: ${M.intercept} + ${M.coef[0]}×ΔElo + ${M.coef[1]}×Δφόρμα + ${M.coef[2]}×Δ%νικών.`],
        ['🎯', 'Πρόβλεψη', `Από τη διαφορά υπολογίζονται η πιθανότητα, Φ(διαφορά / ${M.sigma}), και το σκορ. Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα και αξιολογείται μετά.`],
      ].map(([icon, title, text]) => h('div', {class: 't-step'}, h('div', {class: 't-ico', 'aria-hidden': 'true'}, icon), h('h3', null, title), h('p', null, text)))),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel howto'}, sectionHead('Γιατί τόσο απλό;'),
        h('p', null, 'Με ~180 αγώνες ιστορικού, τα πολύπλοκα μοντέλα «αποστηθίζουν» τον θόρυβο. Σε δοκιμή σε όλο το ιστορικό, το gradient boosting έβγαλε τις χειρότερες πιθανότητες, ενώ η απλή εξίσωση έφτασε τον καλύτερο συνδυασμό.'),
        h('p', null, 'Επίσης, επειδή το σκορ και η πιθανότητα βγαίνουν από την ίδια διαφορά, δεν μπορούν ποτέ να διαφωνούν για τον νικητή.')),
      h('section', {class: 'panel howto'}, sectionHead('Εκδόσεις μοντέλου'),
        h('dl', {class: 'glossary'},
          h('dt', null, M.version), h('dd', null, 'Γραμμικό μοντέλο διαφοράς πόντων, από 05/10/2026.'),
          h('dt', null, 'ensemble-v1'), h('dd', null, 'Gradient boosting + Elo, μέχρι 05/10/2026. Οι προβλέψεις του μένουν στο ιστορικό με αυτή την ετικέτα.')))),
  ];
}

pages.model = ({tab}) => [
  pageBanner('Το μοντέλο', `Έκδοση ${M.version} · πόσο καλά προβλέπει, τι σημαίνει κάθε δείκτης και πώς δουλεύει`),
  tabs('model', [
    {key: 'performance', label: 'Απόδοση', render: performanceTab},
    {key: 'metrics', label: 'Οδηγός δεικτών', count: Object.keys(METRICS).length, render: metricsTab},
    {key: 'how', label: 'Πώς δουλεύει', render: howTab},
  ], tab, k => url('model', k)),
];
