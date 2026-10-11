// components — reusable UI building blocks (no page logic here).

// ---------------------------------------------------------------- headings & banners
function sectionHead(title, sub, link) {
  if (typeof sub === 'string') sub = sub.charAt(0).toUpperCase() + sub.slice(1);  // subtitles start with a capital
  return h('div', {class: 'section-head'},
    h('h2', null, title, sub ? h('span', {class: 'h-sub'}, sub) : null), link || null);
}

function pageBanner(title, sub, extra, crumb) {
  return h('section', {class: 'banner'}, h('div', {class: 'banner-inner'},
    h('div', null, crumb || null,
      h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${season}`),
      h('h1', null, title), sub ? h('p', {class: 'hero-sub'}, sub) : null),
    extra || null));
}

// ---------------------------------------------------------------- metric info & KPI tiles
/** ⓘ button: tooltip with the short explanation; click opens the full guide entry. */
function infoDot(key) {
  const m = METRICS[key];
  if (!m) return null;
  const btn = h('button', {class: 'info', type: 'button', 'aria-label': T(`Τι σημαίνει: ${m.title}`, `What it means: ${m.title}`),
    onclick: e => { e.preventDefault(); e.stopPropagation(); state.flashMetric = key; go(url('model', 'metrics')); }}, 'i');
  return hover(btn, () => [{text: m.title}, {text: m.short}, {text: T('Κλικ για αναλυτική εξήγηση', 'Click for the full explanation'), cls: 't-sub'}]);
}

/** KPI tile. opts: {info, count:{to, dec, fmt}, gold} */
function kpi(label, value, sub, opts = {}) {
  const val = h('div', {class: 'kpi-value'}, value);
  if (opts.count) Object.assign(val.dataset, {count: opts.count.to, dec: opts.count.dec || 0, fmt: opts.count.fmt || 'plain'}, opts.count.of ? {of: opts.count.of} : {});
  return h('div', {class: 'kpi' + (opts.gold ? ' gold' : '')},
    h('div', {class: 'kpi-label'}, label, opts.info ? infoDot(opts.info) : null), val, h('div', {class: 'kpi-sub'}, sub));
}

// ---------------------------------------------------------------- tabs
/**
 * Accessible tab group. items: [{key, label, count?, render: () => Node[]}].
 * Every tab has its own address: `urlFor(key)` gives it, and choosing a tab
 * swaps the address with replaceState (shareable, no page re-render).
 */
function tabs(id, items, initial, urlFor) {
  let current = items.some(t => t.key === initial) ? initial : (state.tabs[id] || items[0].key);
  if (!items.some(t => t.key === current)) current = items[0].key;
  const bar = h('div', {class: 'tabs', role: 'tablist'});
  const ink = h('span', {class: 'tab-ink', 'aria-hidden': 'true'});
  const panel = h('div', {role: 'tabpanel'});
  const buttons = items.map(t => h('button', {class: 'tab', role: 'tab', type: 'button', id: `tab-${id}-${t.key}`,
    onclick: () => select(t.key, true),
    onkeydown: e => {
      const i = items.findIndex(x => x.key === current);
      const j = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : null;
      if (j === null) return;
      e.preventDefault();
      const next = items[(j + items.length) % items.length].key;
      select(next, true);
      bar.querySelector(`#tab-${id}-${next}`).focus();
    }}, t.label, t.count != null ? h('span', {class: 'count'}, t.count) : null));
  bar.append(...buttons, ink);
  const moveInk = () => {
    const b = bar.querySelector('[aria-selected=true]');
    if (!b) return;
    ink.style.left = b.offsetLeft + 'px'; ink.style.width = b.offsetWidth + 'px';
    // On phones the strip scrolls: keep the chosen tab in view.
    if (b.offsetLeft < bar.scrollLeft || b.offsetLeft + b.offsetWidth > bar.scrollLeft + bar.clientWidth) bar.scrollLeft = b.offsetLeft - 16;
  };
  function select(key, user) {
    current = key; state.tabs[id] = key;
    buttons.forEach((b, i) => { const on = items[i].key === key; b.setAttribute('aria-selected', on); b.tabIndex = on ? 0 : -1; });
    panel.setAttribute('aria-labelledby', `tab-${id}-${key}`);
    panel.replaceChildren(h('div', {class: 'tab-panel'}, items.find(t => t.key === key).render()));
    if (user && urlFor) { history.replaceState(null, '', urlFor(key)); applyMeta(); }
    requestAnimationFrame(moveInk);
    if (user) afterRender(panel);
  }
  select(current, false);
  new ResizeObserver(moveInk).observe(bar);
  return h('div', null, bar, panel);
}

