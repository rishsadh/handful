/* Handful - drawing and motion layer.
 *
 * Icons, the motion helpers, and the generic chart builders. Nothing here knows about
 * DATA: every builder takes its numbers as arguments, so a chart cannot invent a value
 * it was not handed.
 *
 * Engine ownership, per DESIGN.md and D-025:
 *   CSS  owns background, border-color, color, box-shadow, hover, focus, layout.
 *   WAAPI owns transform, opacity, stroke-dashoffset and count-ups - and only on
 *         elements carrying data-anim.
 * Never let a CSS transition name transform or opacity on a [data-anim] element.
 *
 * Every animation runs FROM an offset TO the element's real resting state, so when
 * prefers-reduced-motion is set we simply skip the animation and the correct final
 * state is already in the DOM. Content never waits on a timeline.
 */
'use strict';

/* ---------------------------------------------------------------- motion primitives */

const EASE = 'cubic-bezier(.2,.7,.3,1)';
const DUR = { micro: 180, el: 320, seq: 520 };

const reduced = () =>
  window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Animate, unless the visitor asked us not to.
 *
 * Deferred by a frame, and skipped entirely if the node never made it into the document.
 * Views are built detached and appended by the caller, and an animation started on a
 * detached element can sit in `running` forever without progressing - which leaves the
 * element frozen at the first keyframe. That is a stuck 10px offset, not a wobble: it is
 * how the compare cards ended up permanently out of alignment with each other.
 */
function anim(node, keyframes, opts) {
  if (reduced() || !node || !node.animate) return;
  requestAnimationFrame(() => {
    if (!node.isConnected) return;
    node.animate(keyframes, { easing: EASE, fill: 'none', ...opts });
  });
}

/** Fade-and-rise a set of nodes in sequence. Restrained distance, per the register. */
function riseIn(nodes, { dy = 10, delay = 0, step = 40, duration = DUR.el } = {}) {
  nodes.forEach((n, i) => {
    n.setAttribute('data-anim', 'rise');
    anim(n, [
      { opacity: 0, transform: `translateY(${dy}px)` },
      { opacity: 1, transform: 'none' },
    ], { duration, delay: delay + i * step });
  });
}

/**
 * FLIP. Reads positions keyed by data-flip, runs the mutation, then animates each
 * surviving element from where it was to where it now is. Layout properties are never
 * animated - only transform.
 */
function flip(root, mutate) {
  const read = () => {
    const m = new Map();
    root.querySelectorAll('[data-flip]').forEach((n) => m.set(n.dataset.flip, n.getBoundingClientRect()));
    return m;
  };
  const before = reduced() ? null : read();
  mutate();
  if (!before) return;
  root.querySelectorAll('[data-flip]').forEach((n) => {
    const b = before.get(n.dataset.flip);
    if (!b) {
      n.setAttribute('data-anim', 'flip-in');
      anim(n, [{ opacity: 0, transform: 'scale(.94)' }, { opacity: 1, transform: 'none' }],
        { duration: DUR.el });
      return;
    }
    const a = n.getBoundingClientRect();
    const dx = b.left - a.left, dy = b.top - a.top;
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
    n.setAttribute('data-anim', 'flip');
    anim(n, [{ transform: `translate(${dx}px,${dy}px)` }, { transform: 'none' }],
      { duration: 420 });
  });
}

/** Count a number up to its real value. The final text is written first, then animated. */
function countUp(node, to, format, { duration = 620, delay = 0 } = {}) {
  node.textContent = format(to);
  if (reduced() || !Number.isFinite(to)) return;
  node.setAttribute('data-anim', 'count');
  const t0 = performance.now() + delay;
  const tick = (now) => {
    const t = (now - t0) / duration;
    if (t < 0) { requestAnimationFrame(tick); return; }
    if (t >= 1) { node.textContent = format(to); return; }
    const e = 1 - Math.pow(1 - t, 3);
    node.textContent = format(to * e);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/**
 * Draw an SVG path on, using stroke-dashoffset. The path is fully drawn in the DOM.
 *
 * Deferred by a frame: charts are built detached and appended by the caller, and
 * getTotalLength throws on an element that is not yet rendered.
 */
function drawPath(path, { duration = DUR.seq, delay = 0 } = {}) {
  if (reduced() || !path.getTotalLength) return;
  requestAnimationFrame(() => {
    let len = 0;
    try { len = path.getTotalLength(); } catch (e) { return; }
    if (!len || !path.isConnected) return;
    path.setAttribute('data-anim', 'draw');
    anim(path, [
      { strokeDasharray: `${len}`, strokeDashoffset: `${len}` },
      { strokeDasharray: `${len}`, strokeDashoffset: '0' },
    ], { duration, delay });
  });
}

/** Grow a bar from its baseline. scaleX only - width is never animated. */
function growBar(node, { duration = DUR.seq, delay = 0, origin = 'left' } = {}) {
  node.setAttribute('data-anim', 'bar');
  node.style.transformOrigin = `${origin} center`;
  anim(node, [{ transform: 'scaleX(0)' }, { transform: 'none' }], { duration, delay });
}

/** Run a callback the first time a node scrolls into view. Below-fold work stays lazy. */
function onFirstView(node, fn) {
  if (!('IntersectionObserver' in window)) { fn(); return; }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) { io.disconnect(); fn(); return; }
    }
  }, { rootMargin: '0px 0px -10% 0px' });
  io.observe(node);
}

