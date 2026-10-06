// page: contact — form + FAQ. The form goes to the local server (desktop app,
// saved to data/contact_messages.csv) or, on the public site, straight to
// Firestore over REST; firestore.rules accept create-only, validated messages.

const TOPICS = ['Πρόταση', 'Πρόβλημα', 'Ερώτηση', 'Άλλο'];

const FAQ = [
  ['Πόσο συχνά ενημερώνεται;', PUBLIC
    ? 'Αυτόματα, κάθε βράδυ που υπάρχει λόγος: μετά από κάθε αγωνιστική για τα αποτελέσματα και πριν από την επόμενη για τις προβλέψεις.'
    : 'Όποτε πατάς «⟳ Ανανέωση», και αυτόματα όταν ανοίγεις την εφαρμογή αν έχουν περάσει πάνω από 6 ώρες.'],
  ['Γιατί μια ομάδα που κέρδισε έχει ακόμα χαμηλό Elo;', 'Το Elo κινείται σιγά-σιγά: μία νίκη ανεβάζει 5–15 πόντους, ανάλογα με το πόσο αναμενόμενη ήταν. Χρειάζονται αρκετοί αγώνες για να «πιάσει» την πραγματική δύναμη.'],
  ['Λαμβάνονται υπόψη οι τραυματισμοί;', 'Όχι αυτόματα. Υπάρχει μηχανισμός για απουσίες παικτών με βάση τη σημασία τους, που χρειάζεται τα ρόστερ. Είναι στις ιδέες για το μέλλον.'],
  ['Τι σημαίνει το χρυσό 🔥;', `Πρόβλεψη με πιθανότητα ≥ ${HIT_THRESHOLD * 100}% που βγήκε σωστή. Το 🎯 σημαίνει ότι και η διαφορά πόντων έπεσε μέσα σε ±${SHARP_POINTS}.`],
  ['Μπορώ να το χρησιμοποιήσω για στοίχημα;', 'Δεν το προτείνουμε. Οι προβλέψεις είναι στατιστικές εκτιμήσεις, όχι συμβουλή στοιχηματισμού. Ακόμα και οι καλύτερες πιθανότητες χάνουν συχνά.'],
  ['Τι γίνεται με τα στοιχεία μου;', 'Κρατάμε μόνο όσα γράφεις στη φόρμα, για να διαβάσουμε το μήνυμα και, αν δώσεις email, να απαντήσουμε. Δεν τα δίνουμε σε κανέναν. Για διαγραφή, στείλε ένα μήνυμα που να το ζητά.'],
];

