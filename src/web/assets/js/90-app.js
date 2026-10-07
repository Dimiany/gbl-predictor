// app — router, header, footer, theme, refresh, scroll effects, boot.

const app = document.getElementById('app');
const root = document.documentElement;

/** Main menu [page key, label]: render.NAV_PAGES (the static HTML of every page has it too). */
const NAV = ROUTES.nav || [['home', 'Αρχική']];

pages.notfound = () => [pageBanner('Η σελίδα δεν βρέθηκε', 'Ίσως άλλαξε η διεύθυνση ή γράφτηκε λάθος.',
  h('a', {class: 'btn btn-ghost', href: url('home')}, '← Στην αρχική'))];

/** Post-render effects for any freshly inserted subtree (page or tab panel). */
function afterRender(container) {
  drawCharts(container);
  revealIn(container);
  growBars(container);
  countUp(container);
  if (state.flashMetric) {
    const card = document.getElementById(`metric-${state.flashMetric}`);
    state.flashMetric = null;
    if (card) {
      setTimeout(() => card.scrollIntoView({behavior: REDUCED_MOTION ? 'auto' : 'smooth', block: 'center'}), 80);
      card.classList.add('flash');
      setTimeout(() => card.classList.remove('flash'), 2200);
    }
  }
}

/** Every team the data mentions (this season's and older ones), for /teams/<slug>. */
const KNOWN_TEAMS = [...new Set([...TEAMS, ...played.flatMap(g => [g.home, g.away])])];

/** /page[/tab]  or  /teams/<team>[/tab]  ->  {page, tab, name} */
function parseRoute() {
  const parts = location.pathname.split('/').filter(Boolean).map(p => decodeURIComponent(p));
  if (!parts.length || (parts.length === 1 && parts[0] === 'index.html')) return {page: 'home'};
  const page = Object.keys(ROUTES.pages).find(k => k !== 'home' && ROUTES.pages[k] === parts[0]);
  const notFound = {page: 'notfound'};
  if (!page || !pages[page]) return notFound;
  if (page === 'teams' && parts.length > 1) {
    const name = KNOWN_TEAMS.find(t => slugOf(t) === parts[1]);
    const tab = tabFromSlug('team', parts[2]);
    return name && tab && parts.length <= 3 ? {page: 'team', name, tab} : notFound;
  }
  if (parts.length === 1) return {page, tab: tabFromSlug(page)};
  const tab = parts.length === 2 && tabFromSlug(page, parts[1]);
  return tab ? {page, tab} : notFound;
}

/** Go to an address inside the site without reloading the page. */
function go(path) {
  if (path !== location.pathname + location.search) history.pushState(null, '', path);
  route(true);
}