/* ---------------------------------------------------------------- svg primitives */

const NS = 'http://www.w3.org/2000/svg';

function s(tag, attrs, ...kids) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) {
    if (attrs[k] === undefined || attrs[k] === null) continue;
    n.setAttribute(k, String(attrs[k]));
  }
  kids.forEach((c) => c && n.appendChild(c));
  return n;
}
const stext = (x, y, str, attrs) => {
  const t = s('text', { x, y, ...attrs });
  t.textContent = str;
  return t;
};

/* ---------------------------------------------------------------- icons
 *
 * Authored, one stroke weight (1.6 at 24px), no emoji and no unicode glyphs - DESIGN.md.
 * The four band marks are a dial filling clockwise, so the icon set itself encodes the
 * ordering of the bands. Nothing else in the set is decorative.
 */

const ICON = {
  // Band dials: quarter, half, three-quarter, full. The wedge is the data.
  band0: (c) => [s('circle', { cx: 12, cy: 12, r: 8.4, fill: 'none' }),
    s('path', { d: 'M12 12 L12 3.6 A8.4 8.4 0 0 1 20.4 12 Z', fill: c, stroke: 'none' })],
  band1: (c) => [s('circle', { cx: 12, cy: 12, r: 8.4, fill: 'none' }),
    s('path', { d: 'M12 12 L12 3.6 A8.4 8.4 0 0 1 12 20.4 Z', fill: c, stroke: 'none' })],
  band2: (c) => [s('circle', { cx: 12, cy: 12, r: 8.4, fill: 'none' }),
    s('path', { d: 'M12 12 L12 3.6 A8.4 8.4 0 1 1 3.6 12 Z', fill: c, stroke: 'none' })],
  band3: (c) => [s('circle', { cx: 12, cy: 12, r: 8.4, fill: c, stroke: 'none' }),
    s('circle', { cx: 12, cy: 12, r: 8.4, fill: 'none' })],

  // Methods.
  target: () => [s('circle', { cx: 12, cy: 12, r: 8, fill: 'none' }),
    s('circle', { cx: 12, cy: 12, r: 3.2, fill: 'none' }),
    s('path', { d: 'M12 1.6v3M12 19.4v3M1.6 12h3M19.4 12h3', fill: 'none' })],
  equal: () => [s('path', { d: 'M4 7h16M4 12h16M4 17h16', fill: 'none' })],
  rising: () => [s('path', { d: 'M4 19V9M9.5 19V5M15 19v-7M20.5 19v-11', fill: 'none' })],
  dice: () => [s('rect', { x: 4, y: 4, width: 16, height: 16, rx: 3.4, fill: 'none' }),
    s('circle', { cx: 8.6, cy: 8.6, r: 1.15, stroke: 'none', fill: 'currentColor' }),
    s('circle', { cx: 12, cy: 12, r: 1.15, stroke: 'none', fill: 'currentColor' }),
    s('circle', { cx: 15.4, cy: 15.4, r: 1.15, stroke: 'none', fill: 'currentColor' })],

  // Status and structure.
  blocked: () => [s('rect', { x: 4.5, y: 10.5, width: 15, height: 9.5, rx: 2, fill: 'none' }),
    s('path', { d: 'M8.2 10.5V7.8a3.8 3.8 0 0 1 7.6 0v2.7', fill: 'none' })],
  check: () => [s('path', { d: 'M4.5 12.5l5 5 10-11', fill: 'none' })],
  info: () => [s('circle', { cx: 12, cy: 12, r: 8.4, fill: 'none' }),
    s('path', { d: 'M12 11v5.5M12 7.8v.6', fill: 'none' })],
  slots: () => [s('rect', { x: 3, y: 5, width: 5, height: 14, rx: 1.4, fill: 'none' }),
    s('rect', { x: 9.5, y: 5, width: 5, height: 14, rx: 1.4, fill: 'none' }),
    s('rect', { x: 16, y: 5, width: 5, height: 14, rx: 1.4, fill: 'none' })],
  scale: () => [s('path', { d: 'M12 4v16M5 9l7-5 7 5', fill: 'none' })],
};

