// core — shared state, DOM builders, formatting, team helpers, motion, tooltip, toast.
// All modules are concatenated (in file-name order) into one strict-mode IIFE by
// src/web/render.py, so top-level declarations here are visible to later files.

const D = JSON.parse(document.getElementById('data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const REDUCED_MOTION = matchMedia('(prefers-reduced-motion: reduce)').matches;
const FINE_POINTER = matchMedia('(pointer: fine)').matches;

const DAYS = ['Κυρ', 'Δευ', 'Τρι', 'Τετ', 'Πεμ', 'Παρ', 'Σαβ'];
const MONTHS = ['Ιαν', 'Φεβ', 'Μαρ', 'Απρ', 'Μάι', 'Ιουν', 'Ιουλ', 'Αυγ', 'Σεπ', 'Οκτ', 'Νοε', 'Δεκ'];

/** A pick is a "hit" when the model gave the favourite at least this much and was right. */
const HIT_THRESHOLD = 0.8;
/** A pick is "sharp" when the predicted margin was within this many points. */
const SHARP_POINTS = 3;

const STANDING = Object.fromEntries(D.standings.map(r => [r.team, r]));
const TEAMS = D.standings.map(r => r.team);
const LOGOS = D.logos || {};
const season = D.season;
const played = D.games;
const seasonGames = played.filter(g => g.s === season);
const roundNo = Math.max(0, ...D.standings.map(r => r.gp)) + 1;

/** Page registry: pages[name] = ({tab, name}) => Node[]. Filled by the 1x-*.js files. */
const pages = {};

const state = {
  focus: STANDING[localStorage.getItem('gbl-focus')] ? localStorage.getItem('gbl-focus') : D.focus,
  tabs: {},            // last selected tab per tab group
  flashMetric: null,   // metric card to highlight after navigating to the guide
};

// ---------------------------------------------------------------- DOM builders
/** Create an HTML element. Strings become text nodes: CSV/API names never touch innerHTML. */
function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(n.style, v);
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false && c !== '') n.append(c instanceof Node ? c : String(c));
  return n;
}
/** Create an SVG element, optionally appending it to `parent`. */
function s(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function stext(parent, x, y, str, attrs) { const t = s('text', {x, y, ...(attrs || {})}, parent); t.textContent = str; return t; }
const css = name => getComputedStyle(document.querySelector('.viz-root')).getPropertyValue(name).trim();

// ---------------------------------------------------------------- formatting
const parse = iso => new Date(iso + 'T12:00:00');
const pad2 = n => String(n).padStart(2, '0');
const dayLabel = iso => { const d = parse(iso); return `${DAYS[d.getDay()]} ${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}`; };
const fullDate = iso => { const d = parse(iso); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
const pct = x => x == null ? '–' : Math.round(x * 100) + '%';
/** A model probability for display: never claims certainty (99.6% shows as 99%). */
const pctProb = x => x == null ? '–' : Math.min(99, Math.max(1, Math.round(x * 100))) + '%';
const fx = (x, n = 3) => x == null ? '–' : x.toFixed(n);
const signed = x => (x > 0 ? '+' : '') + x;
const streakGr = st => st.replace('W', 'Ν').replace('L', 'Η');

// ---------------------------------------------------------------- teams & picks
const teamHref = t => '#/team/' + encodeURIComponent(t);
const isFocus = (...teams) => teams.includes(state.focus);
const record = t => STANDING[t] ? `${STANDING[t].w}-${STANDING[t].l}` : '';
const winnerOf = g => g.hs > g.as ? g.home : g.away;
const favProb = pk => Math.max(pk.p, 1 - pk.p);
const marginErr = (pk, hs, as) => Math.abs((pk.phs - pk.pas) - (hs - as));

/** Grade a played game's pick: correct? confident hit? sharp margin? */
function outcome(g) {
  const pk = g.pick;
  if (!pk) return null;
  const ok = pk.w === winnerOf(g), prob = favProb(pk), err = marginErr(pk, g.hs, g.as);
  return {ok, prob, err, hit: ok && prob >= HIT_THRESHOLD, sharp: ok && err <= SHARP_POINTS};
}

function crest(team, size = 20) {
  const style = `width:${size}px;height:${size}px`;
  if (LOGOS[team]) return h('img', {class: 'crest', src: LOGOS[team], alt: '', 'aria-hidden': 'true', style, decoding: 'async'});
  const initials = team.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return h('span', {class: 'crest crest-fallback', 'aria-hidden': 'true', style: `${style};font-size:${Math.round(size * 0.4)}px`}, initials);
}
const tlink = (t, size = 18) => h('a', {class: 'tlink', href: teamHref(t), title: t}, crest(t, size), h('span', {class: 'tname'}, t));

// ---------------------------------------------------------------- motion
let revealObserver = null;
/** Fade/slide elements in as they scroll into view, staggered within each group. */
function revealIn(root) {
  const groups = ['.kpis', '.cards', '.hof', '.team-grid', '.timeline', '.grid-3'];
  root.querySelectorAll(groups.map(g => g + ' > *').join(',')).forEach(el => {
    el.classList.add('reveal');
    el.style.setProperty('--d', `${Math.min([...el.parentNode.children].indexOf(el), 12) * 45}ms`);
  });
  root.querySelectorAll(':scope > section:not(.banner), :scope > div, :scope > details').forEach(el => el.classList.add('reveal'));
  if (REDUCED_MOTION || !('IntersectionObserver' in window)) {
    root.querySelectorAll('.reveal').forEach(el => el.classList.add('in'));
    return;
  }
  revealObserver?.disconnect();
  revealObserver = new IntersectionObserver(entries => entries.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); revealObserver.unobserve(e.target); }
  }), {rootMargin: '0px 0px -40px 0px'});
  root.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));
}

