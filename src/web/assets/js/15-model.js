// page: model — tabs: performance · metrics guide · how it works.

function performanceTab() {
  const wf = played.filter(g => g.pick && g.pick.src === 'wf');
  const bins = calibrationBins(wf);
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  return [
    h('section', {class: 'kpis'},
      kpi(T('Σωστή πρόβλεψη νικητή', 'Winner called correctly'), pct(M.acc), T(`${M.n_test} αγώνες · αν κέρδιζε πάντα ο γηπεδούχος: ${pct(M.home_rate)}`, `${M.n_test} games · if the home team always won: ${pct(M.home_rate)}`), {info: 'acc', count: {to: Math.round(M.acc * 100), fmt: 'pct'}}),
      kpi(T('🔥 Υψηλή πιθανότητα (≥80%)', '🔥 High confidence (≥80%)'), conf.length ? `${confOk}/${conf.length}` : '–', conf.length ? T(`${pct(confOk / conf.length)} σωστές`, `${pct(confOk / conf.length)} correct`) : '', {info: 'hit', gold: true}),
      kpi('Log-loss', fx(M.ll), T(`χαμηλότερο = καλύτερο · Elo μόνο ${fx(M.elo_ll)}`, `lower = better · Elo alone ${fx(M.elo_ll)}`), {info: 'logloss', count: {to: M.ll, dec: 3}}),
      kpi('Brier', fx(M.brier), T(`0.25 = κορόνα-γράμματα · Elo ${fx(M.elo_brier)}`, `0.25 = a coin flip · Elo ${fx(M.elo_brier)}`), {info: 'brier', count: {to: M.brier, dec: 3}}),
      kpi(T('Μέσο σφάλμα διαφοράς', 'Average margin error'), `${M.margin_mae}`, T(`πόντοι · R² ${fx(M.margin_r2, 2)}`, `points · R² ${fx(M.margin_r2, 2)}`), {info: 'mae', count: {to: M.margin_mae, dec: 1}})),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel'}, sectionHead(T('Βαθμονόμηση', 'Calibration'), T('αληθεύουν τα ποσοστά;', 'do the percentages hold up?'), infoDot('calibration')), h('div', {class: 'chart', 'data-chart': 'cal'}),
        h('p', {class: 'foot-note'}, T('Κάθε σημείο ομαδοποιεί αγώνες όπου το φαβορί είχε παρόμοια πιθανότητα νίκης· ο αριθμός δείχνει πόσοι αγώνες περιλαμβάνονται. Για παράδειγμα, σε αγώνες με πιθανότητα 70%, το φαβορί θα πρέπει να κερδίζει περίπου 7 στους 10. Όσο πιο κοντά βρίσκονται τα σημεία στη διαγώνιο, τόσο καλύτερα ταιριάζουν οι πιθανότητες του μοντέλου με τα αποτελέσματα.', 'Each point groups games where the favourite had a similar chance of winning; the number shows how many games it holds. In games at 70%, for example, the favourite should win about 7 in 10. The closer the points are to the diagonal, the better the model\'s probabilities match the results.'))),
      h('section', {class: 'panel'}, sectionHead(T('Επιτυχίες ανά πιθανότητα', 'Hits by probability'), T('Πόσο συχνά κερδίζει το φαβορί σε κάθε εύρος πιθανότητας;', 'How often does the favourite win in each probability range?')),
        table([
          {label: T('Πιθανότητα', 'Probability'), render: b => `${pct(b.a)}–${pct(Math.min(1, b.b))}`},
          {label: T('Αγώνες', 'Games'), num: true, render: b => b.n},
          {label: T('Μέση πρόβλεψη', 'Average prediction'), num: true, render: b => pct(b.sp / b.n)},
          {label: T('Νίκες', 'Wins'), num: true, render: b => h('b', null, pct(b.won / b.n))},
        ], bins, {rowClass: b => b.a >= HIT_THRESHOLD ? 'hit' : null}),
        h('p', {class: 'foot-note'}, T('Σε κάθε αγώνα, η πρόβλεψη έγινε μόνο με βάση όσα αποτελέσματα ήταν γνωστά μέχρι τότε.', 'For every game, the prediction used only the results known up to then.')))),
  ];
}

