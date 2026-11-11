// metrics — plain-Greek (and plain-English) explanations of every number on the site.
// Used by the ⓘ buttons (tooltip + link) and by the guide tab on the Model page.

const M = D.model;

/** key -> {icon, title, short (tooltip), long (guide), good (how to read it), now()} */
const METRICS = {
  acc: {
    icon: '🎯', title: T('Ακρίβεια νικητή', 'Winner accuracy'),
    short: T('Σε πόσους αγώνες το μοντέλο βρήκε τον νικητή.', 'How many games the model called the winner of.'),
    long: T('Το ποσοστό των αγώνων όπου κέρδισε η ομάδα με την υψηλότερη πιθανότητα νίκης. Η αξιολόγηση γίνεται με παλιότερους αγώνες: κάθε αγώνας προβλέπεται μόνο με βάση όσα είχαν γίνει πριν από αυτόν.',
      'The share of games won by the team the model gave the higher chance of winning. It is measured on past games: each game is predicted only from what had happened before it.'),
    good: T(`Σημεία αναφοράς: 50% = κορόνα-γράμματα, ${pct(M.home_rate)} = το ποσοστό νικών της ομάδας που παίζει εντός έδρας. Σε ~120 αγώνες, διαφορές 3–4 μονάδων μπορεί να οφείλονται στην τύχη.`,
      `Benchmarks: 50% = a coin flip, ${pct(M.home_rate)} = how often the home team wins. Over ~120 games, differences of 3–4 points can be down to luck.`),
    now: () => pct(M.acc),
  },
  hit: {
    icon: '🔥', title: T('Επιτυχίες σε προβλέψεις υψηλής πιθανότητας', 'High-confidence hits'),
    short: T(`Προβλέψεις όπου το φαβορί είχε πιθανότητα νίκης ≥ ${HIT_THRESHOLD * 100}% και κέρδισε.`, `Predictions where the favourite had a ≥ ${HIT_THRESHOLD * 100}% chance of winning and won.`),
    long: T(`Πόσο συχνά κερδίζει το φαβορί όταν το μοντέλο τού δίνει πιθανότητα νίκης ≥ ${HIT_THRESHOLD * 100}%; Αυτές οι επιτυχίες σημειώνονται με τη φλόγα 🔥 στο site. Αν το μοντέλο υπολογίζει σωστά τις πιθανότητες, περίπου 8–9 από τις 10 τέτοιες προβλέψεις πρέπει να είναι σωστές.`,
      `How often does the favourite win when the model gives it a ≥ ${HIT_THRESHOLD * 100}% chance? These hits carry the flame 🔥 across the site. If the model's probabilities are right, about 8–9 in 10 of these predictions should come true.`),
    good: T('Αν είναι σωστές λιγότερες από 8 στις 10, το μοντέλο πιθανόν υπερεκτιμά τις πιθανότητες νίκης.', 'If fewer than 8 in 10 are right, the model is probably overconfident.'),
    now: () => { const c = confidentPicks(); return c.length ? `${c.filter(g => outcome(g).ok).length}/${c.length}` : '–'; },
  },
  record: {
    icon: '📒', title: T('Ρεκόρ καταγεγραμμένων προβλέψεων', 'Recorded prediction record'),
    short: T('Προβλέψεις που αποθηκεύτηκαν πριν από τον αγώνα και βαθμολογήθηκαν μετά.', 'Predictions saved before the game and graded after it.'),
    long: T('Η πιο αυστηρή μέτρηση: πριν από κάθε αγωνιστική, οι προβλέψεις καταγράφονται με ημερομηνία. Μετά τον αγώνα συγκρίνονται με το αποτέλεσμα. Δεν γίνεται να «διορθωθούν» εκ των υστέρων.',
      'The strictest test: before every round, the predictions are recorded with a date. After the game they are compared with the result. They cannot be "fixed" afterwards.'),
    good: T('Μεγαλώνει με κάθε αγωνιστική. Μετά από ~50 αγώνες γίνεται αξιόπιστο μέτρο.', 'It grows with every round. After ~50 games it becomes a reliable measure.'),
    now: () => { const g = preGameLog.filter(r => r.ok !== null); return g.length ? `${g.filter(r => r.ok).length}/${g.length}` : '–'; },
  },
  season: {
    icon: '📅', title: T('Τρέχουσα σεζόν', 'This season'),
    short: T('Σε πόσους από τους φετινούς αγώνες το μοντέλο βρήκε τον νικητή.', 'How many of this season\'s games the model called the winner of.'),
    long: T('Κάθε φετινός αγώνας που έχει παιχτεί, με την πρόβλεψη που είχε βγάλει το μοντέλο γι’ αυτόν. Κάθε πρόβλεψη βγαίνει μόνο από τους αγώνες που είχαν παιχτεί πριν από αυτόν.',
      'Every game played this season, with the prediction the model made for it. Each prediction uses only the games played before it.'),
    good: T('Μεγαλώνει με κάθε αγωνιστική. Στις πρώτες αγωνιστικές ένας αγώνας αλλάζει πολύ το ποσοστό.', 'It grows with every round. In the first rounds a single game moves the percentage a lot.'),
    now: () => seasonLog.length ? `${seasonLog.filter(r => r.ok).length}/${seasonLog.length}` : '–',
  },
  totalmae: {
    icon: 'Σ', title: T('Σφάλμα συνολικού σκορ', 'Total-points error'),
    short: T('Η μέση διαφορά ανάμεσα στο προβλεπόμενο άθροισμα πόντων και στο πραγματικό.', 'The average gap between the predicted and the actual combined score.'),
    long: T('Για κάθε αγώνα, προσθέτουμε τους πόντους των δύο ομάδων στην πρόβλεψη και στο αποτέλεσμα. Το σφάλμα είναι η απόσταση ανάμεσα στα δύο σύνολα, ανεξάρτητα από το ποια ομάδα σκόραρε τους πόντους. Για παράδειγμα, 169 αντί για 194 σημαίνει σφάλμα 25 πόντων.',
      'For each game we add up both teams\' points, in the prediction and in the result. The error is the gap between the two totals, whichever team scored the points. For example, 169 instead of 194 is an error of 25 points.'),
    good: T('Όσο μικρότερο, τόσο πιο κοντά ήταν το προβλεπόμενο συνολικό σκορ. Δεν δείχνει αν προβλέφθηκε σωστά ο νικητής.', 'The smaller, the closer the predicted total. It says nothing about whether the winner was right.'),
    now: () => T(`${M.total_mae} πόντοι`, `${M.total_mae} points`),
  },
  mae: {
    icon: '📏', title: T('Σφάλμα διαφοράς (MAE)', 'Margin error (MAE)'),
    short: T('Πόσους πόντους απέχει κατά μέσο όρο η προβλεπόμενη διαφορά από την πραγματική.', 'How many points, on average, the predicted margin is from the real one.'),
    long: T('Αν το μοντέλο λέει «γηπεδούχος +6» και τελειώνει +10, το σφάλμα είναι 4. Ο μέσος όρος αυτών των σφαλμάτων είναι το MAE. Ακόμα και τα στοιχηματικά γραφεία έχουν ~10 πόντους στο μπάσκετ.',
      'If the model says "home +6" and the game ends +10, the error is 4. The average of these errors is the MAE. Even bookmakers are ~10 points off in basketball.'),
    good: T('Κάτω από 10 = πολύ καλό. 10–12 = καλό. Πάνω από 13 = αδύναμο.', 'Under 10 = very good. 10–12 = good. Over 13 = weak.'),
    now: () => T(`${M.margin_mae} πόντοι`, `${M.margin_mae} points`),
  },
  logloss: {
    icon: '⚖️', title: 'Log-loss',
    short: T('Μετρά πόσο καλές είναι οι πιθανότητες και επιβαρύνει περισσότερο τις λανθασμένες προβλέψεις με υψηλή πιθανότητα.', 'Measures how good the probabilities are, and punishes confident wrong calls the most.'),
    long: T('Αν το μοντέλο πει 90% και χάσει, χάνει πολλούς βαθμούς. Αν πει 55% και χάσει, ελάχιστους. Έτσι ανταμείβονται οι ειλικρινείς πιθανότητες, όχι μόνο το σωστό φαβορί.',
      'If the model says 90% and loses, it loses a lot. If it says 55% and loses, very little. So honest probabilities are rewarded, not just picking the right favourite.'),
    good: T(`0.693 = πάντα 50/50. Κάτω από 0.60 = χρήσιμες πιθανότητες. Κάτω από 0.50 = πολύ καλές. Elo μόνο: ${fx(M.elo_ll)}.`, `0.693 = always 50/50. Under 0.60 = useful probabilities. Under 0.50 = very good. Elo alone: ${fx(M.elo_ll)}.`),
    now: () => fx(M.ll),
  },
  brier: {
    icon: '🧮', title: 'Brier score',
    short: T('Μέσο τετραγωνικό σφάλμα των πιθανοτήτων (0 = τέλειο).', 'Mean squared error of the probabilities (0 = perfect).'),
    long: T('Για κάθε αγώνα: (πιθανότητα − αποτέλεσμα)², όπου αποτέλεσμα 1 αν κέρδισε ο γηπεδούχος, αλλιώς 0. Πιο «ήπιο» από το log-loss, αλλά μετράει το ίδιο πράγμα.',
      'For each game: (probability − result)², where the result is 1 if the home team won, otherwise 0. Gentler than log-loss, but it measures the same thing.'),
    good: T(`0.25 = πάντα 50/50. Κάτω από 0.20 = καλό. Elo μόνο: ${fx(M.elo_brier)}.`, `0.25 = always 50/50. Under 0.20 = good. Elo alone: ${fx(M.elo_brier)}.`),
    now: () => fx(M.brier),
  },
  r2: {
    icon: '📈', title: T('R² διαφοράς', 'Margin R²'),
    short: T('Τι ποσοστό της διακύμανσης στη διαφορά πόντων εξηγεί το μοντέλο.', 'How much of the variation in point margins the model explains.'),
    long: T('Το 1.0 θα σήμαινε τέλεια πρόβλεψη κάθε διαφοράς, το 0 ότι το μοντέλο δεν είναι καλύτερο από το να λέει πάντα τη μέση διαφορά. Στο μπάσκετ, με τόση τύχη, και το 0.3 είναι αξιοπρεπές.',
      '1.0 would mean every margin predicted perfectly, 0 that the model is no better than always guessing the average margin. With so much luck in basketball, even 0.3 is respectable.'),
    good: T('0.15 είναι περίπου το όριο των στοιχηματικών. Πάνω από 0.25 = πολύ καλό.', 'About 0.15 is the bookmakers\' level. Over 0.25 = very good.'),
    now: () => fx(M.margin_r2, 2),
  },
  elo: {
    icon: '🏆', title: 'Elo',
    short: T('Βαθμός δύναμης κάθε ομάδας. Μέσος όρος 1500.', 'A strength rating for each team. The average is 1500.'),
    long: T('Το Elo κάθε ομάδας αλλάζει μετά από κάθε αγώνα, ανάλογα με το αποτέλεσμα και την απόδοσή της.', 'Each team\'s Elo changes after every game, depending on the result and how it played.'),
    good: T('Διαφορά 100 πόντων ≈ 64% πιθανότητα νίκης για τον ισχυρότερο σε ουδέτερο γήπεδο.', 'A 100-point gap ≈ a 64% chance of winning for the stronger team on a neutral court.'),
    now: () => T(`${Math.max(...D.standings.map(r => r.elo))} κορυφή`, `${Math.max(...D.standings.map(r => r.elo))} top`),
  },
  prob: {
    icon: '🎲', title: T('Πιθανότητα νίκης', 'Win probability'),
    short: T(`Φ(διαφορά / ${M.sigma}): πόσο πιθανό είναι να νικήσει κάθε ομάδα.`, `Φ(margin / ${M.sigma}): how likely each team is to win.`),
    long: T(`Το μοντέλο προβλέπει τη διαφορά πόντων και τη μετατρέπει σε πιθανότητα με την κανονική κατανομή (σ = ${M.sigma} πόντοι). Διαφορά +6 ≈ 69%, +12 ≈ 83%, +20 ≈ 95%. Το σκορ και η πιθανότητα βγαίνουν από τον ίδιο αριθμό, γι' αυτό συμφωνούν πάντα.`,
      `The model predicts the point margin and turns it into a probability with the normal distribution (σ = ${M.sigma} points). A margin of +6 ≈ 69%, +12 ≈ 83%, +20 ≈ 95%. The score and the probability come from the same number, so they always agree.`),
    good: T('Κάτω από 60% = ανοιχτός αγώνας. 60–80% = φαβορί. Πάνω από 80% = φαβορί με υψηλή πιθανότητα νίκης (ένδειξη 🔥).', 'Under 60% = an open game. 60–80% = a favourite. Over 80% = a strong favourite (marked 🔥).'),
    now: () => `σ = ${M.sigma}`,
  },
  band: {
    icon: '↔️', title: T('± πόντοι', '± points'),
    short: T('Το εύρος αβεβαιότητας γύρω από το προβλεπόμενο σκορ.', 'The uncertainty range around the predicted score.'),
    long: T('Το «89–79 ±13» σημαίνει ότι η διαφορά των 10 πόντων είναι η καλύτερη εκτίμηση, αλλά κατά κανόνα το πραγματικό αποτέλεσμα πέφτει μέσα σε ±13 πόντους από αυτήν.',
      '"89–79 ±13" means a 10-point margin is the best estimate, but the real result usually lands within ±13 points of it.'),
    good: T('Δεν είναι λάθος του μοντέλου: είναι ο θόρυβος του αθλήματος.', 'This isn\'t the model failing: it\'s the noise of the sport.'),
    now: () => `±${Math.round(M.margin_rmse)}`,
  },
  calibration: {
    icon: '🧭', title: T('Βαθμονόμηση', 'Calibration'),
    short: T('Όταν το μοντέλο λέει 70%, κερδίζει το φαβορί ~70% των φορών;', 'When the model says 70%, does the favourite win ~70% of the time?'),
    long: T('Οι αγώνες ομαδοποιούνται ανά πιθανότητα (50–60%, 60–70%, …) και συγκρίνεται η μέση πρόβλεψη με το πραγματικό ποσοστό νικών. Όσο πιο κοντά είναι τα σημεία στη διαγώνιο, τόσο περισσότερο οι προβλεπόμενες πιθανότητες συμφωνούν με τα αποτελέσματα.',
      'Games are grouped by probability (50–60%, 60–70%, …) and the average prediction is compared with how often the favourite actually won. The closer the points are to the diagonal, the better the probabilities match the results.'),
    good: T('Πάνω από τη διαγώνιο: στην πράξη κερδίζουν συχνότερα τα φαβορί απ’ όσο εκτιμά το μοντέλο. Κάτω από τη διαγώνιο: το μοντέλο δίνει υπερβολικά υψηλές πιθανότητες.',
      'Above the diagonal: favourites win more often than the model expects. Below it: the model\'s probabilities are too high.'),
    now: () => T(`${M.n_test} αγώνες`, `${M.n_test} games`),
  },
  walkforward: {
    icon: '⏩', title: T('Αξιολόγηση με παλιότερους αγώνες', 'Testing on past games'),
    short: T('Κάθε αγώνας προβλέπεται με βάση μόνο τα αποτελέσματα που είχαν προηγηθεί.', 'Each game is predicted only from the results that came before it.'),
    long: T(`Μετά τους πρώτους ${M.warmup} αγώνες, το μοντέλο εκπαιδεύεται μόνο με προηγούμενα αποτελέσματα και προβλέπει τους επόμενους αγώνες. Κάθε αγώνας αξιολογείται με μοντέλο εκπαιδευμένο στα αποτελέσματα που προηγήθηκαν.`,
      `After the first ${M.warmup} games, the model is trained only on earlier results and predicts the games that follow. Every game is graded with a model trained on the results before it.`),
    good: T('Έτσι βγήκαν οι προβλέψεις της προηγούμενης σεζόν που βλέπεις στα αποτελέσματα.', 'This is how the previous season\'s predictions in the results were made.'),
    now: () => T(`${M.n_test} αγώνες`, `${M.n_test} games`),
  },
  form: {
    icon: '📊', title: T('Φόρμα (L5)', 'Form (L5)'),
    short: T('Μέση διαφορά πόντων στους 5 τελευταίους αγώνες.', 'Average point margin over the last 5 games.'),
    long: T('Δείχνει ποιος «ανεβαίνει» και ποιος «πέφτει» πέρα από το Elo. Χρειάζονται τουλάχιστον 3 αγώνες της σεζόν για να μετρήσει, γι\' αυτό στις πρώτες αγωνιστικές το μοντέλο στηρίζεται περισσότερο στο Elo.',
      'It shows who is rising and who is slipping, beyond Elo. It needs at least 3 games of the season to count, so in the first rounds the model leans more on Elo.'),
    good: T('Στη βαθμολογία: Ν = νίκη, Η = ήττα, από τον παλαιότερο στον πιο πρόσφατο.', 'In the standings: W = win, L = loss, from oldest to most recent.'),
    now: () => T(`${M.coef[1]} π. ανά πόντο φόρμας`, `${M.coef[1]} pts per point of form`),
  },
  sim: {
    icon: '🎲', title: T('Πιθανότητες σεζόν', 'Season projections'),
    short: T('Οι αγώνες που απομένουν παίζονται χιλιάδες φορές στον υπολογιστή: πόσο συχνά παίρνει κάθε ομάδα τον τίτλο, μπαίνει στα πλέι-οφ ή πέφτει.', 'The remaining games are played out thousands of times: how often each team wins the title, makes the playoffs or goes down.'),
    long: T('Για κάθε αγώνα που απομένει, το μοντέλο δίνει μια αναμενόμενη διαφορά πόντων. Σε κάθε προσομοίωση, η διαφορά «κληρώνεται» γύρω από αυτή την τιμή, όπως ακριβώς υπολογίζεται και η πιθανότητα νίκης. Οι νίκες προστίθενται στη σημερινή βαθμολογία, η σεζόν κατατάσσεται, και αυτό επαναλαμβάνεται χιλιάδες φορές. Το ποσοστό των σεζόν όπου μια ομάδα τερματίζει πρώτη είναι η πιθανότητα τίτλου της.',
      'For every remaining game the model gives an expected point margin. In each simulation the margin is drawn around that value, exactly as the win probability is computed. Wins are added to today\'s table, the season is ranked, and this is repeated thousands of times. The share of seasons a team finishes first is its title chance.'),
    good: T('Η δύναμη των ομάδων θεωρείται σταθερή ως το τέλος, και οι ισοβαθμίες λύνονται με τη διαφορά πόντων. Νωρίς στη σεζόν, μία αγωνιστική αλλάζει πολύ τα ποσοστά.', 'Team strength is held fixed to the end, and ties are broken by point difference. Early in the season a single round moves the numbers a lot.'),
    now: () => D.projection ? T(`${D.projection.runs.toLocaleString('el-GR')} προσομοιώσεις`, `${D.projection.runs.toLocaleString('en-GB')} simulations`) : '–',
  },
};

/** All graded picks where the model gave the favourite ≥ HIT_THRESHOLD. */
function confidentPicks() {
  return played.filter(g => g.pick && favProb(g.pick) >= HIT_THRESHOLD);
}
