// page: schedule — every remaining game, by month or by team.

pages.schedule = () => {
  const box = h('div');
  const months = [...new Set(D.upcoming.map(u => u.d.slice(0, 7)))];
  const st = {team: '', month: months[0] || '', predictedOnly: false};
  const draw = () => {
    const rows = D.upcoming.filter(u => (!st.predictedOnly || u.pi >= 0)
      && (st.team ? (u.home === st.team || u.away === st.team) : (!st.month || u.d.startsWith(st.month))));
    const byDay = {};
    rows.forEach(u => (byDay[u.d] = byDay[u.d] || []).push(u));
    box.replaceChildren(...(rows.length ? Object.entries(byDay).map(([d, us]) => h('div', {class: 'sched-day'}, h('div', {class: 'sched-date'}, fullDate(d)),
      us.map(u => {
        const p = u.pi >= 0 ? D.next[u.pi] : null;
        return h('div', {class: 'sched-game' + (isFocus(u.home, u.away) ? ' is-focus' : '')}, h('span', {class: 'muted'}, u.t || ''),
          h('span', {class: 'vs'}, tlink(u.home), h('span', {class: 'muted'}, '–'), tlink(u.away)),
          p ? h('span', {class: 'pchip', title: T(`Το μοντέλο εκτιμά ότι η ομάδα ${tn(p.w)} έχει περίπου ${Math.round(Math.max(p.p, 1 - p.p) * 10)} στις 10 πιθανότητες να κερδίσει.`, `The model gives ${tn(p.w)} about a ${Math.round(Math.max(p.p, 1 - p.p) * 10)} in 10 chance of winning.`)}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${tn(p.w)} ${pct(Math.max(p.p, 1 - p.p))}`) : h('span', {class: 'pchip'}));
      }))) : [h('p', {class: 'empty'}, T('Κανένας αγώνας.', 'No games.'))]));
  };
  const monthCtrl = segCtrl(months.map(mo => [mo, `${MONTHS[+mo.slice(5) - 1]} '${mo.slice(2, 4)}`]), st.month, v => { st.month = v; draw(); });
  const filters = h('div', {class: 'filters'},
    selectEl([['', T('Όλες οι ομάδες', 'All teams')], ...teamOptions()], st.team, v => { st.team = v; monthCtrl.style.display = v ? 'none' : ''; draw(); }, T('Ομάδα', 'Team')),
    monthCtrl,
    selectEl([['all', T('Όλοι οι αγώνες', 'All games')], ['predicted', T('Μόνο αγώνες με πρόβλεψη', 'Only games with a prediction')]], st.predictedOnly ? 'predicted' : 'all', v => { st.predictedOnly = v === 'predicted'; draw(); }, T('Προβλέψεις', 'Predictions')));
  draw();
  return [pageBanner(T('Πρόγραμμα', 'Schedule'), T(`${D.upcoming.length} αγώνες μέχρι το τέλος της κανονικής περιόδου`, `${D.upcoming.length} games to the end of the regular season`)),
    h('section', {class: 'panel'}, sectionHead(T('Αγώνες ανά ημέρα', 'Games by day'), T('δεξιά: η πρόβλεψη του μοντέλου (σκορ · φαβορί και πιθανότητα), μόνο για την επόμενη αγωνιστική', 'on the right: the model\'s prediction (score · favourite and probability), for the next round only'), infoDot('prob')),
      filters, box,
      h('p', {class: 'foot-note'}, T('Το μοντέλο προβλέπει μόνο την επόμενη αγωνιστική. Για τους μελλοντικούς αγώνες δεν εμφανίζουμε ακόμη πρόβλεψη, επειδή τα δεδομένα των ομάδων μπορεί να αλλάξουν.', 'The model predicts only the next round. Later games get no prediction yet, because the teams\' numbers can still change.')))];
};
