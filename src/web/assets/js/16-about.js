// page: about — what this is, how it works, sources, disclaimer.

pages.about = () => {
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  return [
    pageBanner('Σχετικά', 'Ένα ανεξάρτητο εργαλείο προβλέψεων για την Stoiximan Basket League, χτισμένο με δεδομένα και διαφάνεια.'),
    h('section', {class: 'panel'}, h('div', {class: 'about-hero-grid'},
      h('div', {class: 'howto'},
        h('h2', {style: 'margin-bottom:10px'}, `Τι είναι το ${BRAND.name}`),
        h('p', null, h('b', null, `${BRAND.name} · ${BRAND.tagline}.`), ` ${BRAND.slogan} Το όνομα TipOff σημαίνει «τζάμπολ», δηλαδή την έναρξη του αγώνα. Οι προβλέψεις δημοσιεύονται πριν από αυτόν.`),
        h('p', null, `Πριν από κάθε αγωνιστική, το ${BRAND.name} υπολογίζει για κάθε αγώνα την πιθανότητα νίκης και εκτιμά το σκορ. Μετά τον αγώνα, ελέγχουμε και δημοσιεύουμε πόσο σωστή ήταν η πρόβλεψη. Κάθε πρόβλεψη καταγράφεται πριν από το τζάμπολ, ώστε να μην αλλάζει εκ των υστέρων.`),
        h('p', null, 'Οι προβλέψεις βασίζονται στα διαθέσιμα στατιστικά στοιχεία: τη δύναμη των ομάδων (Elo), τη φόρμα και την έδρα, όχι σε προσωπικές εκτιμήσεις. Παράγοντες που δεν περιλαμβάνονται στα δεδομένα, όπως ένας τραυματισμός, μπορεί να μην αποτυπώνονται.'),
        h('div', {class: 'pill-list'}, ['Βαθμολογία Elo', 'Αξιολόγηση σε παλιότερους αγώνες', 'Βαθμονομημένες πιθανότητες', 'Ανοιχτή μεθοδολογία', 'Χωρίς στοιχήματα'].map(t => h('span', {class: 'pill'}, t)))),
      h('div', {class: 'kpis', style: 'grid-template-columns:1fr 1fr'},
        kpi('Αγώνες ιστορικού', String(played.length), `${season} + προηγούμενη σεζόν`, {count: {to: played.length}}),
        kpi('Ακρίβεια', pct(M.acc), 'σε αγώνες που δεν είχε δει το μοντέλο', {count: {to: Math.round(M.acc * 100), fmt: 'pct'}, info: 'acc'}),
        kpi('🔥 Υψηλή πιθανότητα', conf.length ? `${confOk}/${conf.length}` : '–', '≥ 80% και σωστές', {gold: true}),
        kpi('Ομάδες', String(TEAMS.length), `Basket League ${season}`, {count: {to: TEAMS.length}})))),
    h('section', null, sectionHead('Πώς δουλεύει, σε 4 βήματα', null, h('a', {href: url('model', 'how')}, 'Λεπτομέρειες →')), howTab()[0]),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel howto'}, sectionHead('Πηγές δεδομένων'),
        h('dl', {class: 'glossary'},
          h('dt', null, 'Αποτελέσματα & πρόγραμμα'), h('dd', null, 'FlashScore μέσω RapidAPI, ενημέρωση με το κουμπί «Ανανέωση».'),
          h('dt', null, 'Λογότυπα ομάδων'), h('dd', null, 'Από το FlashScore.'),
          h('dt', null, 'Χρώματα'), h('dd', null, 'Εμπνευσμένα από την ταυτότητα της Stoiximan GBL.'))),
      h('section', {class: 'panel howto'}, sectionHead('Αποποίηση'),
        h('p', null, 'Ανεξάρτητη, μη επίσημη εφαρμογή. Δεν έχει σχέση με την ΕΣΑΚΕ, τη Stoiximan ή τις ομάδες. Τα λογότυπα και τα ονόματα ανήκουν στους κατόχους τους.'),
        h('p', null, h('b', null, 'Δεν είναι συμβουλή στοιχηματισμού.'), ' Οι πιθανότητες είναι εκτιμήσεις με αβεβαιότητα: ένα «80%» σημαίνει ότι περίπου 1 στις 5 φορές θα χάσει το φαβορί.'))),
  ];
};
