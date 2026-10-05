// page: contact — form (saved locally by scripts/serve.py) + FAQ.

const FAQ = [
  ['Πόσο συχνά ενημερώνεται;', 'Όποτε πατάς «⟳ Ανανέωση», και αυτόματα όταν ανοίγεις την εφαρμογή αν έχουν περάσει πάνω από 6 ώρες.'],
  ['Γιατί μια ομάδα που κέρδισε έχει ακόμα χαμηλό Elo;', 'Το Elo κινείται σιγά-σιγά: μία νίκη ανεβάζει 5–15 πόντους, ανάλογα με το πόσο αναμενόμενη ήταν. Χρειάζονται αρκετοί αγώνες για να «πιάσει» την πραγματική δύναμη.'],
  ['Λαμβάνονται υπόψη οι τραυματισμοί;', 'Όχι αυτόματα. Υπάρχει μηχανισμός για απουσίες παικτών με βάση τη σημασία τους, που χρειάζεται τα ρόστερ. Είναι στις ιδέες για το μέλλον.'],
  ['Τι σημαίνει το χρυσό 🔥;', `Πρόβλεψη με πιθανότητα ≥ ${HIT_THRESHOLD * 100}% που βγήκε σωστή. Το 🎯 σημαίνει ότι και η διαφορά πόντων έπεσε μέσα σε ±${SHARP_POINTS}.`],
  ['Μπορώ να το χρησιμοποιήσω για στοίχημα;', 'Δεν το προτείνουμε. Είναι εργαλείο ανάλυσης. Ακόμα και οι καλύτερες πιθανότητες χάνουν συχνά.'],
];

pages.contact = () => {
  const formBox = h('div');
  const field = (label, input) => h('label', {class: 'field' + (input.dataset.full ? ' full' : '')}, label, input);
  const name = h('input', {name: 'name', required: true, maxlength: 80, autocomplete: 'name', placeholder: 'π.χ. Δημήτρης'});
  const email = h('input', {name: 'email', type: 'email', maxlength: 120, autocomplete: 'email', placeholder: 'προαιρετικό'});
  const topic = h('select', {name: 'topic'}, ['Πρόταση', 'Πρόβλημα', 'Ερώτηση', 'Άλλο'].map(t => h('option', {value: t}, t)));
  const message = h('textarea', {name: 'message', required: true, maxlength: 4000, placeholder: 'Γράψε μας…', 'data-full': '1'});
  const submit = h('button', {class: 'btn btn-primary', type: 'submit', style: 'padding:11px 22px'}, 'Αποστολή →');

  const form = h('form', {novalidate: true, onsubmit: async e => {
    e.preventDefault();
    if (!name.value.trim() || !message.value.trim()) { showToast('Συμπλήρωσε όνομα και μήνυμα.', 'bad', 4000); return; }
    if (!SERVED) {
      const mail = D.contact_email
        ? `mailto:${D.contact_email}?subject=${encodeURIComponent('[GBL Predictor] ' + topic.value)}&body=${encodeURIComponent(message.value + '\n\n— ' + name.value)}`
        : null;
      if (mail) { location.href = mail; return; }
      showToast('Για να σταλεί το μήνυμα, άνοιξε τη σελίδα από το εικονίδιο «GBL Predictor».', 'bad', 7000);
      return;
    }
    submit.disabled = true; submit.textContent = 'Αποστολή…';
    try {
      const res = await fetch('/api/contact', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-GBL-Refresh': '1'},
        body: JSON.stringify({name: name.value, email: email.value, topic: topic.value, message: message.value})});
      const body = await res.json();
      if (!body.ok) throw new Error(body.message);
      formBox.replaceChildren(h('div', {class: 'sent'}, h('div', {class: 'check'}, '✓'), h('h2', null, 'Ευχαριστούμε!'),
        h('p', {class: 'sub'}, 'Το μήνυμά σου αποθηκεύτηκε. Θα το δούμε σύντομα.'),
        h('button', {class: 'btn', type: 'button', style: 'margin-top:14px', onclick: () => route(false)}, 'Νέο μήνυμα')));
    } catch (err) {
      showToast('Δεν στάλθηκε: ' + err.message, 'bad', 6000);
      submit.disabled = false; submit.textContent = 'Αποστολή →';
    }
  }}, h('div', {class: 'form-grid'}, field('Όνομα', name), field('Email', email), field('Θέμα', topic),
    h('div'), field('Μήνυμα', message)), h('div', {style: 'margin-top:16px;display:flex;justify-content:flex-end'}, submit));
  formBox.append(form);

  return [
    pageBanner('Επικοινωνία', 'Ιδέες, προβλήματα, απορίες; Γράψε μας. Κάθε πρόταση διαβάζεται.'),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Στείλε μήνυμα'), formBox),
      h('section', {class: 'panel faq'}, sectionHead('Συχνές ερωτήσεις'),
        FAQ.map(([q, a]) => h('details', null, h('summary', null, q), h('p', null, a))))),
  ];
};
