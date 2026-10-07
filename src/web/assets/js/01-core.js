// core — shared state, DOM builders, formatting, team helpers, motion, tooltip, toast.
// All modules are concatenated (in file-name order) into one strict-mode IIFE by
// src/web/render.py, so top-level declarations here are visible to later files.

/** Everything the pages show, from data.js (src/web/data.py + render.route_table). */
const D = window.TIPOFF_DATA;
/** Site name and lines (src/config.py SITE_*). */
const BRAND = D.brand || {name: 'TipOff', tagline: 'Greek Basketball Predictor', slogan: '', url: ''};
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
/** Predictions logged before tip-off: the strict record. Retroactive rows are shown but not counted. */
const preGameLog = D.log.filter(r => !r.retro);
const roundNo = Math.max(0, ...D.standings.map(r => r.gp)) + 1;

/** Page registry: pages[name] = ({tab, name}) => Node[]. Filled by the 1x-*.js files. */
const pages = {};

// ---------------------------------------------------------------- addresses
// Every page, tab and team has its own address (/standings, /teams/paok/results).
// The slugs and each address's title come from src/web/render.py (PAGE_SLUGS, TAB_SLUGS).
const ROUTES = D.routes || {pages: {}, tabs: {}, meta: {}};
/** Same rule as render.slug(): "AS Karditsas Iaponiki" -> "as-karditsas-iaponiki". */
const slugOf = t => t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const joinPath = (...parts) => '/' + parts.filter(Boolean).join('/');
/** Address of a page and, optionally, one of its tabs: url('model', 'how') -> '/model/how-it-works'. */
const url = (page, tab) => joinPath(ROUTES.pages[page || 'home'], tab && ROUTES.tabs[page]?.[tab]);
/** Address of a team page (and tab). */
const teamHref = (t, tab) => joinPath(ROUTES.pages.teams, slugOf(t), tab && ROUTES.tabs.team?.[tab]);
/** Tab key for an address part ('' = the first tab, which lives at the page's own address). */
const tabFromSlug = (group, part) => Object.keys(ROUTES.tabs[group] || {}).find(k => ROUTES.tabs[group][k] === (part || ''));

/** Title, description and canonical for the current address (the static <head> of every
 *  page has them too; this keeps them right as the visitor moves around). */
function applyMeta(fallbackTitle) {
  const [title, desc] = ROUTES.meta[location.pathname] || [fallbackTitle, null];
  if (title) document.title = title;
  if (desc) document.querySelector('meta[name="description"]')?.setAttribute('content', desc);
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.href = BRAND.url + (location.pathname === '/' ? '/' : location.pathname);
}

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

/**
 * Endless, self-scrolling strip that can also be dragged with the mouse.
 * The items are cloned once so the loop is seamless. Scrolling pauses while
 * the pointer is over it, while dragging or touching, while it has keyboard
 * focus, when it's off-screen and when the tab is hidden. Reduced motion:
 * no auto-scroll and no clones (it's then a plain scrollable strip).
 */
function autoScroll(strip, speed = 32 /* px per second */) {
  const originals = [...strip.children];
  if (REDUCED_MOTION || originals.length < 2) return strip;
  originals.forEach(n => {
    const c = n.cloneNode(true);
    c.setAttribute('aria-hidden', 'true');
    c.tabIndex = -1;
    strip.append(c);
  });
  // Width of one full set = where the first clone starts.
  const loopWidth = () => strip.children[originals.length].offsetLeft - strip.children[0].offsetLeft;
  const wrap = x => { const w = loopWidth(); return w > 0 ? ((x % w) + w) % w : x; };

  let pos = 0, last = 0, hovering = false, focused = false, visible = true, holdUntil = 0, drag = null;
  const hold = ms => { holdUntil = performance.now() + ms; };

  // Mouse drag; touch and pens scroll natively.
  strip.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    drag = {x: e.clientX, start: strip.scrollLeft, moved: false};
  });
  const onMove = e => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) > 4) { drag.moved = true; strip.classList.add('dragging'); }
    if (drag.moved) { pos = wrap(drag.start - dx); strip.scrollLeft = pos; }
  };
  const onUp = () => {
    if (!drag) return;
    // A drag is not a click: swallow the click that ends it.
    if (drag.moved) strip.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); }, {capture: true, once: true});
    strip.classList.remove('dragging');
    drag = null;
    hold(1500);
  };
  addEventListener('pointermove', onMove);
  addEventListener('pointerup', onUp);
  strip.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') hovering = true; });
  strip.addEventListener('pointerleave', () => { hovering = false; });
  strip.addEventListener('touchstart', () => hold(4000), {passive: true});
  strip.addEventListener('wheel', () => hold(2500), {passive: true});
  strip.addEventListener('focusin', () => { focused = true; });
  strip.addEventListener('focusout', () => { focused = false; });
  if ('IntersectionObserver' in window) new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(strip);

  const step = now => {
    if (last && !strip.isConnected) {  // the page changed: clean up and stop
      removeEventListener('pointermove', onMove);
      removeEventListener('pointerup', onUp);
      return;
    }
    const dt = last ? Math.min(now - last, 64) : 0;
    last = now;
    // Scrolled by hand (touch, wheel, keyboard): carry on from there, inside the loop.
    if (!drag && Math.abs(strip.scrollLeft - pos) > 2) { pos = wrap(strip.scrollLeft); strip.scrollLeft = pos; }
    if (!drag && !hovering && !focused && visible && !document.hidden && now > holdUntil) {
      pos = wrap(pos + speed * dt / 1000);
      strip.scrollLeft = pos;
    }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  return strip;
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

// ---------------------------------------------------------------- site mode
/** Which build this is: 'local' (desktop app), 'live' (public site) or 'preview' (test link). */
const SITE = D.site || {mode: 'local', cloud_sync: false, firestore: null};
const PUBLIC = SITE.mode !== 'local';
/** True when the page is served by scripts/serve.py (Refresh / local contact form work). */
const SERVED = !PUBLIC && location.protocol.startsWith('http');
