// components — reusable UI building blocks (no page logic here).

// ---------------------------------------------------------------- headings & banners
function sectionHead(title, sub, link) {
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
  const btn = h('button', {class: 'info', type: 'button', 'aria-label': `Τι σημαίνει: ${m.title}`,
    onclick: e => { e.preventDefault(); e.stopPropagation(); state.flashMetric = key; location.hash = '#/model/metrics'; }}, 'i');
  return hover(btn, () => [{text: m.title}, {text: m.short}, {text: 'Κλικ για αναλυτική εξήγηση', cls: 't-sub'}]);
}

/** KPI tile. opts: {info, count:{to, dec, fmt}, gold} */
function kpi(label, value, sub, opts = {}) {
  const val = h('div', {class: 'kpi-value'}, value);
  if (opts.count) Object.assign(val.dataset, {count: opts.count.to, dec: opts.count.dec || 0, fmt: opts.count.fmt || 'plain'});
  return h('div', {class: 'kpi' + (opts.gold ? ' gold' : '')},
    h('div', {class: 'kpi-label'}, label, opts.info ? infoDot(opts.info) : null), val, h('div', {class: 'kpi-sub'}, sub));
}

// ---------------------------------------------------------------- tabs
/**
 * Accessible tab group. items: [{key, label, count?, render: () => Node[]}].
 * The chosen tab is remembered per `id` and mirrored in the URL (#/page/tab)
 * with replaceState, so links are shareable without re-rendering the page.
 */
function tabs(id, items, initial, urlBase) {
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
    if (b) { ink.style.left = b.offsetLeft + 'px'; ink.style.width = b.offsetWidth + 'px'; }
  };
  function select(key, user) {
    current = key; state.tabs[id] = key;
    buttons.forEach((b, i) => { const on = items[i].key === key; b.setAttribute('aria-selected', on); b.tabIndex = on ? 0 : -1; });
    panel.setAttribute('aria-labelledby', `tab-${id}-${key}`);
    panel.replaceChildren(h('div', {class: 'tab-panel'}, items.find(t => t.key === key).render()));
    if (user && urlBase) history.replaceState(null, '', `#/${urlBase}/${key}`);
    requestAnimationFrame(moveInk);
    if (user) afterRender(panel);
  }
  select(current, false);
  new ResizeObserver(moveInk).observe(bar);
  return h('div', null, bar, panel);
}

// ---------------------------------------------------------------- tables & controls
/** Sortable table. cols: {label, num?, title?, sort?(row), render(row)} */
function table(cols, rows, opts = {}) {
  let sortIdx = opts.sortIdx ?? -1, dir = opts.dir ?? 1;
  const wrap = h('div', {class: 'table-wrap'});
  function draw() {
    const data = rows.slice();
    if (sortIdx >= 0 && cols[sortIdx].sort) {
      const f = cols[sortIdx].sort;
      data.sort((a, b) => { const x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
    }
    const head = h('tr', null, cols.map((c, i) => {
      const th = h('th', {class: (c.num ? 'num ' : '') + (c.sort ? 'sortable' : ''), title: c.title || null, scope: 'col',
        'aria-sort': i === sortIdx ? (dir > 0 ? 'ascending' : 'descending') : null, tabindex: c.sort ? 0 : null},
        c.label, c.info ? infoDot(c.info) : null, c.sort ? h('span', {class: 'arrow'}, i === sortIdx ? (dir > 0 ? '▲' : '▼') : ' ') : null);
      if (c.sort) {
        const act = () => { if (sortIdx === i) dir = -dir; else { sortIdx = i; dir = c.num ? -1 : 1; } draw(); };
        th.addEventListener('click', act);
        th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
      }
      return th;
    }));
    const body = data.length
      ? data.map(r => h('tr', {class: opts.rowClass ? opts.rowClass(r) : null}, cols.map(c => h('td', {class: c.num ? 'num' : null}, c.render(r)))))
      : [h('tr', null, h('td', {colspan: cols.length, class: 'empty'}, opts.empty || 'Δεν υπάρχουν δεδομένα.'))];
    wrap.replaceChildren(h('table', null, h('thead', null, head), h('tbody', null, body)));
  }
  draw();
  return wrap;
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
    h('span', {class: 'chip ' + (r === 'W' ? 'win' : 'loss'), title: r === 'W' ? 'Νίκη' : 'Ήττα'}, r === 'W' ? 'Ν' : 'Η')));
}
function verdict(ok) {
  if (ok == null) return h('span', {class: 'verdict pending'}, '⏳ εκκρεμεί');
  return h('span', {class: 'verdict ' + (ok ? 'good' : 'bad')}, ok ? '✓ Σωστό' : '✗ Λάθος');
}
function hitBadge(prob) { return h('span', {class: 'hit-badge', title: `Σίγουρη πρόβλεψη (${pctProb(prob)}) που βγήκε σωστή`}, '🔥 ', pctProb(prob)); }
function sharpBadge(err) { return h('span', {class: 'sharp-badge', title: 'Η προβλεπόμενη διαφορά έπεσε σχεδόν ακριβώς'}, '🎯 ', err === 0 ? 'ακριβώς' : `±${err}`); }
/** Confidence label for an upcoming game. */
function confBadge(prob) {
  if (prob >= HIT_THRESHOLD) return h('span', {class: 'conf lock'}, '🔒 σίγουρο');
  if (prob >= 0.6) return h('span', {class: 'conf lean'}, 'φαβορί');
  return h('span', {class: 'conf toss'}, 'ανοιχτό');
}