function metricsTab() {
  return [
    h('p', {class: 'lede'}, T('Τι σημαίνει κάθε νούμερο του site, με απλά λόγια, και πού βρίσκεται τώρα το μοντέλο. Σε όλο το site, το κουμπί ⓘ σε φέρνει εδώ.', 'What every number on the site means, in plain words, and where the model stands now. Anywhere on the site, the ⓘ button brings you here.')),
    h('div', {class: 'grid-3'}, Object.entries(METRICS).map(([key, m]) => h('article', {class: 'metric-card', id: `metric-${key}`},
      h('div', {class: 'm-icon', 'aria-hidden': 'true'}, m.icon), h('h3', null, m.title), h('p', null, m.long),
      h('div', {class: 'm-good'}, m.good),
      h('div', {class: 'm-now'}, h('span', null, T('Τώρα', 'Now')), h('b', null, m.now()))))),
  ];
}

function howTab() {
  return [
    h('div', {class: 'timeline'},
      [['📡', T('Δεδομένα', 'Data'), T('Συγκεντρώνουμε τα αποτελέσματα και το πρόγραμμα των αγώνων.', 'We collect the results and the fixture list.')],
        ['🏆', T('Elo & φόρμα', 'Elo & form'), T('Η βαθμολογία Elo δείχνει τη δυναμικότητα κάθε ομάδας και αλλάζει μετά από κάθε αγώνα. Στις προβλέψεις υπολογίζουμε επίσης τη φόρμα της στα 5 τελευταία παιχνίδια και το ποσοστό νικών της στη σεζόν.', 'The Elo rating shows how strong each team is and changes after every game. The predictions also use each team\'s form over its last 5 games and its win percentage this season.')],
        ['🧠', T('Μοντέλο', 'Model'), T('Το μοντέλο συνδυάζει τη δυναμικότητα, την πρόσφατη πορεία και τα αποτελέσματα της σεζόν για να εκτιμήσει τη διαφορά πόντων, το πιθανό σκορ και την πιθανότητα νίκης.', 'The model combines strength, recent form and the season\'s results to estimate the point margin, the likely score and the win probability.')],
        ['🎯', T('Πρόβλεψη', 'Prediction'), T('Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα και αξιολογείται μετά το αποτέλεσμά του.', 'Every prediction is recorded before the game and graded after the result.')],
      ].map(([icon, title, text]) => h('div', {class: 't-step'}, h('div', {class: 't-ico', 'aria-hidden': 'true'}, icon), h('h3', null, title), h('p', null, text)))),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel howto'}, sectionHead(T('Γιατί τόσο απλό;', 'Why so simple?')),
        h('p', null, T('Με ~180 αγώνες ιστορικού, τα πολύπλοκα μοντέλα «αποστηθίζουν» τον θόρυβο. Σε δοκιμή σε όλο το ιστορικό, το gradient boosting έβγαλε τις χειρότερες πιθανότητες, ενώ η απλή εξίσωση έφτασε τον καλύτερο συνδυασμό.', 'With ~180 games of history, complex models memorise the noise. Tested across the whole history, gradient boosting gave the worst probabilities, while the simple equation gave the best balance.')),
        h('p', null, T('Επίσης, επειδή το σκορ και η πιθανότητα βγαίνουν από την ίδια διαφορά, δεν μπορούν ποτέ να διαφωνούν για τον νικητή.', 'And because the score and the probability come from the same margin, they can never disagree about the winner.'))),
      h('section', {class: 'panel howto'}, sectionHead(T('Εκδόσεις μοντέλου', 'Model versions')),
        h('dl', {class: 'glossary'},
          h('dt', null, M.version), h('dd', null, T('Γραμμικό μοντέλο διαφοράς πόντων, από 05/10/2026.', 'Linear point-margin model, since 5 Oct 2026.')),
          h('dt', null, 'ensemble-v1'), h('dd', null, T('Gradient boosting + Elo, μέχρι 05/10/2026. Οι προβλέψεις του μένουν στο ιστορικό με αυτή την ετικέτα.', 'Gradient boosting + Elo, until 5 Oct 2026. Its predictions stay in the history under this label.'))))),
  ];
}

pages.model = ({tab}) => [
  pageBanner(T('Το μοντέλο', 'The model'), T(`Έκδοση ${M.version} · πόσο καλά προβλέπει, τι σημαίνει κάθε δείκτης και πώς δουλεύει`, `Version ${M.version} · how well it predicts, what each metric means and how it works`)),
  tabs('model', [
    {key: 'performance', label: T('Απόδοση', 'Performance'), render: performanceTab},
    {key: 'metrics', label: T('Οδηγός δεικτών', 'Metrics guide'), count: Object.keys(METRICS).length, render: metricsTab},
    {key: 'how', label: T('Πώς δουλεύει', 'How it works'), render: howTab},
  ], tab, k => url('model', k)),
];