/** Build an icon. `tint` fills the band wedge; everything else inherits currentColor. */
function icon(name, { size = 18, tint = 'currentColor', cls = '' } = {}) {
  const parts = (ICON[name] || ICON.info)(tint);
  const node = s('svg', {
    width: size, height: size, viewBox: '0 0 24 24', class: `ic ${cls}`.trim(),
    fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true',
  });
  parts.forEach((p) => node.appendChild(p));
  return node;
}

/* ---------------------------------------------------------------- charts
 *
 * Every builder below takes real numbers and renders an explicit empty state when it is
 * handed none. None of them fabricates, interpolates or rounds a value into existence.
 */

/**
 * The score landscape. Every exported candidate plotted by reported minutes against
 * relevance score, with a cut line at the lowest chosen score.
 *
 * The point of the chart: hollow marks sitting ABOVE the cut line scored well enough to
 * be picked and were refused, because their preparation-time band was already full. That
 * is the band cap doing its job, and it is otherwise invisible.
 */
function scoreLandscape({ cands, chosenIds, bandFill, bandLine, bandName, onHover }) {
  // Left margin holds the percent ticks AND the rotated axis title; too tight and the
  // two collide, which is what happened at 46.
  const W = 720, H = 320, m = { t: 18, r: 16, b: 44, l: 62 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const box = document.createElement('div');
  box.className = 'chart';
  if (!cands || !cands.length) {
    box.innerHTML = '<p class="hint">No candidates in this export.</p>';
    return box;
  }

  const chosen = new Set(chosenIds || []);
  const picked = cands.filter((c) => chosen.has(c.id));
  const cut = picked.length ? Math.min(...picked.map((c) => c.s)) : null;

  // Minutes span several orders of magnitude, so the x axis is log. It is labelled as
  // such on the axis itself rather than left for the reader to infer.
  const lx = (v) => Math.log10(Math.max(1, v) + 1);
  const xs = cands.map((c) => lx(c.min));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ss = cands.map((c) => c.s);
  const y0 = Math.min(...ss), y1 = Math.max(...ss);
  const padY = (y1 - y0) * 0.12 || 0.02;

  const X = (v) => m.l + (x1 === x0 ? iw / 2 : ((lx(v) - x0) / (x1 - x0)) * iw);
  const Y = (v) => m.t + ih - ((v - (y0 - padY)) / ((y1 + padY) - (y0 - padY))) * ih;

  const svg = s('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', role: 'img',
    'aria-label': `Relevance score against preparation time for ${cands.length} candidate recipes. `
      + `${picked.length} were chosen.`,
  });

  // Band boundaries at 15, 30 and 60 minutes - the protocol's own cut points.
  [15, 30, 60].forEach((v) => {
    if (v < Math.pow(10, x0) - 1 || v > Math.pow(10, x1) - 1) return;
    svg.appendChild(s('line', {
      x1: X(v), x2: X(v), y1: m.t, y2: m.t + ih, class: 'ax-div',
    }));
  });

  // Axes.
  svg.appendChild(s('line', { x1: m.l, x2: m.l + iw, y1: m.t + ih, y2: m.t + ih, class: 'ax' }));
  svg.appendChild(s('line', { x1: m.l, x2: m.l, y1: m.t, y2: m.t + ih, class: 'ax' }));

  [5, 15, 30, 60, 120, 480].forEach((v) => {
    const px = X(v);
    if (px < m.l - 1 || px > m.l + iw + 1) return;
    svg.appendChild(s('line', { x1: px, x2: px, y1: m.t + ih, y2: m.t + ih + 5, class: 'ax' }));
    svg.appendChild(stext(px, m.t + ih + 18, String(v), { class: 'ax-t', 'text-anchor': 'middle' }));
  });
  svg.appendChild(stext(m.l + iw / 2, H - 8,
    'reported preparation time, minutes (log scale)', { class: 'ax-l', 'text-anchor': 'middle' }));

  [y0, (y0 + y1) / 2, y1].forEach((v) => {
    svg.appendChild(stext(m.l - 9, Y(v) + 4, `${Math.round(v * 100)}%`,
      { class: 'ax-t', 'text-anchor': 'end' }));
  });
  svg.appendChild(stext(15, m.t + ih / 2, 'match', {
    class: 'ax-l', 'text-anchor': 'middle', transform: `rotate(-90 15 ${m.t + ih / 2})`,
  }));

  // The cut line.
  if (cut !== null) {
    const cy = Y(cut);
    const cutLine = s('line', { x1: m.l, x2: m.l + iw, y1: cy, y2: cy, class: 'cutline' });
    svg.appendChild(cutLine);
    svg.appendChild(stext(m.l + iw, cy - 8, 'lowest score that made the list',
      { class: 'ax-t cut-t', 'text-anchor': 'end' }));
    drawPath(cutLine, { duration: 600, delay: 220 });
  }

  // Marks. Unchosen first so the chosen always sit on top.
  const order = [...cands].sort((a, b) => (chosen.has(a.id) ? 1 : 0) - (chosen.has(b.id) ? 1 : 0));
  const marks = [];
  order.forEach((c) => {
    const isPicked = chosen.has(c.id);
    const refused = !isPicked && cut !== null && c.s >= cut;
    const g = s('g', {
      class: `mk ${isPicked ? 'mk-on' : refused ? 'mk-refused' : 'mk-off'}`,
      tabindex: '0', role: 'listitem',
    });
    const cx = X(c.min), cy = Y(c.s);
    if (isPicked) {
      g.appendChild(s('circle', { cx, cy, r: 9.5, class: 'mk-halo' }));
      g.appendChild(s('circle', {
        cx, cy, r: 5.6, fill: bandFill(c.b), stroke: bandLine(c.b), 'stroke-width': 1.6,
      }));
    } else {
      g.appendChild(s('circle', {
        cx, cy, r: refused ? 5 : 3.6,
        fill: refused ? 'none' : bandFill(c.b),
        stroke: bandLine(c.b),
        'stroke-width': refused ? 1.6 : 1,
        'stroke-dasharray': refused ? '2.5 2.2' : null,
        opacity: refused ? 1 : 0.55,
      }));
    }
    const label = `${c.name}. ${c.min} minutes, ${bandName(c.b)}. `
      + `${Math.round(c.s * 100)}% match. `
      + (isPicked ? 'Chosen.' : refused ? 'Scored high enough, refused because its time category was full.' : 'Not chosen.');
    g.appendChild(s('title', {}, document.createTextNode(label)));
    if (onHover) {
      const fire = () => onHover({ c, isPicked, refused, x: cx, y: cy });
      g.addEventListener('pointerenter', fire);
      g.addEventListener('focus', fire);
      g.addEventListener('pointerleave', () => onHover(null));
      g.addEventListener('blur', () => onHover(null));
    }
    marks.push(g);
    svg.appendChild(g);
  });

  box.appendChild(svg);

  // Entrance: marks settle in, chosen last so the eye lands on them.
  if (!reduced()) {
    marks.forEach((g, i) => {
      g.setAttribute('data-anim', 'mark');
      anim(g, [{ opacity: 0, transform: 'scale(.6)' }, { opacity: 1, transform: 'none' }],
        { duration: 300, delay: 60 + i * 5 });
    });
  }
  return box;
}