// ---------------------------------------------------------------- tables & controls
/**
 * Sortable table. cols: {label, num?, title?, sort?(row), render(row), plus phone layout:
 *   sticky?: 1|2   column stays put while the table scrolls sideways (#, team)
 *   hideSm?: true  hidden on phones
 *   area?: name    grid area when opts.cards is set (rows become cards on phones)
 *   cap?: true|str caption above the value in a card (the label, or this text)}
 * opts.cards = 'results' | 'log' picks the card layout in app.css.
 * opts.paged = true: pages of 20 / 40 / 60 rows with a pager below (the size is remembered).
 * opts.group = {col, of(row) -> {key, label, note?}}: while sorted by column `col`, a full-width
 *   separator row (label left, note right) goes above each new key (rounds in the history).
 */
const PAGE_SIZES = [20, 40, 60];
function table(cols, rows, opts = {}) {
  let sortIdx = opts.sortIdx ?? -1, dir = opts.dir ?? 1, page = 0;
  let size = PAGE_SIZES.includes(+localStorage.getItem('gbl-page-size')) ? +localStorage.getItem('gbl-page-size') : PAGE_SIZES[0];
  const paged = opts.paged && rows.length > PAGE_SIZES[0];
  const wrap = h('div', {class: 'table-wrap' + (opts.cards ? ` cards-sm cards-${opts.cards}` : '') + (opts.center ? ' t-center' : '')});
  const pager = h('div', {class: 'pager', role: 'navigation', 'aria-label': T('Σελίδες πίνακα', 'Table pages')});
  const cellClass = (c, base) => [base, c.sticky ? `sticky-${c.sticky}` : '', c.hideSm ? 'hide-sm' : '', c.area ? `c-${c.area}` : ''].filter(Boolean).join(' ') || null;
  // A fade on the right edge says "there is more, swipe" while the table can still scroll.
  const edge = () => wrap.classList.toggle('more-right', wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 2);
  wrap.addEventListener('scroll', edge, {passive: true});
  new ResizeObserver(edge).observe(wrap);
  /** Go to another page (or page size) and bring the table's top into view. */
  function turn(to, newSize) {
    if (newSize) { size = newSize; localStorage.setItem('gbl-page-size', String(size)); }
    page = to; draw(); afterRender(wrap);
    const top = wrap.getBoundingClientRect().top;
    if (top < 70) window.scrollBy({top: top - 90, behavior: REDUCED_MOTION ? 'auto' : 'smooth'});
  }
  function drawPager(total) {
    const pages = Math.ceil(total / size);
    page = Math.min(page, pages - 1);
    // 1 … 4 5 6 … 10: first, last and the current page's neighbours
    const nums = [...new Set([0, page - 1, page, page + 1, pages - 1])].filter(n => n >= 0 && n < pages).sort((a, b) => a - b);
    const btn = (label, to, attrs = {}) => h('button', {type: 'button', class: 'pg', onclick: () => turn(to), ...attrs}, label);
    const list = [];
    nums.forEach((n, i) => {
      if (i && n - nums[i - 1] > 1) list.push(h('span', {class: 'pg-gap', 'aria-hidden': 'true'}, '…'));
      list.push(btn(String(n + 1), n, n === page ? {'aria-current': 'page', class: 'pg on'} : {'aria-label': T(`Σελίδα ${n + 1}`, `Page ${n + 1}`)}));
    });
    pager.replaceChildren(
      h('div', {class: 'pg-size'}, h('span', null, T('Ανά σελίδα', 'Per page')),
        segCtrl(PAGE_SIZES.map(n => [n, String(n)]), size, v => turn(0, v))),
      h('div', {class: 'pg-pages'},
        btn('‹', page - 1, {'aria-label': T('Προηγούμενη σελίδα', 'Previous page'), disabled: page === 0}), list,
        btn('›', page + 1, {'aria-label': T('Επόμενη σελίδα', 'Next page'), disabled: page >= pages - 1})),
      h('div', {class: 'pg-count'}, `${page * size + 1}–${Math.min(total, (page + 1) * size)} ${T('από', 'of')} ${total}`));
  }
  function draw() {
    const data = rows.slice();
    if (sortIdx >= 0 && cols[sortIdx].sort) {
      const f = cols[sortIdx].sort;
      data.sort((a, b) => { const x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
    }
    if (paged) drawPager(data.length);
    const head = h('tr', null, cols.map((c, i) => {
      const th = h('th', {class: cellClass(c, (c.num ? 'num ' : '') + (c.sort ? 'sortable' : '')), title: c.title || null, scope: 'col',
        'aria-sort': i === sortIdx ? (dir > 0 ? 'ascending' : 'descending') : null, tabindex: c.sort ? 0 : null},
        c.label, c.info ? infoDot(c.info) : null, c.sort ? h('span', {class: 'arrow'}, i === sortIdx ? (dir > 0 ? '▲' : '▼') : ' ') : null);
      if (c.sort) {
        const act = () => { if (sortIdx === i) dir = -dir; else { sortIdx = i; dir = c.num ? -1 : 1; } page = 0; draw(); };
        th.addEventListener('click', act);
        th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
      }
      return th;
    }));
    const visible = paged ? data.slice(page * size, (page + 1) * size) : data;
    const grouped = opts.group && sortIdx === opts.group.col;
    let lastKey = null;
    const body = data.length
      ? visible.flatMap(r => {
        const row = h('tr', {class: opts.rowClass ? opts.rowClass(r) : null}, cols.map(c => h('td', {class: cellClass(c, c.num ? 'num' : ''),
          'data-label': c.cap ? (typeof c.cap === 'string' ? c.cap : c.label) : null}, c.render(r))));
        if (!grouped) return [row];
        const g = opts.group.of(r);
        if (g.key === lastKey) return [row];
        lastKey = g.key;
        return [h('tr', {class: 'group-row'}, h('td', {colspan: cols.length}, h('div', {class: 'g-inner'},
          h('span', {class: 'g-label'}, g.label), h('span', {class: 'g-line', 'aria-hidden': 'true'}), g.note || null))), row];
      })
      : [h('tr', null, h('td', {colspan: cols.length, class: 'empty'}, opts.empty || T('Δεν υπάρχουν δεδομένα.', 'No data.')))];
    wrap.replaceChildren(h('table', null, h('thead', null, head), h('tbody', null, body)));
    requestAnimationFrame(edge);
  }
  draw();
  return paged ? h('div', {class: 'table-block'}, wrap, pager) : wrap;
}

function segCtrl(options, value, onChange) {
  const box = h('div', {class: 'seg-ctrl', role: 'group'});
  const draw = () => box.replaceChildren(...options.map(([v, label]) =>
    h('button', {type: 'button', 'aria-pressed': String(v === value), onclick: () => { value = v; draw(); onChange(v); }}, label)));
  draw();
  return box;
}

function selectEl(options, value, onChange, label) {
  return h('select', {'aria-label': label, onchange: e => onChange(e.target.value)},
    options.map(([v, t]) => h('option', {value: v, selected: v === value}, t)));
}

// ---------------------------------------------------------------- small badges
function formChips(form) {
  return h('span', {class: 'form'}, form.map(r =>
    h('span', {class: 'chip ' + (r === 'W' ? 'win' : 'loss'), title: r === 'W' ? T('Νίκη', 'Win') : T('Ήττα', 'Loss')}, r === 'W' ? T('Ν', 'W') : T('Η', 'L'))));
}
function verdict(ok) {
  if (ok == null) return h('span', {class: 'verdict pending'}, T('⏳ εκκρεμεί', '⏳ pending'));
  return h('span', {class: 'verdict ' + (ok ? 'good' : 'bad')}, ok ? T('✓ Σωστό', '✓ Correct') : T('✗ Λάθος', '✗ Wrong'));
}
function hitBadge(prob) { return h('span', {class: 'hit-badge', title: T(`Το φαβορί είχε πιθανότητα ${pctProb(prob)} και κέρδισε`, `The favourite had a ${pctProb(prob)} chance and won`)}, '🔥 ', pctProb(prob)); }
function sharpBadge(err) { return h('span', {class: 'sharp-badge', title: T('Η προβλεπόμενη διαφορά ήταν κοντά στην πραγματική', 'The predicted margin was close to the real one')}, '🎯 ', err === 0 ? T('ακριβώς', 'exact') : `±${err}`); }
/** Confidence label for an upcoming game. */
function confBadge(prob) {
  if (prob >= HIT_THRESHOLD) return h('span', {class: 'conf lock'}, T('🔒 ισχυρό φαβορί', '🔒 strong favourite'));
  if (prob >= 0.6) return h('span', {class: 'conf lean'}, T('φαβορί', 'favourite'));
  return h('span', {class: 'conf toss'}, T('ανοιχτό', 'open'));
}

// ---------------------------------------------------------------- probability bar
function probBar(p, cls = 'prob') {
  const hp = Math.round(p.p * 100), ap = 100 - hp, homeFav = p.p >= 0.5;
  return h('div', {class: cls, role: 'img', tabindex: 0, 'aria-label': T(`Πιθανότητα νίκης: ${tn(p.home)} ${hp}%, ${tn(p.away)} ${ap}%`, `Win probability: ${tn(p.home)} ${hp}%, ${tn(p.away)} ${ap}%`)},
    h('div', {class: 'seg ' + (homeFav ? 'accent' : 'track'), 'data-w': `${hp}%`}),
    h('div', {class: 'seg ' + (homeFav ? 'track' : 'accent'), 'data-w': `${ap}%`}));
}

// ---------------------------------------------------------------- prediction card (upcoming)
function predCard(p) {
  const homeFav = p.p >= 0.5, hp = Math.round(p.p * 100), ap = 100 - hp;
  const bar = hover(probBar(p), () => [
    {text: `${tn(p.w)} ${Math.max(hp, ap)}%`},
    {text: T(`Το μοντέλο εκτιμά ότι η ομάδα ${tn(p.w)} έχει περίπου ${Math.round(Math.max(hp, ap) / 10)} στις 10 πιθανότητες να κερδίσει.`,
      `The model gives ${tn(p.w)} about a ${Math.round(Math.max(hp, ap) / 10)} in 10 chance of winning.`)},
    {text: T(`Προβλεπόμενη διαφορά ${signed(p.margin)} για τον γηπεδούχο (±${p.band})`, `Predicted margin ${signed(p.margin)} for the home team (±${p.band})`)},
    {text: T(`Elo μόνο του: ${tn(p.home)} ${Math.round(p.p_elo * 100)}%`, `Elo alone: ${tn(p.home)} ${Math.round(p.p_elo * 100)}%`)},
  ]);
  return tilt(h('article', {class: 'card' + (isFocus(p.home, p.away) ? ' is-focus' : '')},
    h('div', {class: 'card-when'}, h('span', null, `${dayLabel(p.d)} · ${p.t || '–'}`), confBadge(Math.max(p.p, 1 - p.p))),
    h('div', {class: 'board'},
      h('div', {class: 'board-row board-head', 'aria-hidden': 'true'}, h('span', {title: T('Πρώτα ο γηπεδούχος', 'Home team first')}, T('Ομάδες', 'Teams')), h('span', {title: T('Νίκες-ήττες', 'Wins-losses')}, T('Ν-Η', 'W-L')), h('span', null, T('Πρόβλεψη', 'Prediction'))),
      h('div', {class: 'board-row' + (homeFav ? ' fav' : '')}, tlink(p.home), h('span', {class: 'elo', title: T('Γηπεδούχος · ρεκόρ', 'Home team · record')}, record(p.home)), h('span', {class: 'pts'}, p.phs)),
      h('div', {class: 'board-row' + (homeFav ? '' : ' fav')}, tlink(p.away), h('span', {class: 'elo'}, record(p.away)), h('span', {class: 'pts'}, p.pas))),
    bar,
    h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', {class: 'muted', title: `Elo ${p.home_elo} – ${p.away_elo}`}, T(`πιθανότητα νίκης · ±${p.band} π.`, `win probability · ±${p.band} pts`)), h('span', null, ap + '%')),
    (p.notes || []).map(n => h('div', {class: 'card-note'}, n))));
}

// ---------------------------------------------------------------- played games
/** The model's call for a played game: exact score, chosen winner + probability.
 *  (Where the pick came from, pk.src, still decides what counts in the record and the
 *  model stats; the user asked not to label it on the page, 07/10/2026.) */
/** "88/121" whose first number counts up (countUp). */
function fraction(n, of) {
  return h('span', {class: 'frac', 'data-count': n, 'data-of': of}, `${n}/${of}`);
}

function predCell(pk, home) {
  if (!pk) return h('span', {class: 'muted'}, '–');
  const pw = pk.w === home ? pk.p : 1 - pk.p;
  return h('span', {class: 'pred'}, h('b', null, `${pk.phs}–${pk.pas}`), ` · ${tn(pk.w)} ${pctProb(pw)}`);
}
function outcomeCell(g) {
  const o = outcome(g);
  if (!o) return '';
  return h('span', {style: 'display:inline-flex;gap:6px;align-items:center'}, verdict(o.ok), o.hit ? hitBadge(o.prob) : null, o.sharp ? sharpBadge(o.err) : null);
}

/** Results with the model's exact call next to the real score; confident hits glow gold. */
function resultsTable(games, opts = {}) {
  return table([
    {label: T('Ημέρα', 'Date'), area: 'date', sort: g => g.d, render: g => dayLabel(g.d)},
    {label: T('Γηπεδούχος', 'Home'), area: 'home', sort: g => g.home, render: g => h('span', {class: g.hs > g.as ? 'strong' : null}, tlink(g.home))},
    {label: T('Σκορ', 'Score'), area: 'score', num: true, render: g => h('span', {class: 'score-cell'}, h('span', null, g.hs), h('i', null, ' – '), h('span', null, g.as))},
    {label: T('Φιλοξενούμενος', 'Away'), area: 'away', sort: g => g.away, render: g => h('span', {class: g.as > g.hs ? 'strong' : null}, tlink(g.away))},
    {label: T('Πρόβλεψη μοντέλου', 'Model prediction'), area: 'pred', cap: T('Πρόβλεψη', 'Prediction'), render: g => predCell(g.pick, g.home)},
    {label: T('Σφάλμα διαφοράς', 'Margin error'), area: 'err', cap: true, num: true, info: 'mae', sort: g => g.pick ? marginErr(g.pick, g.hs, g.as) : 999, render: g => g.pick ? marginErr(g.pick, g.hs, g.as) + T(' π.', ' pts') : ''},
    {label: T('Αποτέλεσμα', 'Result'), area: 'out', sort: g => g.pick ? (outcome(g).hit ? 2 : outcome(g).ok ? 1 : 0) : -1, render: outcomeCell},
  ], games, {sortIdx: 0, dir: -1, empty: opts.empty, cards: 'results', paged: true,
    rowClass: g => [isFocus(g.home, g.away) ? 'is-focus' : '', outcome(g)?.hit ? 'hit' : ''].join(' ').trim() || null});
}

/** One played game in the ticker: the teams, then the result and the model's call side by side. */
function tickerItem(g) {
  const hw = g.hs > g.as, o = outcome(g), pk = g.pick;
  const pickWinnerProb = pk ? (pk.w === g.home ? pk.p : 1 - pk.p) : null;
  return h('a', {class: 'tick' + (o?.hit ? ' hit' : ''), href: teamHref(isFocus(g.away) ? g.away : g.home), draggable: 'false',
    title: `${tn(g.home)} ${g.hs}–${g.as} ${tn(g.away)}` + (pk ? T(` · πρόβλεψη ${pk.phs}–${pk.pas}`, ` · prediction ${pk.phs}–${pk.pas}`) : '')},
    h('span', {class: 't-date'}, h('span', null, dayLabel(g.d)), o ? (o.hit ? hitBadge(o.prob) : verdict(o.ok)) : h('span')),
    h('span', {class: 't-team' + (hw ? '' : ' lost')}, crest(g.home, 18), h('span', null, tn(g.home))),
    h('span', {class: 't-team' + (hw ? ' lost' : '')}, crest(g.away, 18), h('span', null, tn(g.away))),
    h('span', {class: 't-boxes'},
      h('span', {class: 't-box t-result'}, h('small', null, T('Αποτέλεσμα', 'Result')), h('b', null, `${g.hs}–${g.as}`)),
      h('span', {class: 't-box t-pred' + (o ? (o.ok ? ' ok' : ' bad') : '')}, h('small', null, T('Πρόβλεψη', 'Prediction')),
        pk ? h('b', null, `${pk.phs}–${pk.pas}`) : h('b', {class: 'muted'}, '–'),
        pk ? h('em', null, `${tn(pk.w)} ${pctProb(pickWinnerProb)}`) : null)));
}

/** Latest results strip: scrolls by itself, drags with the mouse, swipes on touch. */
function resultsTicker(games) {
  const strip = h('div', {class: 'ticker', role: 'region', 'aria-label': T('Τελευταία αποτελέσματα και προβλέψεις', 'Latest results and predictions'), tabindex: '0'}, games.map(tickerItem));
  return h('div', {class: 'ticker-wrap'}, autoScroll(strip));
}

/** Gold "hall of fame" card for a confident, correct call. */
function hofCard(g) {
  const o = outcome(g), hw = g.hs > g.as;
  return h('a', {class: 'hof-card', href: teamHref(winnerOf(g))},
    h('div', {class: 'hof-top'}, h('span', null, `${dayLabel(g.d)} · ${g.s}`), hitBadge(o.prob)),
    h('div', {class: 'hof-match'},
      h('div', {class: 'hof-row' + (hw ? ' won' : '')}, h('span', {style: 'display:flex;gap:8px;align-items:center'}, crest(g.home, 22), tn(g.home)), h('b', null, g.hs)),
      h('div', {class: 'hof-row' + (hw ? '' : ' won')}, h('span', {style: 'display:flex;gap:8px;align-items:center'}, crest(g.away, 22), tn(g.away)), h('b', null, g.as))),
    h('div', {class: 'hof-foot'}, h('span', null, T('Πρόβλεψη ', 'Prediction '), h('b', null, `${g.pick.phs}–${g.pick.pas}`)),
      o.sharp ? sharpBadge(o.err) : h('span', null, T(`απόκλιση ${o.err} π.`, `margin error ${o.err} pts`))));
}

// ---------------------------------------------------------------- hero
function hero(p) {
  const nr = D.next, conf = confidentPicks(), hits = conf.filter(g => outcome(g).ok).length;
  const copy = h('div', null,
    h('div', {class: 'eyebrow'}, h('span', {class: 'live-dot'}), `Stoiximan GBL · ${season}`),
    h('h1', null, nr.length ? T(`${roundNo}η αγωνιστική`, `Round ${roundNo}`) : `Basket League ${season}`),
    h('p', {class: 'hero-sub'}, nr.length
      ? `${nextRoundDates()} · ${nGames(nr.length)} · ` + T(`προβλέψεις με το μοντέλο ${M.version}`, `predictions by model ${M.version}`)
      : T(`Ενημέρωση ${D.updated}`, `Updated ${D.updated}`)),
    h('div', {class: 'hero-cta'}, h('a', {class: 'btn btn-cta', href: url('predictions')}, T('Όλες οι προβλέψεις →', 'All predictions →')), h('a', {class: 'btn btn-ghost', href: url('model')}, T('Πώς δουλεύει', 'How it works'))),
    h('div', {class: 'hero-stats'},
      h('div', {class: 'hero-stat'}, h('b', {'data-count': Math.round(M.acc * 100), 'data-fmt': 'pct'}, pct(M.acc)), h('span', null, T('ακρίβεια', 'accuracy')),
        M.n_test ? h('small', null, fraction(Math.round(M.acc * M.n_test), M.n_test), T(' εύστοχες προβλέψεις συνολικά', ' correct predictions in total')) : null),
      // The average margin error (±10) is left to the Model page, where it can be explained.
      conf.length ? h('div', {class: 'hero-stat'}, h('b', null, fraction(hits, conf.length)), h('span', null, T('🔥 επιτυχημένες προβλέψεις ≥80%', '🔥 successful ≥80% predictions')),
        h('small', null, T(`αγώνες όπου το μοντέλο έδινε ${HIT_THRESHOLD * 100}% και πάνω`, `games where the model gave ${HIT_THRESHOLD * 100}% or more`))) : null));
  const inner = h('div', {class: 'banner-inner'}, copy);
  if (p) {
    const homeFav = p.p >= 0.5, hp = Math.round(p.p * 100);
    inner.append(tilt(h('div', {class: 'feature'},
      h('div', {class: 'feature-when'}, h('b', null, isFocus(p.home, p.away) ? T('★ Η ομάδα σου', '★ Your team') : T('Πρώτος αγώνας', 'First game')), h('span', null, `${dayLabel(p.d)} · ${p.t || ''}`)),
      h('div', {class: 'feature-match'},
        h('a', {class: 'feature-team' + (homeFav ? ' fav' : ''), href: teamHref(p.home)}, crest(p.home, 56), h('span', null, tn(p.home))),
        h('div', {class: 'feature-pred'},
          h('small', null, T('Πρόβλεψη ', 'Prediction '), h('span', {class: 'brand-word'}, BRAND.name)),
          h('div', {class: 'feature-score'}, h('span', null, p.phs), h('span', {class: 'dash'}, '–'), h('span', null, p.pas))),
        h('a', {class: 'feature-team' + (homeFav ? '' : ' fav'), href: teamHref(p.away)}, crest(p.away, 56), h('span', null, tn(p.away)))),
      probBar(p, 'prob-hero'),
      h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', null, T('πιθανότητα νίκης', 'win probability')), h('span', null, (100 - hp) + '%'))), 4));
  }
  return h('section', {class: 'banner hero'}, h('div', {class: 'ball', 'aria-hidden': 'true'}), inner);
}
