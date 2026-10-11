// page: contact — form + FAQ. The form goes to the local server (desktop app,
// saved to data/contact_messages.csv) or, on the public site, straight to
// Firestore over REST; firestore.rules accept create-only, validated messages.

const TOPICS = ['Πρόταση', 'Πρόβλημα', 'Ερώτηση', 'Άλλο'];
/** What the English page shows for each topic; the stored value stays Greek (firestore.rules). */
const TOPIC_EN = {'Πρόταση': 'Suggestion', 'Πρόβλημα': 'Problem', 'Ερώτηση': 'Question', 'Άλλο': 'Other'};

const FAQ = [
  [T('Πόσο συχνά ενημερώνεται;', 'How often is it updated?'), PUBLIC
    ? T('Το site ελέγχει καθημερινά για νέα αποτελέσματα και προγραμματισμένους αγώνες. Όταν χρειάζεται, ενημερώνει τα αποτελέσματα και καταγράφει προβλέψεις πριν από τους αγώνες.', 'The site checks every day for new results and scheduled games. When needed, it updates the results and records predictions before the games.')
    : T('Όποτε πατάς «⟳ Ανανέωση», και αυτόματα όταν ανοίγεις την εφαρμογή αν έχουν περάσει πάνω από 6 ώρες.', 'Whenever you press "⟳ Refresh", and automatically when you open the app if more than 6 hours have passed.')],
  [T('Γιατί μια ομάδα που κέρδισε έχει ακόμα χαμηλό Elo;', 'Why does a team that won still have a low Elo?'), T('Το Elo ανανεώνεται μετά από κάθε αγώνα. Μια νίκη απέναντι σε ισχυρότερη ομάδα ανεβάζει περισσότερο το Elo από μια νίκη που αναμενόταν. Η βαθμολογία διαμορφώνεται σταδιακά, μέσα από τα αποτελέσματα πολλών αγώνων.', 'Elo is updated after every game. A win against a stronger team lifts Elo more than an expected win. The rating builds up gradually, over the results of many games.')],
  [T('Λαμβάνονται υπόψη οι τραυματισμοί;', 'Are injuries taken into account?'), T('Όχι προς το παρόν. Οι τραυματισμοί και οι απουσίες παικτών δεν συνυπολογίζονται στις προβλέψεις.', 'Not at the moment. Injuries and missing players are not part of the predictions.')],
  [T('Τι σημαίνει η φλόγα 🔥;', 'What does the flame 🔥 mean?'), T(`Το φαβορί είχε πιθανότητα νίκης ≥ ${HIT_THRESHOLD * 100}% και κέρδισε. Το 🎯 σημαίνει ότι η προβλεπόμενη διαφορά απείχε έως ${SHARP_POINTS} πόντους από την πραγματική.`, `The favourite had a ≥ ${HIT_THRESHOLD * 100}% chance of winning and won. 🎯 means the predicted margin was within ${SHARP_POINTS} points of the real one.`)],
  [T('Μπορώ να το χρησιμοποιήσω για στοίχημα;', 'Can I use it for betting?'), T('Δεν το προτείνουμε. Οι προβλέψεις είναι στατιστικές εκτιμήσεις, όχι συμβουλή στοιχηματισμού. Ακόμα και οι «μεγαλύτερες» πιθανότητες μπορεί να πέσουν έξω.', 'We don\'t recommend it. The predictions are statistical estimates, not betting advice. Even the "biggest" probabilities can miss.')],
  [T('Τι γίνεται με τα στοιχεία μου;', 'What happens to my details?'), T('Κρατάμε μόνο όσα γράφεις στη φόρμα, για να διαβάσουμε το μήνυμα και να σου απαντήσουμε στο email σου.', 'We keep only what you write in the form, to read your message and reply to your email.')],
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
  if (!fs) throw new Error(T('η φόρμα δεν είναι ενεργή σε αυτή την έκδοση', 'the form is not active in this version'));
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
  if (!res.ok) throw new Error(res.status === 403 ? T('το μήνυμα δεν έγινε δεκτό (έλεγξε τα πεδία)', 'the message was not accepted (check the fields)') : T(`σφάλμα δικτύου ${res.status}`, `network error ${res.status}`));
}