/**
 * A paired difference against zero, with its confidence interval. The single most
 * important honest graphic on the page: if the interval crosses the zero line, the
 * result is consistent with no difference, and the chart says so without being read.
 */
function intervalPlot({ diff, lo, hi, leftLabel, rightLabel, unit = '' }) {
  const box = document.createElement('div');
  box.className = 'chart';
  if (![diff, lo, hi].every(Number.isFinite)) {
    box.innerHTML = '<p class="hint">No paired comparison in this export.</p>';
    return box;
  }
  const W = 720, H = 132, m = { t: 30, r: 24, b: 40, l: 24 };
  const iw = W - m.l - m.r;
  const span = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(diff)) * 1.35 || 1;
  const X = (v) => m.l + ((v + span) / (2 * span)) * iw;
  const cy = m.t + 20;

  const svg = s('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', role: 'img',
    'aria-label': `Difference ${diff.toFixed(4)}${unit}, 95% interval ${lo.toFixed(4)} to `
      + `${hi.toFixed(4)}. The interval ${lo <= 0 && hi >= 0 ? 'includes' : 'excludes'} zero.`,
  });

  svg.appendChild(s('line', { x1: m.l, x2: m.l + iw, y1: cy, y2: cy, class: 'ax' }));
  // Zero line - the thing everything is judged against.
  svg.appendChild(s('line', { x1: X(0), x2: X(0), y1: m.t - 12, y2: cy + 22, class: 'zero' }));
  svg.appendChild(stext(X(0), m.t - 18, 'no difference', { class: 'ax-t', 'text-anchor': 'middle' }));

  const bar = s('line', { x1: X(lo), x2: X(hi), y1: cy, y2: cy, class: 'ci' });
  svg.appendChild(bar);
  [lo, hi].forEach((v) => svg.appendChild(s('line', {
    x1: X(v), x2: X(v), y1: cy - 8, y2: cy + 8, class: 'ci-cap',
  })));
  svg.appendChild(s('circle', { cx: X(diff), cy, r: 6, class: 'ci-dot' }));

  svg.appendChild(stext(m.l, H - 14, `◀ ${leftLabel}`, { class: 'ax-l' }));
  svg.appendChild(stext(m.l + iw, H - 14, `${rightLabel} ▶`,
    { class: 'ax-l', 'text-anchor': 'end' }));
  svg.appendChild(stext(X(diff), cy - 16, diff.toFixed(4),
    { class: 'ax-t val', 'text-anchor': 'middle' }));

  box.appendChild(svg);
  bar.setAttribute('data-anim', 'ci');
  if (!reduced()) {
    bar.style.transformOrigin = `${X(diff)}px ${cy}px`;
    anim(bar, [{ transform: 'scaleX(0)' }, { transform: 'none' }], { duration: 560, delay: 180 });
  }
  return box;
}

