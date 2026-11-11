// page: help — how to use the app without ever touching a terminal.
// The desktop app gets the full manual; the public site only what visitors need.
// The desktop manual is for the site's owner and stays in Greek; the public part has both.

function cloudHelp() {
  return h('section', {class: 'panel howto'}, sectionHead('Η δημόσια έκδοση του site'),
    h('p', null, 'Υπάρχει και δημόσια έκδοση, ώστε να τη βλέπεις από το κινητό ή να τη μοιράζεσαι με φίλους. Ενημερώνεται αυτόματα: ελέγχει καθημερινά για νέα αποτελέσματα και προγραμματισμένους αγώνες. Όταν χρειάζεται, ενημερώνει τα αποτελέσματα και καταγράφει προβλέψεις πριν από τους αγώνες. Το GitHub κάνει όλη τη δουλειά, και ο υπολογιστής σου δεν χρειάζεται να είναι ανοιχτός.'),
    h('ul', null,
      h('li', null, h('b', null, 'Ενημέρωση τώρα:'), ' στο github.com, στο repo → Actions → «Site» → Run workflow → Run workflow.'),
      h('li', null, h('b', null, 'Μηνύματα της φόρμας:'), ' console.firebase.google.com → Firestore Database → contact_messages.'),
      h('li', null, h('b', null, 'Αλλαγές στο site:'), ' τις βλέπεις πρώτα στο δοκιμαστικό site, πάντα στο ίδιο link: gbl-predictor-test.web.app (με κίτρινη λωρίδα). Ανεβαίνουν στο κανονικό μόνο όταν πεις «ναι».')),
    h('p', null, 'Σε αυτή την εφαρμογή, το ', h('span', {class: 'kbd'}, '⟳ Ανανέωση'), ' φέρνει τα δεδομένα που ενημέρωσε το GitHub, ώστε εφαρμογή και site να δείχνουν ακριβώς τα ίδια.'));
}

function publicHelp() {
  return [
    pageBanner(T('Οδηγίες', 'Help'), T('Πώς να διαβάσεις το site.', 'How to read the site.')),
    h('section', {class: 'panel howto'}, sectionHead(T('Ενημέρωση', 'Updates')),
      h('p', null, T('Το site ελέγχει καθημερινά για νέα αποτελέσματα και προγραμματισμένους αγώνες. Όταν χρειάζεται, ενημερώνει τα αποτελέσματα και καταγράφει προβλέψεις πριν από τους αγώνες.', 'The site checks every day for new results and scheduled games. When needed, it updates the results and records predictions before the games.'))),
    siteGuide(),
  ];
}

function siteGuide() {
  return h('section', {class: 'panel howto'}, sectionHead(T('Τι θα βρεις', 'What you\'ll find')),
    h('dl', {class: 'glossary'},
      ...[[url('home'), T('Αρχική', 'Home'), T('Η επόμενη αγωνιστική, οι επιτυχίες σε προβλέψεις υψηλής πιθανότητας, η βαθμολογία και τα τελευταία αποτελέσματα.', 'The next round, the high-confidence hits, the standings and the latest results.')],
        [url('predictions'), T('Προβλέψεις', 'Predictions'), T('Καρτέλες: Επόμενη αγωνιστική, ιστορικό με φίλτρα, 🔥 επιτυχίες, όλοι οι αγώνες.', 'Tabs: next round, history with filters, 🔥 hits, all games.')],
        [url('standings'), T('Βαθμολογία', 'Standings'), T('Πλήρης πίνακας με ταξινόμηση, Elo και η εξέλιξή του. Καρτέλα «Πιθανότητες σεζόν»: τίτλος, πλέι-οφ και υποβιβασμός από χιλιάδες προσομοιώσεις.', 'The full sortable table, Elo and how it has moved. The "Season projections" tab: title, playoff and relegation chances from thousands of simulations.')],
        [url('teams'), T('Ομάδες', 'Teams'), T('Σελίδα για κάθε ομάδα: επισκόπηση, αποτελέσματα, πρόγραμμα.', 'A page for every team: overview, results, schedule.')],
        [url('schedule'), T('Πρόγραμμα', 'Schedule'), T('Όλοι οι αγώνες ανά μήνα ή ανά ομάδα.', 'Every game by month or by team.')],
        [url('model'), T('Μοντέλο', 'Model'), T('Απόδοση, ο οδηγός με όλους τους δείκτες, και πώς δουλεύει.', 'Performance, the guide to every metric, and how it works.')],
      ].flatMap(([href, title, text]) => [h('dt', null, h('a', {class: 'tlink', href}, h('span', {class: 'tname'}, title))), h('dd', null, text)]),
      h('dt', null, 'EN / ΕΛ'), h('dd', null, T('Το κουμπί πάνω δεξιά (στο κινητό: Μενού → English) ανοίγει την ίδια σελίδα στα αγγλικά.', 'The button at the top right (on phones: Menu → Ελληνικά) opens the same page in Greek.')),
      h('dt', null, T('Η ομάδα μου', 'My team')), h('dd', null, T('Το μενού πάνω δεξιά τονίζει την ομάδα σου παντού. Το ◐ αλλάζει ανάμεσα σε σκοτεινό και φωτεινό θέμα.', 'The menu at the top right highlights your team everywhere. ◐ switches between the dark and light themes.')),
    ));
}