// ---------------------------------------------------------------- probability bar
function probBar(p, cls = 'prob') {
  const hp = Math.round(p.p * 100), ap = 100 - hp, homeFav = p.p >= 0.5;
  return h('div', {class: cls, role: 'img', tabindex: 0, 'aria-label': `Πιθανότητα νίκης: ${p.home} ${hp}%, ${p.away} ${ap}%`},
    h('div', {class: 'seg ' + (homeFav ? 'accent' : 'track'), 'data-w': `${hp}%`}),
    h('div', {class: 'seg ' + (homeFav ? 'track' : 'accent'), 'data-w': `${ap}%`}));
}

// ---------------------------------------------------------------- prediction card (upcoming)
function predCard(p) {
  const homeFav = p.p >= 0.5, hp = Math.round(p.p * 100), ap = 100 - hp;
  const bar = hover(probBar(p), () => [
    {text: `${p.w} ${Math.max(hp, ap)}%`},
    {text: `Προβλεπόμενη διαφορά ${signed(p.margin)} για τον γηπεδούχο (±${p.band})`},
    {text: `Elo μόνο του: ${p.home} ${Math.round(p.p_elo * 100)}%`},
  ]);
  return tilt(h('article', {class: 'card' + (isFocus(p.home, p.away) ? ' is-focus' : '')},
    h('div', {class: 'card-when'}, h('span', null, `${dayLabel(p.d)} · ${p.t || '–'}`), confBadge(Math.max(p.p, 1 - p.p))),
    h('div', {class: 'board'},
      h('div', {class: 'board-row board-head', 'aria-hidden': 'true'}, h('span', {title: 'Πρώτα ο γηπεδούχος'}, 'Ομάδες'), h('span', {title: 'Νίκες-ήττες'}, 'Ν-Η'), h('span', null, 'Πρόβλεψη')),
      h('div', {class: 'board-row' + (homeFav ? ' fav' : '')}, tlink(p.home), h('span', {class: 'elo', title: 'Γηπεδούχος · ρεκόρ'}, record(p.home)), h('span', {class: 'pts'}, p.phs)),
      h('div', {class: 'board-row' + (homeFav ? '' : ' fav')}, tlink(p.away), h('span', {class: 'elo'}, record(p.away)), h('span', {class: 'pts'}, p.pas))),
    bar,
    h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', {class: 'muted', title: `Elo ${p.home_elo} – ${p.away_elo}`}, `πιθανότητα νίκης · ±${p.band} π.`), h('span', null, ap + '%')),
    (p.notes || []).map(n => h('div', {class: 'card-note'}, n))));
}

