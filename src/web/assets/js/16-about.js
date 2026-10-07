// page: about — what this is, how it works, sources, disclaimer.

pages.about = () => {
  const conf = confidentPicks(), confOk = conf.filter(g => outcome(g).ok).length;
  return [
    pageBanner('Σχετικά', 'Ένα ανεξάρτητο εργαλείο προβλέψεων για την Stoiximan Basket League, χτισμένο με δεδομένα και διαφάνεια.'),
    h('section', {class: 'panel'}, h('div', {class: 'about-hero-grid'},
      h('div', {class: 'howto'},
        h('h2', {style: 'margin-bottom:10px'}, `Τι είναι το ${BRAND.name}`),
        h('p', null, h('b', null, `${BRAND.name} · ${BRAND.tagline}.`), ` ${BRAND.slogan} Το όνομα είναι το «τζάμπολ» στα αγγλικά: οι προβλέψεις βγαίνουν πριν ξεκινήσει ο αγώνας.`),
        h('p', null, `Πριν από κάθε αγωνιστική, το ${BRAND.name} βγάζει για κάθε αγώνα πιθανότητα νίκης και προβλεπόμενο σκορ. Μετά τον αγώνα, βαθμολογεί δημόσια τον εαυτό του. Κάθε πρόβλεψη καταγράφεται πριν από το τζάμπολ, οπότε το ρεκόρ δεν μπορεί να «διορθωθεί» εκ των υστέρων.`),
        h('p', null, 'Όλα όσα βλέπεις υπολογίζονται από τα αποτελέσματα: δύναμη ομάδων (Elo), φόρμα, έδρα. Δεν μπαίνει καμία «αίσθηση» ή γνώμη. Όπου το μοντέλο δεν ξέρει, π.χ. για έναν τραυματισμό, το λέει, και μπορείς να το διορθώσεις.'),
        h('div', {class: 'pill-list'}, ['Elo ratings', 'Walk-forward αξιολόγηση', 'Βαθμονομημένες πιθανότητες', 'Ανοιχτή μεθοδολογία', 'Χωρίς στοιχήματα'].map(t => h('span', {class: 'pill'}, t)))),
      h('div', {class: 'kpis', style: 'grid-template-columns:1fr 1fr'},
        kpi('Αγώνες ιστορικού', String(played.length), `${season} + προηγούμενη σεζόν`, {count: {to: played.length}}),
        kpi('Ακρίβεια', pct(M.acc), 'εκτός δείγματος', {count: {to: Math.round(M.acc * 100), fmt: 'pct'}, info: 'acc'}),
        kpi('🔥 Σίγουρες', conf.length ? `${confOk}/${conf.length}` : '–', '≥ 80% και σωστές', {gold: true}),
        kpi('Ομάδες', String(TEAMS.length), `Basket League ${season}`, {count: {to: TEAMS.length}})))),
    h('section', null, sectionHead('Πώς δουλεύει, σε 4 βήματα', null, h('a', {href: url('model', 'how')}, 'Λεπτομέρειες →')), howTab()[0]),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel howto'}, sectionHead('Πηγές δεδομένων'),
        h('dl', {class: 'glossary'},
          h('dt', null, 'Αποτελέσματα & πρόγραμμα'), h('dd', null, 'FlashScore μέσω RapidAPI, ενημέρωση με το κουμπί «Ανανέωση».'),
          h('dt', null, 'Σήματα ομάδων'), h('dd', null, 'Από το ίδιο API (FlashScore CDN).'),
          h('dt', null, 'Χρώματα'), h('dd', null, 'Εμπνευσμένα από την ταυτότητα της Stoiximan GBL.'))),
      h('section', {class: 'panel howto'}, sectionHead('Αποποίηση'),
        h('p', null, 'Ανεπίσημη, ερασιτεχνική εφαρμογή. Δεν έχει σχέση με την ΕΣΑΚΕ, τη Stoiximan ή τις ομάδες. Τα σήματα και τα ονόματα ανήκουν στους κατόχους τους.'),
        h('p', null, h('b', null, 'Δεν είναι συμβουλή στοιχηματισμού.'), ' Οι πιθανότητες είναι εκτιμήσεις με αβεβαιότητα: ένα «80%» σημαίνει ότι περίπου 1 στις 5 φορές θα χάσει το φαβορί.'))),
  ];
};