pages.help = () => PUBLIC ? publicHelp() : [
  pageBanner('Οδηγίες', 'Όλα γίνονται με κλικ, χωρίς εντολές.'),
  h('section', {class: 'panel howto'}, sectionHead('Κάθε φορά'),
    h('ol', {class: 'steps'},
      h('li', null, h('b', null, `Διπλό κλικ στο εικονίδιο «${BRAND.name}»`), ' στην επιφάνεια εργασίας. Ανοίγει ένα μαύρο παράθυρο και, μετά από λίγα δευτερόλεπτα, αυτή η σελίδα. Αν έχουν περάσει πάνω από 6 ώρες από την τελευταία φορά, φέρνει πρώτα μόνο του τα νέα αποτελέσματα (~20 δευτερόλεπτα). Το VS Code δεν χρειάζεται.'),
      h('li', null, h('b', null, 'Μην κλείσεις το μαύρο παράθυρο'), ' όσο χρησιμοποιείς τη σελίδα. Αυτό κάνει τα κουμπιά «Ανανέωση» και «Αποστολή» να δουλεύουν.'),
      h('li', null, 'Πάτα ', h('span', {class: 'kbd'}, '⟳ Ανανέωση'), ' πάνω δεξιά για τα πιο φρέσκα δεδομένα. Φέρνει αποτελέσματα και πρόγραμμα, ξαναεκπαιδεύει το μοντέλο, βγάζει και καταγράφει τις προβλέψεις της επόμενης αγωνιστικής.'),
      h('li', null, h('b', null, 'Τέλος:'), ' κλείσε τη σελίδα και το μαύρο παράθυρο.'))),
  SITE.cloud_sync ? null : h('section', {class: 'panel howto'}, sectionHead('Πότε να πατάς Ανανέωση'),
    h('p', null, h('b', null, 'Μία φορά μετά από κάθε αγωνιστική και πριν ξεκινήσει η επόμενη'), ', π.χ. Δευτέρα με Παρασκευή. Έτσι οι προβλέψεις καταγράφονται πριν παιχτούν οι αγώνες, και το ρεκόρ είναι αληθινό.'),
    h('p', null, 'Η υπηρεσία δεδομένων έχει όριο 500 αιτημάτων τον μήνα, και κάθε ανανέωση χρησιμοποιεί περίπου 6–8.')),
  siteGuide(),
  SITE.cloud_sync ? cloudHelp() : null,
  h('section', {class: 'panel howto'}, sectionHead('Αν κάτι δεν πάει καλά'),
    h('dl', {class: 'glossary'},
      h('dt', null, '«API rejected the key»'), h('dd', null, 'Το κλειδί ή η συνδρομή στο RapidAPI έληξε. Κάνε ξανά Subscribe στο FlashScore (δωρεάν πλάνο) και ζήτα από το Claude να βάλει το νέο κλειδί.'),
      h('dt', null, '«rate limit»'), h('dd', null, 'Τελείωσαν οι κλήσεις του μήνα. Η σελίδα δείχνει κανονικά τα τελευταία δεδομένα.'),
      h('dt', null, '«Unmapped team names»'), h('dd', null, 'Το API έφερε όνομα ομάδας που δεν αναγνωρίζεται, συνήθως νέας ομάδας. Πες στο Claude να το προσθέσει.'),
      h('dt', null, 'Τα κουμπιά δεν κάνουν τίποτα'), h('dd', null, `Η σελίδα άνοιξε απευθείας από αρχείο και όχι από το εικονίδιο. Άνοιξέ την από το «${BRAND.name}».`),
      h('dt', null, 'Δεν ανοίγει τίποτα'), h('dd', null, 'Διάβασε τι γράφει το μαύρο παράθυρο και στείλε το στο Claude.'))),
];