/** Store the message: local server, Firestore, or nothing (opened as a plain file). */
async function sendMessage(msg) {
  if (SERVED) {
    const res = await fetch('/api/contact', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-GBL-Refresh': '1'},
      body: JSON.stringify(msg)});
    const body = await res.json();
    if (!body.ok) throw new Error(body.message);
    return;
  }
  const fs = SITE.firestore;
  if (!fs) throw new Error('η φόρμα δεν είναι ενεργή σε αυτή την έκδοση');
  // documents:commit lets the server stamp `created` (rules require created == request.time).
  const base = `projects/${fs.project}/databases/(default)/documents`;
  const fields = Object.fromEntries(Object.entries(msg).filter(([, v]) => v).map(([k, v]) => [k, {stringValue: v}]));
  const res = await fetch(`https://firestore.googleapis.com/v1/${base}:commit?key=${encodeURIComponent(fs.key)}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({writes: [{
      update: {name: `${base}/${fs.collection}/${crypto.randomUUID()}`, fields},
      updateTransforms: [{fieldPath: 'created', setToServerValue: 'REQUEST_TIME'}],
      currentDocument: {exists: false},
    }]})});
  if (!res.ok) throw new Error(res.status === 403 ? 'το μήνυμα δεν έγινε δεκτό (έλεγξε τα πεδία)' : `σφάλμα δικτύου ${res.status}`);
}

pages.contact = () => {
  const formBox = h('div');
  const canSend = SERVED || Boolean(SITE.firestore);
  const field = (label, input) => h('label', {class: 'field' + (input.dataset.full ? ' full' : '')}, label, input);
  const name = h('input', {name: 'name', required: true, maxlength: 80, autocomplete: 'name', placeholder: 'π.χ. Δημήτρης'});
  const email = h('input', {name: 'email', type: 'email', maxlength: 120, autocomplete: 'email', placeholder: 'προαιρετικό'});
  const topic = h('select', {name: 'topic'}, TOPICS.map(t => h('option', {value: t}, t)));
  const message = h('textarea', {name: 'message', required: true, maxlength: 4000, placeholder: 'Γράψε μας…', 'data-full': '1'});
  // Honeypot: invisible to people, filled in by spam bots. A filled one "succeeds" silently.
  const trap = h('input', {name: 'website', tabindex: '-1', autocomplete: 'off'});
  const submit = h('button', {class: 'btn btn-primary', type: 'submit', style: 'padding:11px 22px'}, 'Αποστολή →');

  const thanks = () => formBox.replaceChildren(h('div', {class: 'sent'}, h('div', {class: 'check'}, '✓'), h('h2', null, 'Ευχαριστούμε!'),
    h('p', {class: 'sub'}, 'Το μήνυμά σου αποθηκεύτηκε. Θα το δούμε σύντομα.'),
    h('button', {class: 'btn', type: 'button', style: 'margin-top:14px', onclick: () => route(false)}, 'Νέο μήνυμα')));

  const form = h('form', {novalidate: true, onsubmit: async e => {
    e.preventDefault();
    if (!name.value.trim() || !message.value.trim()) { showToast('Συμπλήρωσε όνομα και μήνυμα.', 'bad', 4000); return; }
    if (trap.value) { thanks(); return; }
    if (!canSend) {
      if (D.contact_email) {
        location.href = `mailto:${D.contact_email}?subject=${encodeURIComponent('[GBL Predictor] ' + topic.value)}&body=${encodeURIComponent(message.value + '\n\n— ' + name.value)}`;
        return;
      }
      showToast('Για να σταλεί το μήνυμα, άνοιξε τη σελίδα από το εικονίδιο «GBL Predictor».', 'bad', 7000);
      return;
    }
    submit.disabled = true; submit.textContent = 'Αποστολή…';
    try {
      await sendMessage({name: name.value.trim(), email: email.value.trim(), topic: topic.value, message: message.value.trim()});
      thanks();
    } catch (err) {
      showToast('Δεν στάλθηκε: ' + err.message, 'bad', 6000);
      submit.disabled = false; submit.textContent = 'Αποστολή →';
    }
  }}, h('div', {class: 'form-grid'}, field('Όνομα', name), field('Email', email), field('Θέμα', topic),
    h('div'), field('Μήνυμα', message)),
  h('label', {class: 'hp-field', 'aria-hidden': 'true'}, 'Αφήστε το κενό', trap),
  h('div', {style: 'margin-top:16px;display:flex;justify-content:flex-end'}, submit),
  h('p', {class: 'form-note'}, PUBLIC
    ? 'Το μήνυμα αποθηκεύεται με ασφάλεια σε βάση δεδομένων της Google (Firebase, στην Ευρώπη) και το διαβάζει μόνο ο διαχειριστής. Το email είναι προαιρετικό και χρησιμοποιείται μόνο για απάντηση.'
    : 'Το μήνυμα αποθηκεύεται μόνο σε αυτόν τον υπολογιστή.'));
  formBox.append(form);

  return [
    pageBanner('Επικοινωνία', 'Ιδέες, προβλήματα, απορίες; Γράψε μας. Κάθε πρόταση διαβάζεται.'),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Στείλε μήνυμα'), formBox),
      h('section', {class: 'panel faq'}, sectionHead('Συχνές ερωτήσεις'),
        FAQ.map(([q, a]) => h('details', null, h('summary', null, q), h('p', null, a))))),
  ];
};
