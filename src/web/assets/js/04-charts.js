// charts — SVG charts drawn from D. Every chart has a hover/focus tooltip and its
// values are also available as text (standings table, Elo table, calibration table).

/** Elo of every team relative to 1500, as diverging bars (blue above, red below). */
function eloBars(host) {
  host.replaceChildren();
  const rows = [...D.standings].sort((a, b) => b.elo - a.elo);
  const W = Math.max(host.clientWidth, 300), rowH = 26, barH = 16, top = 8, labelW = Math.min(170, W * 0.36), valW = 44;
  const H = top + rows.length * rowH + 22;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Elo ανά ομάδα σε σχέση με το 1500'}, host);
  const ext = Math.max(50, ...rows.map(r => Math.abs(r.elo - 1500)));
  const x0 = labelW + valW, x1 = W - valW, sx = v => x0 + (v + ext) / (2 * ext) * (x1 - x0), mid = sx(0);
  [-ext, -ext / 2, ext / 2, ext].forEach(v => {
    s('line', {x1: sx(v), x2: sx(v), y1: top - 4, y2: H - 20, class: 'grid'}, svg);
    stext(svg, sx(v), H - 6, String(1500 + Math.round(v)), {'text-anchor': 'middle', class: 'axis-label'});
  });
  stext(svg, mid, H - 6, '1500', {'text-anchor': 'middle', class: 'axis-label'});
  rows.forEach((r, i) => {
    const y = top + i * rowH, d = r.elo - 1500;
    const g = s('g', {class: 'bar-row' + (r.team === state.focus ? ' is-focus' : '')}, svg);
    stext(g, labelW - 8, y + barH - 3, r.team, {'text-anchor': 'end'});
    const w = Math.max(1, Math.abs(sx(d) - mid)), rad = Math.min(4, w), xs = d >= 0 ? mid : mid - w;
    // Rounded at the data end, square at the baseline.
    const path = d >= 0
      ? `M${xs},${y} h${w - rad} a${rad},${rad} 0 0 1 ${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 1 -${rad},${rad} h-${w - rad} z`
      : `M${xs + w},${y} h-${w - rad} a${rad},${rad} 0 0 0 -${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 0 ${rad},${rad} h${w - rad} z`;
    s('path', {d: path, class: d >= 0 ? 'bar-pos' : 'bar-neg', style: `--d:${i * 40}ms`}, g);
    stext(g, d >= 0 ? mid + w + 6 : mid - w - 6, y + barH - 3, String(r.elo), {'text-anchor': d >= 0 ? 'start' : 'end'});
    const hit = s('rect', {x: 0, y: y - 4, width: W, height: rowH, class: 'bar-hit', tabindex: 0, role: 'link', 'aria-label': `${r.team}, Elo ${r.elo}`}, g);
    hover(hit, () => [{text: `Elo ${r.elo}`}, {text: `${r.team} · ${signed(d)} από τον μέσο όρο`}, {text: `${r.pos}ος · ${r.w}-${r.l} · κλικ για τη σελίδα της`}]);
    hit.addEventListener('click', () => { location.hash = teamHref(r.team); });
    hit.addEventListener('keydown', e => { if (e.key === 'Enter') location.hash = teamHref(r.team); });
  });
  s('line', {x1: mid, x2: mid, y1: top - 4, y2: H - 20, class: 'baseline'}, svg);
}

function eloAt(team, t) {
  let v = null;
  for (const seg of D.elo_history[team] || []) for (const [d, e] of seg) { if (parse(d) <= t) v = e; else return v; }
  return v;
}