pages.contact = () => {
  const formBox = h('div');
  const canSend = SERVED || Boolean(SITE.firestore);
  const field = (label, input) => h('label', {class: 'field' + (input.dataset.full ? ' full' : '')}, label, input);
  const name = h('input', {name: 'name', required: true, maxlength: 80, autocomplete: 'name'});
  const email = h('input', {name: 'email', type: 'email', required: true, maxlength: 120, autocomplete: 'email'});
  const topic = h('select', {name: 'topic'}, TOPICS.map(t => h('option', {value: t}, T(t, TOPIC_EN[t]))));
  const message = h('textarea', {name: 'message', required: true, maxlength: 4000, placeholder: T('Γράψε μας…', 'Write to us…'), 'data-full': '1'});
  // Honeypot: invisible to people, filled in by spam bots. A filled one "succeeds" silently.
  const trap = h('input', {name: 'website', tabindex: '-1', autocomplete: 'off'});
  const submit = h('button', {class: 'btn btn-primary', type: 'submit', style: 'padding:11px 22px'}, T('Αποστολή →', 'Send →'));

  const thanks = () => formBox.replaceChildren(h('div', {class: 'sent'}, h('div', {class: 'check'}, '✓'), h('h2', null, T(`Ευχαριστούμε που επικοινώνησες με την ομάδα του ${BRAND.name}!`, `Thanks for contacting the ${BRAND.name} team!`)),
    h('p', {class: 'sub'}, T('Σύντομα θα λάβεις απάντηση στο αίτημά σου :)', 'You\'ll hear back from us soon :)')),
    h('button', {class: 'btn', type: 'button', style: 'margin-top:14px', onclick: () => route(false)}, T('Νέο μήνυμα', 'New message'))));

  const form = h('form', {novalidate: true, onsubmit: async e => {
    e.preventDefault();
    if (!name.value.trim() || !email.value.trim() || !message.value.trim()) { showToast(T('Συμπλήρωσε όνομα, email και μήνυμα.', 'Please fill in your name, email and message.'), 'bad', 4000); return; }
    if (!EMAIL_RE.test(email.value.trim())) { showToast(T('Το email δεν φαίνεται σωστό.', 'That email doesn\'t look right.'), 'bad', 4000); email.focus(); return; }
    // Bots fill the hidden field or post within a moment of loading: pretend it worked.
    if (trap.value || Date.now() - shownAt < MIN_FORM_MS) { thanks(); return; }
    if ((message.value.match(/https?:\/\/|www\./gi) || []).length > MAX_LINKS) {
      showToast(T(`Το μήνυμα έχει πολλούς συνδέσμους (μέχρι ${MAX_LINKS}).`, `The message has too many links (at most ${MAX_LINKS}).`), 'bad', 5000); return;
    }
    const last = +(localStorage.getItem(SENT_KEY) || 0);
    if (Date.now() - last < COOLDOWN_MS) { showToast(T('Μόλις έστειλες μήνυμα. Δοκίμασε ξανά σε ένα λεπτό.', 'You just sent a message. Try again in a minute.'), 'bad', 5000); return; }
    if (!canSend) {
      if (D.contact_email) {
        location.href = `mailto:${D.contact_email}?subject=${encodeURIComponent(`[${BRAND.name}] ` + topic.value)}&body=${encodeURIComponent(message.value + '\n\n— ' + name.value)}`;
        return;
      }
      showToast(T(`Για να σταλεί το μήνυμα, άνοιξε τη σελίδα από το εικονίδιο «${BRAND.name}».`, `To send the message, open the page from the "${BRAND.name}" icon.`), 'bad', 7000);
      return;
    }
    submit.disabled = true; submit.textContent = T('Αποστολή…', 'Sending…');
    try {
      await sendMessage({name: name.value.trim(), email: email.value.trim(), topic: topic.value, message: message.value.trim()});
      try { localStorage.setItem(SENT_KEY, String(Date.now())); } catch { /* private mode */ }
      thanks();
    } catch (err) {
      showToast(T('Δεν στάλθηκε: ', 'Not sent: ') + err.message, 'bad', 6000);
      submit.disabled = false; submit.textContent = T('Αποστολή →', 'Send →');
    }
  }}, h('div', {class: 'form-grid'}, field(T('Όνομα', 'Name'), name), field(h('span', null, 'Email * ', h('small', {class: 'muted'}, T('(υποχρεωτικό πεδίο)', '(required)'))), email), field(T('Θέμα', 'Topic'), topic),
    h('div'), field(T('Μήνυμα', 'Message'), message)),
  h('label', {class: 'hp-field', 'aria-hidden': 'true'}, T('Αφήστε το κενό', 'Leave this empty'), trap),
  h('div', {style: 'margin-top:16px;display:flex;justify-content:flex-end'}, submit),
  PUBLIC ? null : h('p', {class: 'form-note'}, T('Το μήνυμα αποθηκεύεται μόνο σε αυτόν τον υπολογιστή.', 'The message is saved on this computer only.')));
  formBox.append(form);
  const shownAt = Date.now();

  return [
    pageBanner(T('Επικοινωνία', 'Contact'), T('Έχεις ιδέες, εντόπισες πρόβλημα ή έχεις απορία; Γράψε μας — διαβάζουμε κάθε μήνυμα.', 'Got an idea, found a problem or have a question? Write to us — we read every message.')),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead(T('Στείλε μήνυμα', 'Send a message')), formBox),
      h('section', {class: 'panel faq'}, sectionHead(T('Συχνές ερωτήσεις', 'Frequently asked questions')),
        FAQ.map(([q, a]) => h('details', null, h('summary', null, q), h('p', null, a))))),
  ];
};
