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
  ['Τι σημαίνει το χρυσό 🔥;', `Το φαβορί είχε πιθανότητα νίκης ≥ ${HIT_THRESHOLD * 100}% και κέρδισε. Το 🎯 σημαίνει ότι η προβλεπόμενη διαφορά απείχε έως ${SHARP_POINTS} πόντους από την πραγματική.`],
  ['Μπορώ να το χρησιμοποιήσω για στοίχημα;', 'Δεν το προτείνουμε. Οι προβλέψεις είναι στατιστικές εκτιμήσεις, όχι συμβουλή στοιχηματισμού. Ακόμα και οι «μεγαλύτερες» πιθανότητες μπορεί να πέσουν έξω.'],
  ['Τι γίνεται με τα στοιχεία μου;', 'Κρατάμε μόνο όσα γράφεις στη φόρμα, για να διαβάσουμε το μήνυμα και να σου απαντήσουμε στο email σου.'],
];

/** Anti-spam, all in the page (no outside scripts): a hidden honeypot field, a minimum time
 *  on the form, one message a minute per browser and at most MAX_LINKS links. The Firestore
 *  rules check the fields again (email required) for anything that skips the page. */
const MIN_FORM_MS = 3000, COOLDOWN_MS = 60_000, MAX_LINKS = 2, SENT_KEY = 'tipoff-last-message';
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

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
  const name = h('input', {name: 'name', required: true, maxlength: 80, autocomplete: 'name'});
  const email = h('input', {name: 'email', type: 'email', required: true, maxlength: 120, autocomplete: 'email'});
  const topic = h('select', {name: 'topic'}, TOPICS.map(t => h('option', {value: t}, t)));
  const message = h('textarea', {name: 'message', required: true, maxlength: 4000, placeholder: 'Γράψε μας…', 'data-full': '1'});
  // Honeypot: invisible to people, filled in by spam bots. A filled one "succeeds" silently.
  const trap = h('input', {name: 'website', tabindex: '-1', autocomplete: 'off'});
  const submit = h('button', {class: 'btn btn-primary', type: 'submit', style: 'padding:11px 22px'}, 'Αποστολή →');

  const thanks = () => formBox.replaceChildren(h('div', {class: 'sent'}, h('div', {class: 'check'}, '✓'), h('h2', null, `Ευχαριστούμε που επικοινώνησες με την ομάδα του ${BRAND.name}!`),
    h('p', {class: 'sub'}, 'Σύντομα θα λάβεις απάντηση στο αίτημά σου :)'),
    h('button', {class: 'btn', type: 'button', style: 'margin-top:14px', onclick: () => route(false)}, 'Νέο μήνυμα')));

  const form = h('form', {novalidate: true, onsubmit: async e => {
    e.preventDefault();
    if (!name.value.trim() || !email.value.trim() || !message.value.trim()) { showToast('Συμπλήρωσε όνομα, email και μήνυμα.', 'bad', 4000); return; }
    if (!EMAIL_RE.test(email.value.trim())) { showToast('Το email δεν φαίνεται σωστό.', 'bad', 4000); email.focus(); return; }
    // Bots fill the hidden field or post within a moment of loading: pretend it worked.
    if (trap.value || Date.now() - shownAt < MIN_FORM_MS) { thanks(); return; }
    if ((message.value.match(/https?:\/\/|www\./gi) || []).length > MAX_LINKS) {
      showToast(`Το μήνυμα έχει πολλούς συνδέσμους (μέχρι ${MAX_LINKS}).`, 'bad', 5000); return;
    }
    const last = +(localStorage.getItem(SENT_KEY) || 0);
    if (Date.now() - last < COOLDOWN_MS) { showToast('Μόλις έστειλες μήνυμα. Δοκίμασε ξανά σε ένα λεπτό.', 'bad', 5000); return; }
    if (!canSend) {
      if (D.contact_email) {
        location.href = `mailto:${D.contact_email}?subject=${encodeURIComponent(`[${BRAND.name}] ` + topic.value)}&body=${encodeURIComponent(message.value + '\n\n— ' + name.value)}`;
        return;
      }
      showToast(`Για να σταλεί το μήνυμα, άνοιξε τη σελίδα από το εικονίδιο «${BRAND.name}».`, 'bad', 7000);
      return;
    }
    submit.disabled = true; submit.textContent = 'Αποστολή…';
    try {
      await sendMessage({name: name.value.trim(), email: email.value.trim(), topic: topic.value, message: message.value.trim()});
      try { localStorage.setItem(SENT_KEY, String(Date.now())); } catch { /* private mode */ }
      thanks();
    } catch (err) {
      showToast('Δεν στάλθηκε: ' + err.message, 'bad', 6000);
      submit.disabled = false; submit.textContent = 'Αποστολή →';
    }
  }}, h('div', {class: 'form-grid'}, field('Όνομα', name), field('Email *', email), field('Θέμα', topic),
    h('div'), field('Μήνυμα', message)),
  h('label', {class: 'hp-field', 'aria-hidden': 'true'}, 'Αφήστε το κενό', trap),
  h('div', {style: 'margin-top:16px;display:flex;justify-content:flex-end'}, submit),
  PUBLIC ? null : h('p', {class: 'form-note'}, 'Το μήνυμα αποθηκεύεται μόνο σε αυτόν τον υπολογιστή.'));
  formBox.append(form);
  const shownAt = Date.now();

  return [
    pageBanner('Επικοινωνία', 'Έχεις ιδέες, εντόπισες πρόβλημα ή έχεις απορία; Γράψε μας — διαβάζουμε κάθε μήνυμα.'),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Στείλε μήνυμα'), formBox),
      h('section', {class: 'panel faq'}, sectionHead('Συχνές ερωτήσεις'),
        FAQ.map(([q, a]) => h('details', null, h('summary', null, q), h('p', null, a))))),
  ];
};