// ---------------------------------------------------------------- played games
/** The model's pre-game call: exact score, chosen winner + probability, source. */
function predCell(pk, home) {
  if (!pk) return h('span', {class: 'muted'}, '–');
  const pw = pk.w === home ? pk.p : 1 - pk.p;
  return h('span', {class: 'pred'}, h('b', null, `${pk.phs}–${pk.pas}`), ` · ${pk.w} ${pctProb(pw)}`,
    h('span', {class: 'badge', title: PICK_SOURCES[pk.src].title(pk)}, PICK_SOURCES[pk.src].label));
}
/** Where a played game's pick came from: logged before tip-off, re-predicted later, or walk-forward. */
const PICK_SOURCES = {
  log: {label: 'πριν τον αγώνα', title: pk => `Καταγράφηκε πριν από τον αγώνα · μοντέλο ${pk.v}`},
  retro: {label: 'αναδρομική', title: pk => `Αναδρομική: μοντέλο ${pk.v} εκπαιδευμένο μόνο με αγώνες πριν από την αγωνιστική, χωρίς να ξέρει το σκορ`},
  wf: {label: 'walk-forward', title: () => 'Walk-forward: μοντέλο εκπαιδευμένο μόνο σε προηγούμενους αγώνες'},
};
function retroBadge() {
  return h('span', {class: 'badge', style: 'margin:0', title: 'Βγήκε μετά τον αγώνα, από μοντέλο που είδε μόνο τους προηγούμενους αγώνες. Δεν μετράει στο ρεκόρ.'}, 'αναδρομική');
}
function outcomeCell(g) {
  const o = outcome(g);
  if (!o) return '';
  return h('span', {style: 'display:inline-flex;gap:6px;align-items:center'}, verdict(o.ok), o.hit ? hitBadge(o.prob) : null, o.sharp ? sharpBadge(o.err) : null);
}

/** Results with the model's exact call next to the real score; confident hits glow gold. */
function resultsTable(games, opts = {}) {
  return table([
    {label: 'Ημέρα', sort: g => g.d, render: g => dayLabel(g.d)},
    {label: 'Γηπεδούχος', sort: g => g.home, render: g => h('span', {class: g.hs > g.as ? 'strong' : null}, tlink(g.home))},
    {label: 'Σκορ', num: true, render: g => h('span', {class: 'score-cell'}, `${g.hs} – ${g.as}`)},
    {label: 'Φιλοξενούμενος', sort: g => g.away, render: g => h('span', {class: g.as > g.hs ? 'strong' : null}, tlink(g.away))},
    {label: 'Πρόβλεψη μοντέλου', render: g => predCell(g.pick, g.home)},
    {label: 'Απόκλιση', num: true, info: 'mae', sort: g => g.pick ? marginErr(g.pick, g.hs, g.as) : 999, render: g => g.pick ? marginErr(g.pick, g.hs, g.as) + ' π.' : ''},
    {label: 'Αποτέλεσμα', sort: g => g.pick ? (outcome(g).hit ? 2 : outcome(g).ok ? 1 : 0) : -1, render: outcomeCell},
  ], games, {sortIdx: 0, dir: -1, empty: opts.empty,
    rowClass: g => [isFocus(g.home, g.away) ? 'is-focus' : '', outcome(g)?.hit ? 'hit' : ''].join(' ').trim() || null});
}

/** One played game in the ticker: the teams, then the result and the model's call side by side. */
function tickerItem(g) {
  const hw = g.hs > g.as, o = outcome(g), pk = g.pick;
  const pickWinnerProb = pk ? (pk.w === g.home ? pk.p : 1 - pk.p) : null;
  return h('a', {class: 'tick' + (o?.hit ? ' hit' : ''), href: teamHref(isFocus(g.away) ? g.away : g.home), draggable: 'false',
    title: `${g.home} ${g.hs}–${g.as} ${g.away}` + (pk ? ` · πρόβλεψη ${pk.phs}–${pk.pas}` : '')},
    h('span', {class: 't-date'}, h('span', null, dayLabel(g.d)), o ? (o.hit ? hitBadge(o.prob) : verdict(o.ok)) : h('span')),
    h('span', {class: 't-team' + (hw ? '' : ' lost')}, crest(g.home, 18), h('span', null, g.home)),
    h('span', {class: 't-team' + (hw ? ' lost' : '')}, crest(g.away, 18), h('span', null, g.away)),
    h('span', {class: 't-boxes'},
      h('span', {class: 't-box'}, h('small', null, 'Αποτέλεσμα'), h('b', null, `${g.hs}–${g.as}`)),
      h('span', {class: 't-box t-pred' + (o ? (o.ok ? ' ok' : ' bad') : '')}, h('small', null, 'Πρόβλεψη'),
        pk ? h('b', null, `${pk.phs}–${pk.pas}`) : h('b', {class: 'muted'}, '–'),
        pk ? h('em', null, `${pk.w} ${pctProb(pickWinnerProb)}`) : null)));
}

