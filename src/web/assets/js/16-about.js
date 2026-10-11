// page: about — what this is, how it works, disclaimer.

pages.about = () => {
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  return [
    pageBanner(T('Σχετικά', 'About'), T('Ένα ανεξάρτητο εργαλείο προβλέψεων για την Stoiximan Basket League, χτισμένο με δεδομένα και διαφάνεια.', 'An independent prediction tool for the Stoiximan Basket League, built on data and transparency.')),
    h('section', {class: 'panel'}, h('div', {class: 'about-hero-grid'},
      h('div', {class: 'howto'},
        h('h2', {style: 'margin-bottom:10px'}, T(`Τι είναι το ${BRAND.name}`, `What ${BRAND.name} is`)),
        h('p', null, h('b', null, `${BRAND.name} · ${BRAND.tagline}.`), T(` ${BRAND.slogan} Το όνομα TipOff σημαίνει «τζάμπολ», δηλαδή την έναρξη του αγώνα. Οι προβλέψεις δημοσιεύονται πριν από αυτόν.`, ` ${BRAND.slogan} The tip-off is the jump ball that starts a game, and the predictions are published before it.`)),
        h('p', null, T(`Πριν από κάθε αγωνιστική, το ${BRAND.name} υπολογίζει για κάθε αγώνα την πιθανότητα νίκης και εκτιμά το σκορ. Μετά τον αγώνα, ελέγχουμε και δημοσιεύουμε πόσο σωστή ήταν η πρόβλεψη. Κάθε πρόβλεψη καταγράφεται πριν από το τζάμπολ, ώστε να μην αλλάζει εκ των υστέρων.`, `Before every round, ${BRAND.name} works out each game's win probability and estimates the score. After the game, we check and publish how right the prediction was. Every prediction is recorded before tip-off, so it can't be changed afterwards.`)),
        h('p', null, T('Οι προβλέψεις βασίζονται στα διαθέσιμα στατιστικά στοιχεία: τη δύναμη των ομάδων (Elo), τη φόρμα και την έδρα, όχι σε προσωπικές εκτιμήσεις. Παράγοντες που δεν περιλαμβάνονται στα δεδομένα, όπως ένας τραυματισμός, μπορεί να μην αποτυπώνονται.', 'The predictions rest on the available statistics: team strength (Elo), form and home court, not on personal opinion. Things the data doesn\'t include, such as an injury, may not be reflected.')),
        h('div', {class: 'pill-list'}, [T('Βαθμολογία Elo', 'Elo ratings'), T('Αξιολόγηση σε παλιότερους αγώνες', 'Tested on past games'), T('Βαθμονομημένες πιθανότητες', 'Calibrated probabilities'), T('Ανοιχτή μεθοδολογία', 'Open method'), T('Χωρίς στοιχήματα', 'No betting')].map(t => h('span', {class: 'pill'}, t)))),
      h('div', {class: 'kpis', style: 'grid-template-columns:1fr 1fr'},
        kpi(T('Αγώνες ιστορικού', 'Games in history'), String(played.length), T(`${season} + προηγούμενη σεζόν`, `${season} + previous season`), {count: {to: played.length}}),
        kpi(T('Ακρίβεια', 'Accuracy'), pct(M.acc), T('σε αγώνες που δεν είχε δει το μοντέλο', 'on games the model hadn\'t seen'), {count: {to: Math.round(M.acc * 100), fmt: 'pct'}, info: 'acc'}),
        kpi(T('🔥 Υψηλή πιθανότητα', '🔥 High confidence'), conf.length ? `${confOk}/${conf.length}` : '–', T('≥ 80% και σωστές', '≥ 80% and correct'), {gold: true}),
        kpi(T('Ομάδες', 'Teams'), String(TEAMS.length), `Basket League ${season}`, {count: {to: TEAMS.length}})))),
    h('section', null, sectionHead(T('Πώς δουλεύει, σε 4 βήματα', 'How it works, in 4 steps'), null, h('a', {href: url('model', 'how')}, T('Λεπτομέρειες →', 'Details →'))), howTab()[0]),
    h('section', {class: 'panel howto'}, sectionHead(T('Δήλωση αποποίησης ευθύνης', 'Disclaimer')),
      h('p', null, T('Ανεξάρτητη, μη επίσημη εφαρμογή. Δεν έχει σχέση με την ΕΣΑΚΕ, τη Stoiximan ή τις ομάδες. Τα λογότυπα και τα ονόματα ανήκουν στους κατόχους τους.', 'An independent, unofficial app. It has no connection with ESAKE, Stoiximan or the clubs. Logos and names belong to their owners.')),
      h('p', null, h('b', null, T('Δεν είναι συμβουλή στοιχηματισμού.', 'This is not betting advice.')), T(' Οι πιθανότητες είναι εκτιμήσεις με αβεβαιότητα: ένα «80%» σημαίνει ότι περίπου 1 στις 5 φορές θα χάσει το φαβορί.', ' The probabilities are uncertain estimates: "80%" means the favourite will lose about 1 time in 5.'))),
  ];
};