/**
 * Horizontal bars for a small set of labelled values. Zero is drawn as a visible tick,
 * never as nothing - a method that scored zero must not simply vanish from the chart.
 */
function valueBars(rows, { format = (v) => v.toFixed(4), highlight = null } = {}) {
  const box = document.createElement('div');
  box.className = 'vbars';
  if (!rows || !rows.length) {
    box.innerHTML = '<p class="hint">Not available in this export.</p>';
    return box;
  }
  const max = Math.max(...rows.map((r) => Math.abs(r.value) || 0)) || 1;
  rows.forEach((r, i) => {
    const row = document.createElement('div');
    row.className = 'vbar' + (r.label === highlight ? ' is-hi' : '');
    const lab = document.createElement('span');
    lab.className = 'vbar-l';
    lab.textContent = r.label;
    const track = document.createElement('span');
    track.className = 'vbar-track';
    const fill = document.createElement('span');
    fill.className = 'vbar-fill' + (r.value ? '' : ' is-zero');
    fill.style.width = r.value ? `${Math.max(2, (Math.abs(r.value) / max) * 100)}%` : '3px';
    track.appendChild(fill);
    const val = document.createElement('span');
    val.className = 'vbar-v';
    val.textContent = format(r.value);
    row.append(lab, track, val);
    box.appendChild(row);
    if (r.value) growBar(fill, { delay: 100 + i * 70 });
  });
  return box;
}

/**
 * The scale funnel. Widths are log-scaled and labelled as such: six out of two hundred
 * thousand drawn linearly is a bar one pixel wide, which reads as an error rather than
 * as a fact.
 */
function funnel(stages) {
  const box = document.createElement('div');
  box.className = 'funnel';
  const lg = (v) => Math.log10(Math.max(1, v));
  const top = lg(stages[0].value) || 1;
  stages.forEach((st, i) => {
    const row = document.createElement('div');
    row.className = 'fn-row';
    const head = document.createElement('div');
    head.className = 'fn-head';
    const v = document.createElement('span');
    v.className = 'fn-v';
    const lab = document.createElement('span');
    lab.className = 'fn-l';
    lab.textContent = st.label;
    head.append(v, lab);
    const track = document.createElement('div');
    track.className = 'fn-track';
    const fill = document.createElement('div');
    fill.className = 'fn-fill';
    fill.style.width = `${Math.max(6, (lg(st.value) / top) * 100)}%`;
    track.appendChild(fill);
    row.append(head, track);
    if (st.note) {
      const n = document.createElement('div');
      n.className = 'fn-n';
      n.textContent = st.note;
      row.appendChild(n);
    }
    box.appendChild(row);
    countUp(v, st.value, (x) => Math.round(x).toLocaleString('en-GB'), { delay: 80 + i * 110 });
    growBar(fill, { delay: 80 + i * 110, duration: 620 });
  });
  const note = document.createElement('p');
  note.className = 'hint fn-note';
  note.textContent = 'Bar widths are log-scaled. Drawn to scale, the final bar would be '
    + 'narrower than a hairline.';
  box.appendChild(note);
  return box;
}