/** Animate probability bars / meters from 0 to their target width. */
function growBars(root) {
  const targets = root.querySelectorAll('[data-w]');
  requestAnimationFrame(() => requestAnimationFrame(() => targets.forEach(el => { el.style.width = el.dataset.w; })));
}

/** Count KPI numbers up from zero. data-count = target, data-dec = decimals, data-fmt = pct|pm|plain. */
function countUp(root) {
  root.querySelectorAll('[data-count]').forEach(el => {
    const to = +el.dataset.count, dec = +(el.dataset.dec || 0), fmt = el.dataset.fmt || 'plain';
    const show = v => {
      const n = v.toFixed(dec);
      el.textContent = fmt === 'pct' ? `${n}%` : fmt === 'pm' ? `±${n}` : n;
    };
    if (REDUCED_MOTION) { show(to); return; }
    const t0 = performance.now(), dur = 900;
    const step = now => {
      const k = Math.min(1, (now - t0) / dur), eased = 1 - Math.pow(1 - k, 3);
      show(to * eased);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/** Subtle 3D tilt that follows the pointer (desktop only, off with reduced motion). */
function tilt(el, max = 5) {
  if (REDUCED_MOTION || !FINE_POINTER) return el;
  el.addEventListener('pointermove', e => {
    const b = el.getBoundingClientRect(), x = (e.clientX - b.left) / b.width - 0.5, y = (e.clientY - b.top) / b.height - 0.5;
    el.style.transform = `perspective(900px) rotateX(${(-y * max).toFixed(2)}deg) rotateY(${(x * max).toFixed(2)}deg) translateY(-2px)`;
  });
  el.addEventListener('pointerleave', () => { el.style.transform = ''; });
  return el;
}

// ---------------------------------------------------------------- tooltip
const tip = document.getElementById('tip');
function showTip(evt, rows) {
  tip.replaceChildren(...rows.map((r, i) => {
    const d = h('div', {class: r.cls || (i === 0 ? 't-val' : 't-sub')});
    if (r.key) { d.classList.add('t-row'); d.append(h('span', {class: 'key', style: `background:${r.key}`})); }
    d.append(r.text);
    return d;
  }));
  tip.hidden = false;
  const pad = 14, w = tip.offsetWidth, ht = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > innerWidth - 8) x = evt.clientX - w - pad;
  if (y + ht > innerHeight - 8) y = evt.clientY - ht - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
const hideTip = () => { tip.hidden = true; };
/** Attach the same tooltip to hover and keyboard focus. */
function hover(node, rowsFn) {
  node.addEventListener('pointermove', e => showTip(e, rowsFn()));
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', () => { const b = node.getBoundingClientRect(); showTip({clientX: b.left + b.width / 2, clientY: b.bottom}, rowsFn()); });
  node.addEventListener('blur', hideTip);
  return node;
}

// ---------------------------------------------------------------- toast
const toastEl = document.getElementById('toast');
let toastTimer;
function showToast(msg, kind, ms) {
  toastEl.textContent = msg;
  toastEl.className = 'toast' + (kind ? ' ' + kind : '');
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
}

/** True when the page is served by scripts/serve.py (Refresh / Contact work). */
const SERVED = location.protocol.startsWith('http');