/** Latest results strip: scrolls by itself, drags with the mouse, swipes on touch. */
function resultsTicker(games) {
  const strip = h('div', {class: 'ticker', role: 'region', 'aria-label': 'Τελευταία αποτελέσματα και προβλέψεις', tabindex: '0'}, games.map(tickerItem));
  return h('div', {class: 'ticker-wrap'}, autoScroll(strip));
}

/** Gold "hall of fame" card for a confident, correct call. */
function hofCard(g) {
  const o = outcome(g), hw = g.hs > g.as;
  return h('a', {class: 'hof-card', href: teamHref(winnerOf(g))},
    h('div', {class: 'hof-top'}, h('span', null, `${dayLabel(g.d)} · ${g.s}`), hitBadge(o.prob)),
    h('div', {class: 'hof-match'},
      h('div', {class: 'hof-row' + (hw ? ' won' : '')}, h('span', {style: 'display:flex;gap:8px;align-items:center'}, crest(g.home, 22), g.home), h('b', null, g.hs)),
      h('div', {class: 'hof-row' + (hw ? '' : ' won')}, h('span', {style: 'display:flex;gap:8px;align-items:center'}, crest(g.away, 22), g.away), h('b', null, g.as))),
    h('div', {class: 'hof-foot'}, h('span', null, 'Πρόβλεψη ', h('b', null, `${g.pick.phs}–${g.pick.pas}`)),
      o.sharp ? sharpBadge(o.err) : h('span', null, `απόκλιση ${o.err} π.`)));
}

// ---------------------------------------------------------------- hero
function hero(p) {
  const nr = D.next, conf = confidentPicks(), hits = conf.filter(g => outcome(g).ok).length;
  const copy = h('div', null,
    h('div', {class: 'eyebrow'}, h('span', {class: 'live-dot'}), `Stoiximan GBL · ${season}`),
    h('h1', null, nr.length ? `${roundNo}η αγωνιστική` : `Basket League ${season}`),
    h('p', {class: 'hero-sub'}, nr.length
      ? `${dayLabel(nr[0].d)} – ${dayLabel(nr[nr.length - 1].d)} · ${nr.length} αγώνες · προβλέψεις με το μοντέλο ${M.version}`
      : `Ενημέρωση ${D.updated}`),
    h('div', {class: 'hero-cta'}, h('a', {class: 'btn btn-cta', href: '#/predictions'}, 'Όλες οι προβλέψεις →'), h('a', {class: 'btn btn-ghost', href: '#/model'}, 'Πώς δουλεύει')),
    h('div', {class: 'hero-stats'},
      h('div', {class: 'hero-stat'}, h('b', {'data-count': Math.round(M.acc * 100), 'data-fmt': 'pct'}, pct(M.acc)), h('span', null, 'ακρίβεια')),
      conf.length ? h('div', {class: 'hero-stat'}, h('b', null, `${hits}/${conf.length}`), h('span', null, '🔥 σίγουρες')) : null,
      h('div', {class: 'hero-stat'}, h('b', {'data-count': M.margin_mae, 'data-dec': 1, 'data-fmt': 'pm'}, `±${M.margin_mae}`), h('span', null, 'πόντοι σφάλμα'))));
  const inner = h('div', {class: 'banner-inner'}, copy);
  if (p) {
    const homeFav = p.p >= 0.5, hp = Math.round(p.p * 100);
    inner.append(tilt(h('div', {class: 'feature'},
      h('div', {class: 'feature-when'}, h('b', null, isFocus(p.home, p.away) ? '★ Η ομάδα σου' : 'Πρώτος αγώνας'), h('span', null, `${dayLabel(p.d)} · ${p.t || ''}`)),
      h('div', {class: 'feature-match'},
        h('a', {class: 'feature-team' + (homeFav ? ' fav' : ''), href: teamHref(p.home)}, crest(p.home, 56), h('span', null, p.home)),
        h('div', {class: 'feature-score'}, h('span', null, p.phs), h('span', {class: 'dash'}, '–'), h('span', null, p.pas)),
        h('a', {class: 'feature-team' + (homeFav ? '' : ' fav'), href: teamHref(p.away)}, crest(p.away, 56), h('span', null, p.away))),
      probBar(p, 'prob-hero'),
      h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', null, 'πιθανότητα νίκης'), h('span', null, (100 - hp) + '%'))), 4));
  }
  return h('section', {class: 'banner hero'}, h('div', {class: 'ball', 'aria-hidden': 'true'}), inner);
}