/** Elo over time: `team` in the accent colour, everyone else as grey context. */
function eloLines(host, team) {
  host.replaceChildren();
  const W = Math.max(host.clientWidth, 300), H = 280, m = {l: 40, r: 78, t: 18, b: 26};
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Εξέλιξη Elo, ${team}`}, host);
  const all = Object.values(D.elo_history).flat(2);
  // Ordinal x: one slot per game day so summers don't eat the width; 3-slot gap per new season.
  const dates = [...new Set(all.map(p => p[0]))].sort();
  const starts = new Set(D.season_starts.slice(1));
  const pos = {}; let k = 0;
  dates.forEach(d => { if (starts.has(d)) k += 3; pos[d] = k++; });
  const sx = d => m.l + pos[d] / Math.max(1, k - 1) * (W - m.l - m.r);
  let lo = Math.min(...all.map(p => p[1])), hi = Math.max(...all.map(p => p[1]));
  lo = Math.floor((lo - 10) / 50) * 50; hi = Math.ceil((hi + 10) / 50) * 50;
  const sy = v => m.t + (hi - v) / (hi - lo) * (H - m.t - m.b);
  for (let v = lo; v <= hi; v += 50) {
    s('line', {x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: v === 1500 ? 'baseline' : 'grid'}, svg);
    stext(svg, m.l - 6, sy(v) + 4, String(v), {'text-anchor': 'end', class: 'axis-label'});
  }
  let prevMonth = '', prevX = -Infinity;
  dates.forEach(d => {
    const mo = d.slice(0, 7), x = sx(d);
    if (mo !== prevMonth && x - prevX > 46) { const dt = parse(d); stext(svg, x, H - 8, `${MONTHS[dt.getMonth()]} '${String(dt.getFullYear()).slice(2)}`, {class: 'axis-label'}); prevX = x; }
    prevMonth = mo;
  });
  D.season_starts.slice(1).forEach(st => {
    const i = dates.indexOf(st), x = i > 0 ? (sx(st) + sx(dates[i - 1])) / 2 : sx(st);
    s('line', {x1: x, x2: x, y1: m.t, y2: H - m.b, class: 'season-mark'}, svg);
    stext(svg, x + 4, m.t - 6, 'νέα σεζόν', {class: 'axis-label'});
  });
  const pathOf = seg => seg.map((p, i) => (i ? 'L' : 'M') + sx(p[0]).toFixed(1) + ',' + sy(p[1]).toFixed(1)).join('');
  for (const [t, segs] of Object.entries(D.elo_history)) if (t !== team) segs.forEach(sg => s('path', {d: pathOf(sg), class: 'line-ctx'}, svg));
  const fsegs = D.elo_history[team] || [];
  fsegs.forEach(sg => {
    const path = s('path', {d: pathOf(sg), class: 'line-focus'}, svg);
    if (!REDUCED_MOTION) {
      const len = path.getTotalLength();
      path.style.strokeDasharray = len; path.style.setProperty('--len', len); path.classList.add('draw');
    }
  });
  const last = fsegs.length ? fsegs[fsegs.length - 1].slice(-1)[0] : null;
  if (last) {
    s('circle', {cx: sx(last[0]), cy: sy(last[1]), r: 4.5, class: 'end-dot'}, svg);
    stext(svg, sx(last[0]) + 8, sy(last[1]) + 4, `${team} ${Math.round(last[1])}`, {style: 'fill:var(--text-primary);font-weight:700'});
  }
  const cross = s('line', {y1: m.t, y2: H - m.b, class: 'crosshair', visibility: 'hidden'}, svg);
  const overlay = s('rect', {x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent'}, svg);
  overlay.addEventListener('pointermove', e => {
    const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width;
    let best = dates[0], bd = Infinity;
    for (const d of dates) { const dd = Math.abs(sx(d) - px); if (dd < bd) { bd = dd; best = d; } }
    const t = parse(best), x = sx(best);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('visibility', 'visible');
    const vals = Object.keys(D.elo_history).map(tm => [tm, eloAt(tm, t)]).filter(v => v[1] !== null).sort((a, b) => b[1] - a[1]);
    const fv = eloAt(team, t);
    showTip(e, [{text: fv === null ? team : `${team} ${Math.round(fv)}`, cls: 't-val'}, {text: fullDate(best), cls: 't-sub'},
      ...vals.map(([tm, v]) => ({text: `${Math.round(v)}  ${tm}`, key: tm === team ? css('--accent') : css('--context'), cls: 't-sub'}))]);
  });
  overlay.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
}

/** Group picks by the probability given to the favourite. */
function calibrationBins(games) {
  const bins = [[0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.01]].map(([a, b]) => ({a, b, n: 0, sp: 0, won: 0}));
  for (const g of games) {
    const pf = favProb(g.pick), favHome = g.pick.p >= 0.5;
    const bin = bins.find(x => pf >= x.a && pf < x.b);
    if (!bin) continue;
    bin.n++; bin.sp += pf; bin.won += (favHome === (g.hs > g.as)) ? 1 : 0;
  }
  return bins.filter(b => b.n);
}

/** Reliability diagram: predicted favourite probability vs how often it actually won. */
function calibration(host, games) {
  host.replaceChildren();
  const bins = calibrationBins(games);
  const W = Math.max(host.clientWidth, 280), H = Math.min(300, W * 0.78), m = {l: 44, r: 20, t: 12, b: 36};
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Βαθμονόμηση πιθανοτήτων'}, host);
  const sx = v => m.l + (v - 0.5) / 0.5 * (W - m.l - m.r), sy = v => m.t + (1 - v) / 0.6 * (H - m.t - m.b);
  [0.4, 0.6, 0.8, 1.0].forEach(v => { s('line', {x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: 'grid'}, svg); stext(svg, m.l - 6, sy(v) + 4, pct(v), {'text-anchor': 'end', class: 'axis-label'}); });
  [0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach(v => stext(svg, sx(v), H - 18, pct(v), {'text-anchor': 'middle', class: 'axis-label'}));
  stext(svg, (m.l + W - m.r) / 2, H - 2, 'πιθανότητα που έδωσε το μοντέλο στο φαβορί', {'text-anchor': 'middle', class: 'axis-label'});
  s('line', {x1: sx(0.5), y1: sy(0.5), x2: sx(1), y2: sy(1), class: 'diag'}, svg);
  stext(svg, sx(0.6) + 6, sy(0.6) + 16, 'τέλεια βαθμονόμηση', {class: 'axis-label'});
  bins.forEach(b => {
    const px = b.sp / b.n, py = Math.max(0.4, b.won / b.n);
    s('circle', {cx: sx(px), cy: sy(py), r: 5, class: 'cal-dot'}, svg);
    stext(svg, sx(px) + 9, sy(py) + 4, String(b.n), {class: 'axis-label'});
    hover(s('circle', {cx: sx(px), cy: sy(py), r: 14, fill: 'transparent', tabindex: 0}, svg),
      () => [{text: `${pct(b.won / b.n)} νίκες του φαβορί`}, {text: `μέση πρόβλεψη ${pct(px)} · ${b.n} αγώνες`}]);
  });
}

/** Draw every chart placeholder inside `root` (called after each render and on resize/theme change). */
function drawCharts(root) {
  root.querySelectorAll('[data-chart]').forEach(c => {
    if (c.dataset.chart === 'bars') eloBars(c);
    else if (c.dataset.chart === 'lines') eloLines(c, c.dataset.team || state.focus);
    else if (c.dataset.chart === 'cal') calibration(c, played.filter(g => g.pick && g.pick.src === 'wf'));
  });
}