function route(scrollTop) {
  hideTip();
  const r = parseRoute();
  app.replaceChildren(...[].concat(pages[r.page](r)).filter(Boolean));
  app.classList.remove('enter'); void app.offsetWidth; app.classList.add('enter');
  const active = r.page === 'team' ? 'teams' : r.page;
  document.querySelectorAll('#nav a, .tabbar a, .sheet a').forEach(a => {
    const on = a.dataset.k === active;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  menuBtn.classList.toggle('current', !TABBAR.some(([k]) => k === active));
  setMenu(false);
  applyMeta(r.page === 'notfound' ? `Η σελίδα δεν βρέθηκε · ${BRAND.name}` : `${r.name || BRAND.name} · ${BRAND.name}`);
  afterRender(app);
  if (scrollTop) window.scrollTo({top: 0});
}

// ---------------------------------------------------------------- header
const nav = document.getElementById('nav');
nav.replaceChildren(...NAV.map(([k, label]) => h('a', {href: url(k), 'data-k': k}, label)));

// ---------------------------------------------------------------- phone tab bar
// Phones get an app-style bar at the bottom, within thumb reach (the top menu row is
// hidden there, app.css). "Μενού" opens a sheet with every page.
const ICONS = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5.5v-6h-5v6H4a1 1 0 0 1-1-1z',
  predictions: 'M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zm0-4.5a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9zm0-3.6a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8z',
  standings: 'M3 20h18M4.5 20v-7h4.5v7M9.75 20V5h4.5v15M15 20v-10h4.5v10',
  teams: 'M12 3l8 3v6c0 4.6-3.3 7.9-8 9-4.7-1.1-8-4.4-8-9V6z',
  menu: 'M4 7h16M4 12h16M4 17h16',
};
function icon(name) {
  const svg = s('svg', {viewBox: '0 0 24 24', width: 22, height: 22, 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor',
    'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'});
  s('path', {d: ICONS[name]}, svg);
  return svg;
}
const TABBAR = [['home', 'Αρχική'], ['predictions', 'Προβλέψεις'], ['standings', 'Βαθμολογία'], ['teams', 'Ομάδες']];
const menuBtn = h('button', {type: 'button', class: 'tb-item', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', 'aria-controls': 'menu-sheet'},
  icon('menu'), h('span', null, 'Μενού'));
const sheet = h('div', {class: 'sheet', id: 'menu-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Όλες οι σελίδες', tabindex: '-1', hidden: true},
  h('div', {class: 'sheet-grip', 'aria-hidden': 'true'}),
  [...NAV, ['help', 'Οδηγίες']].map(([k, label]) => h('a', {href: url(k), 'data-k': k}, label, h('span', {'aria-hidden': 'true'}, '›'))));
const backdrop = h('div', {class: 'sheet-backdrop', hidden: true});
function setMenu(open) {
  sheet.hidden = backdrop.hidden = !open;
  menuBtn.setAttribute('aria-expanded', String(open));
  menuBtn.classList.toggle('open', open);
  if (open) sheet.focus();
}
menuBtn.addEventListener('click', () => setMenu(sheet.hidden));
backdrop.addEventListener('click', () => setMenu(false));
addEventListener('keydown', e => { if (e.key === 'Escape' && !sheet.hidden) { setMenu(false); menuBtn.focus(); } });
document.querySelector('.viz-root').append(backdrop, sheet,
  h('nav', {class: 'tabbar', 'aria-label': 'Πλοήγηση'},
    TABBAR.map(([k, label]) => h('a', {class: 'tb-item', href: url(k), 'data-k': k}, icon(k), h('span', null, label))), menuBtn));

const focusSel = document.getElementById('focus');
focusSel.replaceChildren(...TEAMS.slice().sort().map(t => h('option', {value: t, selected: t === state.focus}, t)));
focusSel.addEventListener('change', e => setFocus(e.target.value));

// Theme: dark by default; the toggle wins and is remembered.
root.dataset.theme = localStorage.getItem('gbl-theme') || 'dark';
document.getElementById('theme').addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('gbl-theme', root.dataset.theme);
  drawCharts(app);
});

// Refresh: sync + retrain + predict + rebuild through scripts/serve.py.
// The public site updates itself (GitHub Actions), so it has no Refresh button.
const refreshBtn = document.getElementById('refresh');
refreshBtn.hidden = PUBLIC;
const resetRefresh = () => { refreshBtn.disabled = false; refreshBtn.classList.remove('busy'); };
refreshBtn.addEventListener('click', async () => {
  if (!SERVED) {
    showToast(`Για να δουλέψει η Ανανέωση, άνοιξε τη σελίδα από το εικονίδιο «${BRAND.name}» στην επιφάνεια εργασίας.`, 'bad', 9000);
    return;
  }
  refreshBtn.disabled = true; refreshBtn.classList.add('busy');
  showToast(SITE.cloud_sync
    ? 'Φέρνω τα νέα δεδομένα από το GitHub και εκπαιδεύω το μοντέλο… (~20 δευτερόλεπτα)'
    : 'Φέρνω νέα αποτελέσματα, εκπαιδεύω το μοντέλο και βγάζω προβλέψεις… (~20 δευτερόλεπτα)');
  try {
    const res = await fetch('/api/refresh', {method: 'POST', headers: {'X-GBL-Refresh': '1'}});
    const body = await res.json();
    if (body.ok) { showToast('Έτοιμο!\n' + body.message, 'good'); setTimeout(() => location.reload(), 1500); }
    else { showToast('Κάτι δεν πήγε καλά:\n' + body.message + '\n\nΔες τις «Οδηγίες».', 'bad'); resetRefresh(); }
  } catch {
    showToast(`Δεν βρέθηκε το πρόγραμμα. Μήπως έκλεισε το μαύρο παράθυρο; Άνοιξε ξανά το «${BRAND.name}».`, 'bad');
    resetRefresh();
  }
});

// Preview links say so on every page, so a test build is never mistaken for the real site.
if (SITE.mode === 'preview') {
  document.querySelector('.viz-root').prepend(h('div', {class: 'preview-strip', role: 'note'},
    h('b', null, 'ΔΟΚΙΜΑΣΤΙΚΗ ΕΚΔΟΣΗ'), ' · αλλαγές προς έγκριση, όχι το κανονικό site · τα μηνύματα της φόρμας πάνε σε δοκιμαστική συλλογή'));
}

// ---------------------------------------------------------------- footer
(function buildFooter() {
  const col = (title, links) => h('div', {class: 'foot-col'}, h('h2', null, title), links.map(([href, t]) => h('a', {href}, t)));
  document.getElementById('foot').replaceChildren(
    h('div', {class: 'foot-inner'},
      h('div', {class: 'foot-col'},
        h('div', {class: 'foot-brand'}, h('img', {src: document.querySelector('.brand-badge img')?.src || '', alt: ''}), BRAND.name),
        h('p', {style: 'margin:0 0 6px;max-width:340px'}, h('b', null, BRAND.tagline), ' · ', BRAND.slogan),
        h('p', {style: 'margin:0;max-width:340px'}, 'Προβλέψεις, βαθμολογία και στατιστικά για τη Stoiximan Basket League. Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα και βαθμολογείται δημόσια.')),
      col('Σελίδες', [[url('home'), 'Αρχική'], [url('predictions'), 'Προβλέψεις'], [url('standings'), 'Βαθμολογία'], [url('teams'), 'Ομάδες'], [url('schedule'), 'Πρόγραμμα']]),
      col('Μοντέλο', [[url('model'), 'Απόδοση'], [url('model', 'metrics'), 'Οδηγός δεικτών'], [url('model', 'how'), 'Πώς δουλεύει'], [url('predictions', 'hits'), '🔥 Hall of Fame']]),
      col('Βοήθεια', [[url('help'), 'Οδηγίες'], [url('about'), 'Σχετικά'], [url('contact'), 'Επικοινωνία']])),
    h('div', {class: 'foot-bottom'},
      h('p', {class: 'foot-disclaimer'},
        'Οι προβλέψεις του ', BRAND.name, ' είναι αποτέλεσμα μαθηματικών υπολογισμών και στατιστικών αλγορίθμων: ένας τρόπος να διαβάσουμε το παιχνίδι μέσα από τους αριθμούς. ',
        h('b', null, 'Δεν αποτελούν σε καμία περίπτωση προτάσεις ή συμβουλές στοιχηματισμού.'))));
})();

// ---------------------------------------------------------------- scroll effects
const progress = document.getElementById('scroll-progress');
const toTop = document.getElementById('to-top');
toTop.addEventListener('click', () => window.scrollTo({top: 0, behavior: REDUCED_MOTION ? 'auto' : 'smooth'}));
let ticking = false;
addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => {
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
    toTop.classList.toggle('show', scrollY > 600);
    ticking = false;
  });
}, {passive: true});

// ---------------------------------------------------------------- navigation
// Links to our own pages swap the content in place (no reload); the address,
// back/forward and "open in new tab" all behave like a normal site.
document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  if (a.target || a.hasAttribute('download')) return;
  const to = new URL(a.href, location.href);
  if (to.origin !== location.origin || /\.\w+$/.test(to.pathname)) return;  // other sites, files
  e.preventDefault();
  go(to.pathname);
});
addEventListener('popstate', () => route(true));

// Old links (#/standings, #/team/PAOK/results) from before the site had real addresses.
if (location.hash.startsWith('#/')) {
  const [p, a, b] = location.hash.slice(2).split('/').map(x => decodeURIComponent(x));
  const to = p === 'team' ? teamHref(a || '', b) : ROUTES.pages[p || 'home'] != null ? url(p || 'home', a) : '/';
  history.replaceState(null, '', to);
}

// ---------------------------------------------------------------- boot
let resizeTimer;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => drawCharts(app), 150); });
route(false);
