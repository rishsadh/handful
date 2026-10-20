/* Handful - the page's interactive layer.
 *
 * One script, one page. It mounts into whichever hosts exist in the document:
 *
 *   #try       the original experiment, run on the reader           (course: the problem)
 *   #lpp       the linear programme with the sliders' numbers live   (course: the method)
 *   #slice     the two-variable graphical slice, draggable           (course: the method)
 *   #dual      the dual, its certificate and the shadow values       (course: the method)
 *   #receipt   the current shortlist as an itemised bill             (course: the method)
 *   #evidence  the validation-run result                             (course: the result)
 *   #view      the demo tabs: picks, compare, history, solved        (course: the demo)
 *   #credits   image attributions from the two manifests
 *
 * Any host that is absent is simply skipped, so this file also serves a page with only
 * some of the courses on it.
 *
 * The shortlist is re-solved here, in the browser, by a score-sorted, capacity-respecting
 * greedy pass. That is not an approximation of the linear programme: because the
 * preparation-time bands partition the candidates, greedy is provably optimal for this
 * structure, and scripts/export_demo.py checks it against scipy.optimize.linprog for every
 * (k, cap) the sliders can produce before writing data.json.
 *
 * No data is collected, nothing is sent anywhere, and there is no analytics. Photographs
 * are self-hosted and appear only where a manifest says one exists for that exact recipe
 * (DESIGN.md, D-027). Drawing and motion live in viz.js, which loads first.
 */
'use strict';

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const esc = (s) => String(s == null ? '' : s);
const fmt = (v, d = 4) => (Number.isFinite(v) ? v.toFixed(d) : '—');
const fmtPct = (v) => (Number.isFinite(v) ? `${Math.round(v * 100)}%` : '—');
// Explicit locale: a bare toLocaleString() follows the viewer's machine and renders
// 230,064 as "2,30,064" on an Indian-English system, which the page's own prose does not.
const fmtInt = (v) => Math.round(v).toLocaleString('en-GB');

let DATA = null;
let PHOTOS = null;   // { recipes: { "<id>": { file, page, ... } } } or null if none
let STOCK = null;    // { role: [ { file, creator, license, ... } ] } or null
let state = { profile: 0, k: 6, cap: 3, view: 'shortlist' };
let lastRender = { view: null, profile: null };

/* ---------------------------------------------------------------- plain-language layer */

const BAND_SHORT = ['Quick', 'Fast', 'Moderate', 'Long'];
const BAND_RANGE = ['15 min or less', '15–30 min', '30–60 min', 'over an hour'];

const METHOD_PLAIN = {
  AI_LP: 'Our method',
  AI_TOPK: 'No variety rule',
  POPULARITY_LP: 'Most popular',
  RANDOM: 'Random pick',
};
const METHOD_ICON = { AI_LP: 'target', AI_TOPK: 'equal', POPULARITY_LP: 'rising', RANDOM: 'dice' };
const methodPlain = (name) => METHOD_PLAIN[name] || name;

const _bandCache = {};
function bandColor(b, suffix) {
  const key = `--b${b}${suffix}`;
  if (!(key in _bandCache)) {
    _bandCache[key] = getComputedStyle(document.documentElement).getPropertyValue(key).trim();
  }
  return _bandCache[key];
}
const bandFill = (b) => bandColor(b, '');
const bandLine = (b) => bandColor(b, 'l');
const bandWash = (b) => bandColor(b, 'w');

/* ---------------------------------------------------------------- photographs
 *
 * Recipe photographs are off. The Food.com images belong to Food.com and the dataset's
 * licence ("Data files (c) Original Authors") does not cover redistributing them, so the
 * page no longer loads the manifest and every recipe card renders without a photo. The
 * code path stays so a licensed source could be plugged in later. Nothing is substituted
 * per recipe; the only photographs on the page are the four CC BY band photos.
 */
function photo(id, cls) {
  if (!PHOTOS || !PHOTOS.recipes || !PHOTOS.recipes[String(id)]) return null;
  const img = el('img', cls || 'ph');
  img.src = `/img/recipes/${PHOTOS.recipes[String(id)].file}`;
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.addEventListener('error', () => img.remove(), { once: true });
  return img;
}
const hasPhotos = () => !!(PHOTOS && PHOTOS.recipes && Object.keys(PHOTOS.recipes).length);

/* ---------------------------------------------------------------- the solver */

function feasibility(cands, k, cap, nBands) {
  const sizes = new Array(nBands).fill(0);
  for (const c of cands) sizes[c.b]++;
  const capacity = sizes.reduce((acc, n) => acc + Math.min(cap, n), 0);
  return { feasible: capacity >= k, capacity, sizes };
}

function solve(cands, k, cap, key) {
  const order = [...cands].sort((a, b) => (b[key] - a[key]) || (a.id - b.id));
  const used = {};
  const chosen = [];
  for (const c of order) {
    if (chosen.length === k) break;
    const u = used[c.b] || 0;
    if (u < cap) { chosen.push(c); used[c.b] = u + 1; }
  }
  return chosen.length === k ? chosen : null;
}

function topk(cands, k, key) {
  const order = [...cands].sort((a, b) => (b[key] - a[key]) || (a.id - b.id));
  return order.length >= k ? order.slice(0, k) : null;
}

function randomPick(cands, k, cap, seed) {
  let s = seed >>> 0;
  const rnd = () => { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 1e6) / 1e6; };
  const order = [...cands].map((c) => ({ c, r: rnd() })).sort((a, b) => a.r - b.r).map((x) => x.c);
  const used = {};
  const chosen = [];
  for (const c of order) {
    if (chosen.length === k) break;
    const u = used[c.b] || 0;
    if (u < cap) { chosen.push(c); used[c.b] = u + 1; }
  }
  return chosen.length === k ? chosen : null;
}

const bandUsage = (list, nBands) => {
  const u = new Array(nBands).fill(0);
  for (const c of list) u[c.b]++;
  return u;
};
const totalScore = (list, key) => list.reduce((a, c) => a + c[key], 0);
const nBands = () => DATA.meta.band_labels.length;

/* ---------------------------------------------------------------- small parts */

function bandName(i) { return DATA.meta.band_labels[i]; }
function bandPlain(i) { return BAND_SHORT[i] || bandName(i); }
function bandRange(i) { return BAND_RANGE[i] || DATA.meta.band_bounds[bandName(i)] || ''; }

function section(title, sub, iconName) {
  const wrap = el('section', 'sec');
  const h = el('div', 'sec-h');
  if (iconName) h.appendChild(icon(iconName, { size: 17 }));
  h.appendChild(el('h3', null, title));
  wrap.appendChild(h);
  if (sub) wrap.appendChild(el('p', 'sec-sub', sub));
  return wrap;
}

function stat(label, value, note) {
  const d = el('div');
  d.appendChild(el('div', 'stat-label', label));
  d.appendChild(el('div', 'stat-value', value));
  if (note) d.appendChild(el('div', 'stat-note', note));
  return d;
}

function infeasibleNotice(feas, k, cap) {
  const d = el('div', 'banner banner-block');
  d.innerHTML =
    `<strong>Can't fit that many in.</strong><br>` +
    `With at most ${cap} recipe${cap === 1 ? '' : 's'} allowed per time category, and only ` +
    `${feas.sizes.join(' / ')} recipes available in each of the four categories, the most ` +
    `we can offer is <strong>${feas.capacity}</strong> — but you asked for ` +
    `<strong>${k}</strong>.<br><br>` +
    `Try lowering "how many to pick," or raising "max from one time category." Nothing ` +
    `gets relaxed automatically — quietly ignoring a limit you set would be the worst way ` +
    `for a tool like this to fail.`;
  return d;
}

const photoCredit = () => {
  const p = el('p', 'hint credit');
  p.textContent = hasPhotos() ? 'Photographs: Food.com, for the exact recipe shown. No image is substituted.' : '';
  return p;
};

/* ---------------------------------------------------------------- the card
 *
 * One recipe, as an index card: a photograph if Food.com has one, the name, the minutes,
 * and the match score pencilled in the corner. Every recipe on either page is this card
 * at one of three sizes, which is what makes the two pages read as one deck.
 */
function recipeCard(c, { size = 'chip', rank = null } = {}) {
  const card = el('div', `card card-${size}`);
  card.style.setProperty('--bl', bandLine(c.b));
  card.style.setProperty('--bf', bandFill(c.b));
  card.title = `${c.name} — ${c.min} min, ${fmtPct(c.s)} match`;
  const ph = photo(c.id, 'card-ph');
  if (ph) card.appendChild(ph);
  // Not every recipe has a real Food.com photograph (some pages carry only the site's own
  // generic share graphic, which is not a photograph of the dish and is correctly rejected
  // by the fetcher). No substitute is used - the card holds the divider's colour instead,
  // at the same aspect ratio, so it sits evenly beside photographed cards without faking one.
  else {
    // Food.com itself has no photograph for 209 of the 470 recipes in this extract - mostly
    // pre-2010 uploads. Nothing is substituted for the dish: the card shows its own initial
    // on its divider's colour, which claims nothing about what the food looks like.
    const empty = el('div', 'card-ph card-ph-empty');
    empty.title = 'Food.com has no photograph for this recipe.';
    empty.appendChild(el('span', 'cpe-i', (c.name || '?').trim().charAt(0).toUpperCase()));
    empty.appendChild(el('span', 'cpe-b', bandPlain(c.b)));
    card.appendChild(empty);
  }
  const body = el('div', 'card-b');
  if (rank !== null) body.appendChild(el('span', 'card-rank', String(rank)));
  body.appendChild(el('div', 'card-n', c.name));
  const m = el('div', 'card-m');
  m.appendChild(el('span', 'card-min', `${c.min} min`));
  m.appendChild(el('span', 'card-band', bandPlain(c.b)));
  body.appendChild(m);
  card.appendChild(body);
  const score = el('span', 'card-score', fmtPct(c.s));
  score.title = 'match score';
  card.appendChild(score);
  return card;
}

/* The box's count alone, for the demo page: the one dark object on a paper page, and the
 * person's real number. */
function viewBoxCount(p) {
  const line = el('span');
  const n = el('b');
  line.appendChild(n);
  line.appendChild(document.createTextNode(` cards ${p.label} has not tried · every one scored · ${state.k} pulled`));
  countUp(n, p.n_eligible_candidates, fmtInt, { duration: 1200 });
  return line;
}

/* ---------------------------------------------------------------- reveals
 *
 * Once, on entry, in reading order. The rest state is the visible default, so a page
 * without JavaScript is complete; the animation only ever runs from an offset to it.
 */
function bindReveals() {
  const nodes = [...document.querySelectorAll('[data-reveal]')];
  if (!nodes.length || reduced() || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      const kids = e.target.hasAttribute('data-reveal-children')
        ? [...e.target.children] : [e.target];
      kids.forEach((k, i) => {
        k.setAttribute('data-anim', 'reveal');
        anim(k, [{ opacity: 0.25, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
          { duration: 520, delay: i * 70 });
      });
    });
  }, { rootMargin: '0px 0px -12% 0px', threshold: 0.05 });
  nodes.forEach((n) => io.observe(n));
}

/* ---------------------------------------------------------------- the band board */

function refusedInBand(p, picked, cap, b) {
  if (!picked || !picked.length) return null;
  if (bandUsage(picked, nBands())[b] < cap) return null;
  const chosen = new Set(picked.map((c) => c.id));
  const cut = Math.min(...picked.map((c) => c.s));
  return p.candidates
    .filter((c) => c.b === b && !chosen.has(c.id) && c.s >= cut)
    .sort((x, y) => (y.s - x.s) || (x.id - y.id))[0] || null;
}

function hasRefusal(p, k, cap) {
  const picked = solve(p.candidates, k, cap, 's');
  if (!picked) return false;
  for (let b = 0; b < nBands(); b++) if (refusedInBand(p, picked, cap, b)) return true;
  return false;
}

function capThatBites(p, k, current) {
  const hi = DATA.meta.b_range[1];
  for (let d = 1; d <= hi; d++) {
    for (const cap of [current - d, current + d]) {
      if (cap >= DATA.meta.b_range[0] && cap <= hi && hasRefusal(p, k, cap)) return cap;
    }
  }
  return null;
}

function buildBoard(p, picked, k, cap) {
  const nB = nBands();
  const board = el('div', 'board');
  const slots = Math.max(1, Math.min(cap, k));

  for (let b = 0; b < nB; b++) {
    const inBand = picked.filter((c) => c.b === b);
    const full = inBand.length >= cap;
    const row = el('div', 'brow' + (full ? ' is-full' : ''));
    row.style.setProperty('--bl', bandLine(b));
    row.style.setProperty('--bw', bandWash(b));

    const head = el('div', 'bhead');
    head.appendChild(icon(`band${b}`, { size: 22, tint: bandFill(b) }));
    const meta = el('div', 'bmeta');
    meta.appendChild(el('div', 'bname', bandPlain(b)));
    meta.appendChild(el('div', 'brange', bandRange(b)));
    head.appendChild(meta);
    row.appendChild(head);

    const strip = el('div', 'strip');
    inBand.forEach((c) => {
      // The outer .chip is moved by WAAPI (FLIP). The inner .card is what CSS lifts on
      // hover. Two elements, so the transform property never has two owners.
      const chip = el('div', 'chip');
      chip.dataset.flip = `c${c.id}`;
      chip.style.setProperty('--bl', bandLine(b));
      chip.style.setProperty('--bw', bandWash(b));
      chip.appendChild(recipeCard(c, { size: 'chip' }));
      strip.appendChild(chip);
    });
    for (let j = inBand.length; j < slots; j++) strip.appendChild(el('div', 'slot'));
    row.appendChild(strip);

    row.appendChild(el('div', 'bcount' + (full ? ' is-full' : ''), `${inBand.length} / ${cap}`));

    // The teaching moment: a recipe good enough to make the list, refused by the cap.
    // In the menu's language, it was 86'd.
    const blocked = refusedInBand(p, picked, cap, b);
    if (blocked) {
      const r = el('div', 'refused');
      r.appendChild(el('span', 'stamp', "86'd"));
      const t = el('div');
      t.innerHTML = `<b>${esc(blocked.name)}</b> scored ${fmtPct(blocked.s)} — enough to ` +
        `make the list — and was put back because this divider was already full.`;
      r.appendChild(t);
      row.appendChild(r);
    }
    board.appendChild(row);
  }
  return board;
}

/* ---------------------------------------------------------------- landscape */

function buildLandscape(p, picked) {
  const host = el('div');
  const tip = el('div', 'tip');
  tip.hidden = true;

  const chart = scoreLandscape({
    cands: p.candidates,
    chosenIds: picked.map((c) => c.id),
    bandFill, bandLine, bandName: bandPlain,
    onHover: (h) => {
      if (!h) { tip.hidden = true; return; }
      const status = h.isPicked ? 'Chosen'
        : h.refused ? 'Scored high enough — put back, its divider was full'
          : 'Not chosen';
      tip.innerHTML = '';
      const ph = photo(h.c.id, 'tip-ph');
      if (ph) tip.appendChild(ph);
      const t = el('div');
      t.innerHTML = `<b>${esc(h.c.name)}</b>` +
        `<span class="t-s">${h.c.min} min · ${esc(bandPlain(h.c.b))} · ` +
        `${fmtPct(h.c.s)} match</span><br>${status}`;
      tip.appendChild(t);
      tip.hidden = false;
      const svg = chart.querySelector('svg');
      const r = svg.getBoundingClientRect();
      const sx = r.width / 720, sy = r.height / 320;
      tip.style.left = `${Math.min(Math.max(h.x * sx - 100, 6), Math.max(6, r.width - 260))}px`;
      tip.style.top = `${Math.max(h.y * sy - 66, 4)}px`;
    },
  });
  chart.appendChild(tip);

  const lg = el('div', 'legend');
  const item = (cls, label, style) => {
    const sp = el('span', cls);
    const sw = el('i');
    if (style) Object.assign(sw.style, style);
    sp.appendChild(sw);
    sp.appendChild(document.createTextNode(label));
    return sp;
  };
  lg.appendChild(item('', 'chosen', { background: bandFill(1), borderColor: 'var(--accent)', borderWidth: '2px' }));
  lg.appendChild(item('lg-ref', 'scored high enough, refused by the cap', { borderColor: bandLine(2) }));
  lg.appendChild(item('lg-off', 'scored below the cut', { background: bandFill(0), borderColor: bandLine(0) }));
  lg.appendChild(el('span', null, 'colour = time category, light to dark'));
  host.appendChild(chart);
  host.appendChild(lg);
  return host;
}

/* ---------------------------------------------------------------- view: their picks */

function capNarrative(p) {
  const base = `Four dividers, at most ${state.cap} from behind any one of them. `;
  if (hasRefusal(p, state.k, state.cap)) {
    return `${base}The rule is biting right now — look for the 86'd line below, where a ` +
      'card that scored well enough was put back because its divider was full. That ' +
      'refusal is the whole idea.';
  }
  const better = capThatBites(p, state.k, state.cap);
  if (better !== null) {
    return `${base}Right now the rule is not changing anything: the best matches were ` +
      `already spread out. Set the limit to ${better} to watch it turn a good recipe away.`;
  }
  return `${base}For this person the rule never has to step in at any setting — their ` +
    'best matches are already spread across dividers. That happens, and it is worth ' +
    'saying rather than hiding. Try another person from the dropdown to see it bite.';
}

function slFunnel(p) {
  const host = el('div');
  host.appendChild(funnel([
    { value: DATA.meta.denominators.n_catalogue_recipes, label: 'recipes in the catalogue' },
    { value: p.n_eligible_candidates, label: 'they haven\'t already cooked',
      note: 'every one of these was scored against this person\'s taste' },
    { value: state.k, label: 'on their shortlist' },
  ]));
  const ratio = el('p', 'sec-sub');
  ratio.style.margin = '.5rem 0 0';
  ratio.innerHTML = `That is <strong>one recipe in ` +
    `${fmtInt(p.n_eligible_candidates / state.k)}</strong> making the ` +
    `list — which is why picking the right ${state.k} is worth doing carefully.`;
  host.appendChild(ratio);
  return host;
}

function slStats(p, picked) {
  const usage = bandUsage(picked, nBands());
  const avgMatch = totalScore(picked, 's') / picked.length;
  const row = el('div', 'stat-row');
  row.appendChild(stat('Recipes picked', String(picked.length), `out of ${state.k} requested`));
  row.appendChild(stat('Average match', fmtPct(avgMatch), 'how close to their taste'));
  row.appendChild(stat('Dividers used', `${usage.filter((n) => n > 0).length} of ${usage.length}`,
    'time categories represented'));
  row.appendChild(stat('Chosen from', fmtInt(p.n_eligible_candidates),
    'recipes this person hasn’t tried'));
  return row;
}

function pullCaption(p, picked, k, cap) {
  const cap_ = el('p', 'caption stage-cap');
  let blocked = null;
  for (let b = 0; b < nBands() && !blocked; b++) blocked = refusedInBand(p, picked, cap, b);
  if (blocked) {
    // The board's own row carries the name and the score; the sentence says what it means.
    cap_.textContent = 'The stamped card scored well enough to make the list. It was put back because its divider was already full — that refusal is the whole idea.';
    return cap_;
  }
  const better = capThatBites(p, k, cap);
  cap_.textContent = better !== null
    ? `The rule is not changing anything here: the best matches were already spread out. Set the limit to ${better} to watch it turn a good card away.`
    : 'For this person the rule never has to step in: their best matches are already spread across the dividers.';
  return cap_;
}

/* The board is the screen. Everything that explains it sits one layer down. */
function viewShortlist(p, opts = {}) {
  const out = el('div');
  const sink = opts.working || out;
  const k = opts.k ?? state.k, cap = opts.cap ?? state.cap;
  const feas = feasibility(p.candidates, k, cap, nBands());
  if (!feas.feasible) { out.appendChild(infeasibleNotice(feas, k, cap)); return out; }
  const picked = solve(p.candidates, k, cap, 's');

  const boardHost = el('div');
  boardHost.id = 'sl-board';
  boardHost.appendChild(buildBoard(p, picked, k, cap));
  out.appendChild(boardHost);
  const capHost = el('div');
  capHost.id = 'sl-cap-note';
  capHost.appendChild(pullCaption(p, picked, k, cap));
  out.appendChild(capHost);

  const s2 = section('Why those, and what it turned down',
    'One dot per card. Up is a better match; right is a longer cook. Hollow dots above the line were put back.', 'scale');
  const landHost = el('div');
  landHost.id = 'sl-land';
  landHost.appendChild(buildLandscape(p, picked));
  s2.appendChild(landHost);
  // On the box the landscape sits under the board in view; on the story it is the working.
  if (opts.landscapeInline) { s2.style.marginTop = '3rem'; out.appendChild(s2); } else sink.appendChild(s2);

  const note = el('div', 'banner banner-info');
  note.style.marginInline = 'auto';
  note.innerHTML = `<strong>What "match" means.</strong> How similar a recipe's ingredients ` +
    `and description are to the recipes this person already rated highly — not a ` +
    `prediction that they'll enjoy it, and not a rating.`;
  sink.appendChild(note);

  const statsHost = el('div');
  statsHost.id = 'sl-stats';
  statsHost.appendChild(slStats(p, picked));
  sink.appendChild(statsHost);

  const s3 = section('The size of the problem',
    'What the optimiser chooses between every time you move a slider. Almost nothing is filtered out first.', 'rising');
  const fnHost = el('div');
  fnHost.id = 'sl-funnel';
  fnHost.appendChild(slFunnel(p));
  s3.appendChild(fnHost);
  sink.appendChild(s3);
  sink.appendChild(photoCredit());
  return out;
}

function updateShortlist(p, host, working) {
  const boardHost = host.querySelector('#sl-board');
  const feas = feasibility(p.candidates, state.k, state.cap, nBands());
  if (!boardHost || !feas.feasible) {
    host.innerHTML = '';
    if (working) working.innerHTML = '';
    host.appendChild(viewShortlist(p, { working, landscapeInline: !!working }));
    return;
  }
  const picked = solve(p.candidates, state.k, state.cap, 's');
  flip(boardHost, () => {
    boardHost.innerHTML = '';
    boardHost.appendChild(buildBoard(p, picked, state.k, state.cap));
  });
  const capHost = host.querySelector('#sl-cap-note');
  if (capHost) { capHost.innerHTML = ''; capHost.appendChild(pullCaption(p, picked, state.k, state.cap)); }
  const root = working || host;
  const statsHost = root.querySelector('#sl-stats');
  if (statsHost) { statsHost.innerHTML = ''; statsHost.appendChild(slStats(p, picked)); }
  const landHost = root.querySelector('#sl-land');
  if (landHost) { landHost.innerHTML = ''; landHost.appendChild(buildLandscape(p, picked)); }
  const fnHost = root.querySelector('#sl-funnel');
  if (fnHost) { fnHost.innerHTML = ''; fnHost.appendChild(slFunnel(p)); }
}

/* ---------------------------------------------------------------- try it yourself */

const TRY_MENU_SIZE = 60;

/* The three rounds, described once. `key` is what a round is called in the recorded row;
 * `order` below is the sequence this visitor actually saw. The intro copy promises a
 * fixed shape - the long list once, then two short lists - so `menu` always goes first;
 * only the two six-item rounds are shuffled per visitor, so the warm-up advantage does
 * not always land on the same one of those two. */
const TRY_ROUNDS = {
  menu: {
    title: 'Pick something you would actually cook.',
    sub: `${TRY_MENU_SIZE} real recipes from this person's list. Take as long as you like.`,
    label: `The whole menu (${TRY_MENU_SIZE})`,
  },
  random: {
    title: 'Now pick from these six.',
    sub: 'Six recipes chosen completely at random. No taste matching, no variety rule.',
    label: 'Six at random',
  },
  ours: {
    title: 'Now pick from these six.',
    sub: "Six chosen by our method - matched to this person's taste and spread across cooking times.",
    label: 'Our six',
  },
};

const shuffled = (arr, seed) => {
  // Deterministic per visitor, so a reload does not silently reshuffle mid-run.
  // Math.imul keeps the multiply inside true 32-bit integer arithmetic - plain `*`
  // overflows Number.MAX_SAFE_INTEGER here and silently rounds to an even result,
  // which made every draw swap the same way regardless of seed (found during QA).
  const a = [...arr];
  let r = seed;
  for (let i = a.length - 1; i > 0; i--) {
    r = (Math.imul(r, 1103515245) + 12345) & 0x7fffffff;
    const j = r % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

function newTryState() {
  const seed = Math.floor(Math.random() * 0x7fffffff);
  return {
    stage: -1,
    seed,
    order: ['menu', ...shuffled(['random', 'ours'], seed)],
    times: {},
    picks: {},
    t0: null,
    session: (Math.random().toString(36).slice(2, 10) + Date.now().toString(36)).slice(0, 14),
    started: new Date().toISOString(),
    sent: false,
  };
}

let tryState = newTryState();
const tryReset = () => { tryState = newTryState(); };

/* Anonymous run record. Netlify Forms: a same-origin POST, no database, no third party,
 * exported as CSV from the Netlify dashboard. Times, picks and screen width only - no
 * name, no login, no identifier that outlives the tab. */
function sendTryRun() {
  if (tryState.sent) return;
  tryState.sent = true;
  const body = new URLSearchParams({
    'form-name': 'try-run',
    session: tryState.session,
    profile: DATA.profiles[state.profile].label,
    order: tryState.order.join(','),
    t_menu: Math.round(tryState.times.menu || 0),
    t_random: Math.round(tryState.times.random || 0),
    t_ours: Math.round(tryState.times.ours || 0),
    pick_menu: String(tryState.picks.menu ?? ''),
    pick_random: String(tryState.picks.random ?? ''),
    pick_ours: String(tryState.picks.ours ?? ''),
    screen: `${window.innerWidth}x${window.innerHeight}`,
    started_utc: tryState.started,
    menu_size: String(TRY_MENU_SIZE),
  });
  fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body })
    .catch(() => { /* a failed record must never break the demonstration */ });
}

function tryOptions(p, key) {
  if (key === 'menu') return shuffled(p.candidates, tryState.seed).slice(0, TRY_MENU_SIZE);
  // Seeded from tryState.seed (fresh every run, via newTryState()) rather than the
  // profile alone, so the "completely at random" six actually varies from one attempt
  // to the next instead of freezing on the same six for a given profile forever. The
  // '+ 1' just decorrelates it from the menu shuffle, which uses the same seed value.
  if (key === 'random') return randomPick(p.candidates, 6, 6, tryState.seed + 1) || p.candidates.slice(0, 6);
  return solve(p.candidates, 6, DATA.meta.b_default, 's') || p.candidates.slice(0, 6);
}

function tryMenu(p, key) {
  const opts = tryOptions(p, key);
  const grid = el('div', 'menu-grid' + (key !== 'menu' ? ' is-short' : ''));
  opts.forEach((c) => {
    const b = el('button', 'mi');
    b.type = 'button';
    b.appendChild(recipeCard(c, { size: key === 'menu' ? 'menu' : 'menu-lg' }));
    b.addEventListener('click', () => {
      tryState.times[key] = performance.now() - tryState.t0;
      tryState.picks[key] = c.id;
      tryState.stage += 1;
      tryState.t0 = performance.now();
      if (tryState.stage >= tryState.order.length) sendTryRun();
      renderTry();
      window.scrollTo({ top: 0, behavior: reduced() ? 'auto' : 'smooth' });
    });
    grid.appendChild(b);
  });
  return grid;
}

/* Three dots, so a phone always shows how much is left. */
function tryProgress(stage) {
  const wrap = el('div', 'try-dots');
  tryState.order.forEach((_, i) => {
    const d = el('i', i < stage ? 'is-done' : i === stage ? 'is-now' : '');
    wrap.appendChild(d);
  });
  return wrap;
}

const secs = (ms) => (Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)}s` : '—');

/* The sixty-then-six visual: a loose pile of small photos narrowing, through an arrow,
 * into three tilted cards - the same card treatment as the homepage hero, so the two
 * pages read as one material. Built from the four CC BY band photos (credited below the
 * page); nothing generated. Real numbers from the round the visitor is about to run. */
const TRY_MANY = ['band-quick', 'band-moderate', 'band-fast', 'band-long', 'band-moderate', 'band-long', 'band-quick', 'band-fast'];
const TRY_FEW = ['band-quick', 'band-moderate', 'band-long'];

function tryFanNew() {
  const wrap = el('div', 'try-fan-new');
  const many = el('div', 'tfn-many');
  TRY_MANY.forEach((id) => {
    const img = el('img', 'tfn-chip');
    img.src = `/img/stock/${id}.jpg`;
    img.alt = ''; img.loading = 'eager'; img.width = 480; img.height = 360;
    many.appendChild(img);
  });
  many.appendChild(el('span', 'tfn-tag', String(TRY_MENU_SIZE)));
  wrap.appendChild(many);

  const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  arrow.setAttribute('class', 'tfn-arrow');
  arrow.setAttribute('viewBox', '0 0 32 18');
  arrow.setAttribute('aria-hidden', 'true');
  arrow.innerHTML = '<path d="M1 9h27M21 2l8 7-8 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>';
  wrap.appendChild(arrow);

  const few = el('div', 'tfn-few');
  TRY_FEW.forEach((id) => {
    const img = el('img', 'hc');
    img.src = `/img/stock/${id}.jpg`;
    img.alt = ''; img.loading = 'eager'; img.width = 480; img.height = 360;
    few.appendChild(img);
  });
  few.appendChild(el('span', 'tfn-tag tfn-tag-few', '6'));
  wrap.appendChild(few);
  return wrap;
}

function tryIntro() {
  const out = el('div', 'try-intro');
  out.appendChild(tryFanNew());
  out.appendChild(el('p', 'try-kicker', 'A one-minute demonstration'));
  out.appendChild(el('h1', 'try-h', 'Sixty recipes, then six.'));
  const lead = el('p', 'try-lead');
  lead.textContent = 'You will pick a recipe three times: once from a long list, and twice '
    + 'from a short one. We time each pick and show you your own three numbers at the end.';
  out.appendChild(lead);

  const steps = el('ol', 'try-steps');
  [
    'Pick a recipe you would actually cook. There is no right answer.',
    'Do it twice more from six-recipe lists.',
    'See your three times, and why one person’s times are not evidence.',
  ].forEach((t) => steps.appendChild(el('li', null, t)));
  out.appendChild(steps);

  const row = el('div', 'btn-row');
  const go = el('button', 'btn big', 'Start');
  go.type = 'button';
  go.addEventListener('click', () => { tryState.stage = 0; tryState.t0 = performance.now(); renderTry(); });
  row.appendChild(go);
  out.appendChild(row);

  const notice = el('p', 'try-notice');
  notice.textContent = 'Your three times and which recipe you picked are recorded anonymously '
    + 'for this class demonstration. No name, no login, nothing that identifies you.';
  out.appendChild(notice);
  return out;
}

function tryDebrief() {
  const out = el('div');
  out.appendChild(el('p', 'try-kicker', 'Your result'));
  out.appendChild(el('h1', 'try-h', 'Your three times.'));

  const t = tryState.times;
  const max = Math.max(t.menu || 0, t.random || 0, t.ours || 0) || 1;
  const box = el('div', 'times');
  ['menu', 'random', 'ours'].forEach((key, i) => {
    const row = el('div', `trow${key === 'menu' ? ' is-menu' : ''}`);
    row.appendChild(el('span', null, TRY_ROUNDS[key].label));
    const track = el('div', 'tt');
    const fill = el('div', 'tf');
    fill.style.width = `${Math.max(2, ((t[key] || 0) / max) * 100)}%`;
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el('span', 'tv', secs(t[key])));
    box.appendChild(row);
    growBar(fill, { delay: 90 + i * 90 });
  });
  out.appendChild(box);

  const shorter = Number.isFinite(t.menu) && Number.isFinite(t.ours) && t.ours < t.menu;
  const verdict = el('div', 'banner banner-info');
  verdict.innerHTML = shorter
    ? `<strong>Picking from six was faster for you than picking from ${TRY_MENU_SIZE}.</strong> `
      + 'That feeling is the hunch this project starts from. On its own it proves nothing - here is why.'
    : '<strong>The short list was not faster for you.</strong> That happens, and it is worth '
      + 'seeing. One person on one try tells you almost nothing either way.';
  out.appendChild(verdict);

  const why = el('div', 'banner banner-warn');
  why.innerHTML =
    '<strong>Why this is a demonstration and not a result.</strong> Three reasons, each fatal on its own:'
    + '<br><br><strong>1.</strong> One person. You. A real study needs many, chosen properly.<br>'
    + '<strong>2.</strong> You knew what was being tested, which changes how people behave.<br>'
    + '<strong>3.</strong> Choosing fast is not the same as choosing well, and nothing here measures '
    + 'whether you would have enjoyed the meal.'
    + '<br><br>Your round order was shuffled, which removes one flaw a fixed order would add. '
    + 'It does not make one person a study.';
  out.appendChild(why);

  const say = el('p', 'try-lead');
  say.style.marginTop = '1.6rem';
  say.innerHTML = 'What the real study measures instead: whether a six-recipe shortlist actually '
    + 'contains recipes people later rated highly. It was tested on <strong>812 real people</strong> in validation and <strong>530</strong> in the final run, '
    + 'and the honest answer is on the story page.';
  out.appendChild(say);

  const row = el('div', 'btn-row');
  const a = el('a', 'btn', 'See what the study found');
  a.href = '/#result';
  row.appendChild(a);
  const b = el('a', 'btn ghost', 'Open the box');
  b.href = '/demo/';
  row.appendChild(b);
  const again = el('button', 'btn ghost', 'Run it again');
  again.type = 'button';
  again.addEventListener('click', () => { tryReset(); renderTry(); window.scrollTo({ top: 0 }); });
  row.appendChild(again);
  out.appendChild(row);
  return out;
}

function viewTry(p) {
  if (tryState.stage === -1) return tryIntro();
  if (tryState.stage >= tryState.order.length) return tryDebrief();
  const round = tryState.stage;
  const key = tryState.order[round];
  const meta = TRY_ROUNDS[key];
  const out = el('div');
  const head = el('div', 'try-head');
  head.appendChild(el('span', 'try-step', `Round ${round + 1} of ${tryState.order.length}`));
  head.appendChild(el('span', 'try-clock', 'timing you now'));
  out.appendChild(head);
  out.appendChild(tryProgress(round));
  out.appendChild(el('h1', 'try-h', meta.title));
  out.appendChild(el('p', 'try-lead', meta.sub));
  out.appendChild(tryMenu(p, key));
  if (key === 'menu') out.appendChild(photoCredit());
  const skip = el('div', 'btn-row');
  const sBtn = el('button', 'btn ghost', 'Start over');
  sBtn.type = 'button';
  sBtn.addEventListener('click', () => { tryReset(); renderTry(); });
  skip.appendChild(sBtn);
  out.appendChild(skip);
  return out;
}

/* "Try it yourself" lives either in its own host (#try) or as a tab of the demo. */
function renderTry() {
  const host = $('#try');
  if (host) { host.innerHTML = ''; host.appendChild(viewTry(DATA.profiles[state.profile])); return; }
  if (sheetState.open === 'try') renderSheet();
}

/* ---------------------------------------------------------------- compare */

const METHOD_BLURB = {
  AI_LP: 'Their taste, kept spread across the dividers.',
  AI_TOPK: 'Their taste, no variety rule — so it can pick six near-identical recipes.',
  POPULARITY_LP: 'Ignores this person. Picks what is popular with everyone.',
  RANDOM: 'Random recipes, still obeying the variety rule. The floor.',
};

function methodColumn(m, shared, nB) {
  const col = el('div', 'mcol' + (m.name === 'AI_LP' ? ' is-ours' : ''));
  const h = el('div', 'mcol-h');
  h.appendChild(icon(METHOD_ICON[m.name] || 'info', { size: 18 }));
  h.appendChild(el('h4', null, methodPlain(m.name)));
  col.appendChild(h);
  col.appendChild(el('p', 'desc', METHOD_BLURB[m.name] || ''));
  if (!m.list) { col.appendChild(el('p', 'desc', 'Couldn\'t fit a valid list here.')); return col; }

  const u = bandUsage(m.list, nB);
  const strip = el('div', 'usage');
  strip.title = u.map((n, i) => `${bandPlain(i)}: ${n}`).join(', ');
  u.forEach((n, i) => { for (let j = 0; j < n; j++) { const c = el('i'); c.style.background = bandFill(i); strip.appendChild(c); } });
  col.appendChild(strip);

  const chips = el('div', 'mchips');
  m.list.forEach((c) => {
    const chip = el('div', 'mchip' + (shared.has(c.id) ? ' is-shared' : ''));
    chip.style.setProperty('--bl', bandLine(c.b));
    chip.title = `${c.name} — ${c.min} min, ${bandPlain(c.b)}`;
    const ph = photo(c.id, 'mchip-ph');
    if (ph) chip.appendChild(ph);
    chip.append(el('div', 'mchip-d', c.name), el('div', 'mchip-t', `${c.min}m`));
    chips.appendChild(chip);
  });
  col.appendChild(chips);

  const max = Math.max(...u);
  const foot = el('div', 'mfoot');
  const avg = el('span');
  avg.innerHTML = `avg match <b>${fmtPct(totalScore(m.list, 's') / m.list.length)}</b>`;
  const rule = el('span');
  rule.innerHTML = max <= state.cap
    ? `<b>${u.filter((n) => n > 0).length}</b> of ${nB} dividers`
    : `<span class="bad">breaks the rule: ${max} from one</span>`;
  foot.append(avg, rule);
  col.appendChild(foot);
  return col;
}

function viewCompare(p) {
  const out = el('div');
  const nB = nBands();
  const feas = feasibility(p.candidates, state.k, state.cap, nB);
  if (!feas.feasible) { out.appendChild(infeasibleNotice(feas, state.k, state.cap)); return out; }

  out.appendChild(el('p', 'headline',
    'Same person, same recipes to choose from — four different ways of picking. ' +
    'Only "Our method" combines personal taste with a rule that keeps the list varied.'));
  // The strip's key, as swatches: the sentence that used to say "coloured by divider" is now the thing itself.
  const legend = el('div', 'legend');
  legend.style.margin = '0 0 .9rem';
  const key = (label, fill, line) => {
    const sp = el('span');
    const sw = el('i');
    sw.style.background = fill;
    sw.style.borderColor = line;
    sp.appendChild(sw);
    sp.appendChild(document.createTextNode(label));
    legend.appendChild(sp);
  };
  BAND_SHORT.forEach((name, i) => key(name, bandFill(i), bandLine(i)));
  key('picked by more than one', 'var(--accent-wash)', 'var(--accent)');
  out.appendChild(legend);

  const methods = [
    { name: 'AI_LP', list: solve(p.candidates, state.k, state.cap, 's') },
    { name: 'AI_TOPK', list: topk(p.candidates, state.k, 's') },
    { name: 'POPULARITY_LP', list: solve(p.candidates, state.k, state.cap, 'p') },
    { name: 'RANDOM', list: randomPick(p.candidates, state.k, state.cap, 42 + state.profile) },
  ];
  const counts = new Map();
  methods.forEach((m) => (m.list || []).forEach((c) => counts.set(c.id, (counts.get(c.id) || 0) + 1)));
  const shared = new Set([...counts.entries()].filter(([, n]) => n > 1).map(([id]) => id));

  const grid = el('div', 'mstack');
  methods.forEach((m) => grid.appendChild(methodColumn(m, shared, nB)));
  out.appendChild(grid);

  const ids = (m) => (m.list || []).map((c) => c.id).sort().join(',');
  if (ids(methods[0]) && ids(methods[0]) === ids(methods[1])) {
    const note = el('div', 'banner banner-info');
    note.innerHTML = '<strong>These two are identical right now, and that is the point.</strong> ' +
      'With this person and these settings the variety rule never has to step in — the six ' +
      'best-matching recipes were already spread across enough dividers. Drag "max behind one ' +
      'divider" down to 1 or 2 and the two lists come apart.';
    out.appendChild(note);
  }
  if (shared.size) {
    const sh = el('p', 'hint');
    sh.style.marginTop = '.8rem';
    sh.textContent = `${shared.size} recipe${shared.size === 1 ? ' was' : 's were'} picked by more than one approach.`;
    out.appendChild(sh);
  }
  const note = el('div', 'banner banner-info');
  note.innerHTML = '"No variety rule" is allowed to repeat one divider as much as it likes, so its ' +
    'average match score will always be at least as high as "Our method" — that\'s expected, ' +
    'not a win. The real question is which one actually recommends recipes people go on to ' +
    'enjoy, and that\'s answered in <strong>The result</strong> above.';
  out.appendChild(note);
  const caveat = el('div', 'banner banner-warn');
  caveat.innerHTML = '<strong>About "Random pick" here.</strong> This page draws once from a small ' +
    'sample of recipes, just to illustrate the idea. The real test ran random selection 20 ' +
    'times per person over the entire recipe catalogue and averaged the results.';
  out.appendChild(caveat);
  return out;
}

/* ---------------------------------------------------------------- the method: LPP, live */

function viewLpp(p, opts = {}) {
  const out = el('div');
  const sink = opts.working || out;
  const feas = feasibility(p.candidates, state.k, state.cap, nBands());
  const model = el('pre', 'lp');
  model.innerHTML =
    `maximise    Σ s<span class="c">ui</span> · x<span class="c">i</span>` +
    `${' '.repeat(16)}<span class="c">total match of the six</span>\n\n` +
    `subject to  Σ x<span class="c">i</span> = ${state.k}` +
    `${' '.repeat(Math.max(1, 20 - String(state.k).length))}<span class="c">exactly ${state.k}</span>\n` +
    `            Σ<span class="c">i∈G</span> x<span class="c">i</span> ≤ ${state.cap}` +
    `${' '.repeat(Math.max(1, 18 - String(state.cap).length))}<span class="c">at most ${state.cap} per divider</span>\n` +
    `            0 ≤ x<span class="c">i</span> ≤ 1${' '.repeat(16)}<span class="c">continuous, not binary</span>`;
  out.appendChild(model);
  const f = el('p', 'sec-sub');
  f.style.margin = '.9rem 0 0';
  f.innerHTML = `Feasible? <code>Σ min(cap, |G|)</code> = <strong>${feas.capacity}</strong>, needs ≥ ` +
    `<strong>${state.k}</strong> → <strong>${feas.feasible ? 'yes' : 'NO — infeasible'}</strong>. ` +
    `Cards behind each divider in this extract: ${feas.sizes.join(', ')}.`;
  sink.appendChild(f);
  return out;
}

/* ---------------------------------------------------------------- the method: the slice
 *
 * Hold every pick but the weakest fixed. Let that pick (A) and the best recipe that could
 * take its place (B) compete for the one open slot. x_A + x_B = 1: the feasible region is
 * a line, the objective is linear, and the best point is one of its two ends. Drag the
 * point along the line and watch splitting the slot lose to either whole recipe.
 */
function sliceData(p) {
  const picked = solve(p.candidates, state.k, state.cap, 's');
  if (!picked) return null;
  const usage = bandUsage(picked, nBands());
  const A = picked[picked.length - 1];
  const chosen = new Set(picked.map((c) => c.id));
  const room = (b) => usage[b] - (b === A.b ? 1 : 0) < state.cap;
  const B = p.candidates.filter((c) => !chosen.has(c.id) && room(c.b))
    .sort((x, y) => (y.s - x.s) || (x.id - y.id))[0];
  if (!B) return null;
  return { A, B, base: totalScore(picked, 's') - A.s };
}

function viewSlice(p) {
  const out = el('div');
  const d = sliceData(p);
  if (!d) { out.appendChild(el('p', 'hint', 'No valid shortlist at these settings, so there is no slice to draw.')); return out; }
  const { A, B, base } = d;

  const wrap = el('div', 'slice');
  const W = 380, L = 56, S = 268; // left/top edge and side of the unit square
  const P = (t) => [L + S * t, L + S * t]; // t = x_A; (1,0) bottom-right, (0,1) top-left
  const svg = s('svg', { viewBox: `0 0 ${W} ${W}`, class: 'slice-svg', role: 'img',
    'aria-label': `Two recipes competing for one slot. Recipe A scores ${A.s.toFixed(4)}, recipe B ${B.s.toFixed(4)}. The best answer is a whole recipe, not a split.` });
  svg.appendChild(s('rect', { x: L, y: L, width: S, height: S, class: 'sq' }));
  svg.appendChild(s('line', { x1: L, y1: L + S, x2: L + S + 14, y2: L + S, class: 'ax' }));
  svg.appendChild(s('line', { x1: L, y1: L + S, x2: L, y2: L - 14, class: 'ax' }));
  svg.appendChild(stext(L + S + 4, L + S + 22, 'x_A', { class: 'ax-t' }));
  svg.appendChild(stext(L - 30, L - 4, 'x_B', { class: 'ax-t' }));
  const seg = s('line', { x1: P(1)[0], y1: P(1)[1], x2: P(0)[0], y2: P(0)[1], class: 'seg' });
  svg.appendChild(seg);
  svg.appendChild(stext(L + S / 2 + 10, L + S / 2 - 12, 'x_A + x_B = 1', { class: 'seg-t', transform: `rotate(45 ${L + S / 2 + 10} ${L + S / 2 - 12})` }));
  const endA = s('circle', { cx: P(1)[0], cy: P(1)[1], r: 8, class: 'end end-a' });
  const endB = s('circle', { cx: P(0)[0], cy: P(0)[1], r: 8, class: 'end end-b' });
  svg.append(endA, endB);
  svg.appendChild(stext(P(1)[0] - 4, P(1)[1] + 26, '(1, 0)  take A', { class: 'ax-t', 'text-anchor': 'end' }));
  svg.appendChild(stext(P(0)[0] + 14, P(0)[1] - 12, '(0, 1)  take B', { class: 'ax-t' }));
  const dot = s('circle', { cx: P(1)[0], cy: P(1)[1], r: 11, class: 'dot' });
  svg.appendChild(dot);
  wrap.appendChild(svg);

  const read = el('div', 'slice-read');
  const line = (lab) => { const r = el('div', 'sr'); r.appendChild(el('span', 'sr-l', lab)); const v = el('span', 'sr-v'); r.appendChild(v); read.appendChild(r); return v; };
  const vXA = line('x_A'), vXB = line('x_B');
  const vObj = line('slice objective'); const vTot = line('whole shortlist');
  const verdict = el('p', 'slice-verdict');
  read.appendChild(verdict);
  wrap.appendChild(read);
  out.appendChild(wrap);

  const names = el('div', 'slice-names');
  names.innerHTML = `<div><span class="tag tag-a">A</span> <b>${esc(A.name)}</b> · ${A.min} min · score <b>${A.s.toFixed(4)}</b></div>` +
    `<div><span class="tag tag-b">B</span> <b>${esc(B.name)}</b> · ${B.min} min · score <b>${B.s.toFixed(4)}</b></div>`;
  out.appendChild(names);

  const set = (t) => {
    t = Math.max(0, Math.min(1, t));
    const [x, y] = P(t);
    dot.setAttribute('cx', x); dot.setAttribute('cy', y);
    const obj = A.s * t + B.s * (1 - t);
    vXA.textContent = t.toFixed(2); vXB.textContent = (1 - t).toFixed(2);
    vObj.textContent = obj.toFixed(4); vTot.textContent = (base + obj).toFixed(4);
    const best = Math.max(A.s, B.s);
    endA.classList.toggle('is-best', A.s >= B.s); endB.classList.toggle('is-best', B.s > A.s);
    if (t === 1 || t === 0) {
      verdict.textContent = (t === 1 ? A.s : B.s) >= best
        ? 'A corner. This is the optimum — a whole recipe.'
        : 'The other corner scores higher.';
    } else {
      verdict.textContent = `A split scores ${obj.toFixed(4)} — less than the better corner (${best.toFixed(4)}). Splitting never pays.`;
    }
  };
  set(1);

  // Drag along the segment: project the pointer onto the diagonal in viewBox units.
  const toT = (evt) => {
    const r = svg.getBoundingClientRect();
    const px = (evt.clientX - r.left) * (W / r.width);
    const py = (evt.clientY - r.top) * (W / r.height);
    return ((px - L) + (py - L)) / (2 * S);
  };
  let dragging = false;
  svg.addEventListener('pointerdown', (e) => { dragging = true; svg.setPointerCapture(e.pointerId); set(toT(e)); });
  svg.addEventListener('pointermove', (e) => { if (dragging) set(toT(e)); });
  svg.addEventListener('pointerup', () => { dragging = false; });
  svg.addEventListener('pointercancel', () => { dragging = false; });
  return out;
}

/* ---------------------------------------------------------------- the method: duality */

function betaBars(p) {
  const box = el('div', 'beta');
  const sv = p.solve, d = p.dual;
  const max = Math.max(...d.beta.map((v) => Math.abs(v)), 1e-9);
  DATA.meta.band_labels.forEach((lab, i) => {
    const used = sv.band_usage[lab] || 0;
    const binding = used === sv.cap;
    const row = el('div', 'brow-b');
    row.appendChild(el('span', null, `${bandPlain(i)} (${lab})`));
    const track = el('div', 'bt');
    const fill = el('div', 'bf');
    fill.style.width = `${Math.max(1.5, (Math.abs(d.beta[i]) / max) * 100)}%`;
    fill.style.background = binding ? bandLine(i) : 'var(--line)';
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el('span', 'bv', fmt(d.beta[i], 4)));
    row.appendChild(el('span', 'bs' + (binding ? ' on' : ''), binding ? 'cap binds' : 'slack'));
    box.appendChild(row);
    growBar(fill, { delay: 120 + i * 80 });
  });
  return box;
}

function certLine(p) {
  const d = p.dual;
  const line = el('div', 'certline');
  const part = (lab, val, cls) => {
    const w = el('span', cls || '');
    w.appendChild(el('span', 'cl-l', lab));
    w.appendChild(document.createTextNode(val));
    line.appendChild(w);
  };
  // Never animated: these numbers are a proof, and a proof that reads wrong for a second is wrong.
  part('primal, maximise', d.primal_objective.toFixed(6));
  line.appendChild(el('span', 'cl-eq', '='));
  part('dual, minimise', d.dual_objective.toFixed(6));
  line.appendChild(el('span', 'cl-eq', '·'));
  part('gap', d.duality_gap.toExponential(1), 'cl-gap');
  return line;
}

function viewDual(p, opts = {}) {
  const out = el('div');
  const sink = opts.working || out;
  const sv = p.solve, d = p.dual;
  out.appendChild(certLine(p));
  const ok = el('p', 'cert-ok');
  ok.innerHTML = d.strong_duality_holds
    ? `${icon('check', { size: 16 }).outerHTML} Strong duality holds within ${sv.tolerance}. Complementary slackness holds. <strong>The shortlist is certified optimal.</strong>`
    : 'CHECK FAILED';
  out.appendChild(ok);

  const pre = el('pre', 'lp');
  pre.innerHTML =
    `minimise    ${sv.k}·α  +  Σ<span class="c">g</span> ${sv.cap}·β<span class="c">g</span>  +  Σ<span class="c">i</span> γ<span class="c">i</span>\n\n` +
    `subject to  α + β<span class="c">g(i)</span> + γ<span class="c">i</span>  ≥  s<span class="c">ui</span>${' '.repeat(6)}<span class="c">for every candidate i</span>\n` +
    `            β<span class="c">g</span> ≥ 0,   γ<span class="c">i</span> ≥ 0,   α free`;
  sink.appendChild(pre);
  const note = el('p', 'sec-sub');
  note.style.margin = '1.2rem auto .4rem';
  note.innerHTML = `These numbers come from <code>scipy.optimize.linprog</code> on the full, unpruned candidate set at the protocol defaults (k = ${sv.k}, cap = ${sv.cap}). They do not move with the sliders.`;
  sink.appendChild(note);
  const bh = el('h4', 'sub-h', 'Shadow value of each cap');
  bh.style.textAlign = 'center';
  sink.appendChild(bh);
  const bp = el('p', 'sec-sub');
  bp.style.marginInline = 'auto';
  bp.textContent = 'How much match score one more slot behind that divider would buy. A cap that is not full has nothing to give, so its shadow value is zero. α, the value of one more slot overall, is ' + fmt(d.alpha, 4) + '.';
  sink.appendChild(bp);
  sink.appendChild(betaBars(p));
  if (d.beta.every((v) => Math.abs(v) < 1e-9)) {
    const z = el('p', 'hint');
    z.style.margin = '.6rem auto 0';
    z.textContent = 'Every shadow value is zero: for this person, at the defaults, no cap is binding — the variety rule is costing this shortlist nothing. Profile-0007 shows a binding cap.';
    sink.appendChild(z);
  }
  return out;
}

/* ---------------------------------------------------------------- the method: receipt */

function viewReceipt(p) {
  const out = el('div');
  const picked = solve(p.candidates, state.k, state.cap, 's');
  if (!picked) { out.appendChild(el('p', 'hint', 'No valid shortlist at these settings.')); return out; }
  const bill = el('div', 'bill');
  picked.forEach((c, i) => {
    const r = el('div', 'bill-r');
    r.appendChild(el('span', 'bill-n', `${i + 1}.  ${c.name}`));
    r.appendChild(el('span', 'bill-d'));
    r.appendChild(el('span', 'bill-v', c.s.toFixed(4)));
    bill.appendChild(r);
  });
  const tot = el('div', 'bill-r bill-t');
  tot.appendChild(el('span', 'bill-n', 'Objective  (total match score)'));
  tot.appendChild(el('span', 'bill-d'));
  const v = el('span', 'bill-v', totalScore(picked, 's').toFixed(6));
  tot.appendChild(v);
  bill.appendChild(tot);
  out.appendChild(bill);
  const atDefaults = state.k === p.solve.k && state.cap === p.solve.cap;
  const n = el('p', 'hint');
  n.textContent = atDefaults
    ? `The solver reports ${fmt(p.solve.objective, 6)} for this person at these settings. Same six, same total.`
    : 'Re-solved live at the current slider settings. The certified solve above is at the defaults.';
  out.appendChild(n);
  return out;
}

/* ---------------------------------------------------------------- the method as one tab
 *
 * The demo page carries the three lenses under a single tab so a reader never leaves
 * the page; the story page mounts the same pieces one course at a time.
 */
function viewSolved(p) {
  const out = el('div');
  const piece = (num, title, sub, build) => {
    const s1 = section(title, sub, null);
    s1.querySelector('.sec-h').prepend(el('span', 'lens-n', num));
    s1.appendChild(build(p));
    out.appendChild(s1);
  };
  piece('Lens one', 'The linear programme',
    'Maximise the total match of the picks. Exactly this many. At most this many per divider. Every number is the sliders\' number.', viewLpp);
  piece('Lens two', 'The graphical method',
    'Hold every pick but the weakest fixed, and let two recipes compete for the last slot. Drag the point: every split scores below the better corner.', viewSlice);
  piece('Lens three', 'Duality: the receipt that proves it',
    'A second programme that runs the other way. When its value meets the first one, the gap is zero and the shortlist is certified optimal.', viewDual);
  piece('The bill', 'The current shortlist, itemised',
    'The picks, added up. The total is the objective the programme maximised.', viewReceipt);
  piece('Raw variables', 'Every x, and the guarantee behind it',
    'The chosen cards with their score and their x. Every x is a whole 1 or 0, with nothing forcing it to be.', viewOR);
  return out;
}

/* ---------------------------------------------------------------- demo teaser (story page)
 *
 * A menu card of the six at the protocol defaults, with a pointer to the demo page. It
 * is a preview, not the demo: no sliders here, nothing to operate.
 */
function viewTeaser(p) {
  const out = el('div');
  const picked = solve(p.candidates, DATA.meta.k_default, DATA.meta.b_default, 's');
  if (!picked) { out.appendChild(el('p', 'hint', 'No valid shortlist at the defaults for this person.')); return out; }
  const card = el('div', 'menu-card');
  const h = el('div', 'mc-h');
  h.appendChild(el('span', 'mc-t', `Tonight, for ${p.label}`));
  h.appendChild(el('span', 'mc-s', `${picked.length} pulled · max ${DATA.meta.b_default} per divider`));
  card.appendChild(h);
  picked.forEach((c) => {
    const r = el('div', 'mc-r');
    const ph = photo(c.id, 'mc-ph');
    if (ph) r.appendChild(ph);
    const n = el('span', 'mc-n', c.name);
    const sm = el('small', null, `${c.min} min · ${bandPlain(c.b)}`);
    n.appendChild(sm);
    r.appendChild(n);
    r.appendChild(el('span', 'mc-v', `${fmtPct(c.s)} match`));
    card.appendChild(r);
  });
  card.appendChild(el('p', 'mc-f', hasPhotos()
    ? 'Photographs: Food.com, for the exact recipe shown.'
    : ''));
  out.appendChild(card);
  return out;
}

/* ---------------------------------------------------------------- how it's solved (tab) */

function viewOR(p) {
  const out = el('div');
  const feas = feasibility(p.candidates, state.k, state.cap, nBands());
  const guarantee = el('div', 'banner banner-info');
  guarantee.innerHTML = `Every combination of the two sliders — ` +
    `${fmtInt(DATA.meta.verification.combinations_checked)} in total — was checked in ` +
    `advance against <code>scipy.optimize.linprog</code>. The picks you see always match the ` +
    `mathematically best possible answer. The programme, the graphical slice and the dual are ` +
    `laid out in <strong>The method</strong> above; this tab shows the raw variables.`;
  out.appendChild(guarantee);
  if (!feas.feasible) { out.appendChild(infeasibleNotice(feas, state.k, state.cap)); return out; }
  const picked = solve(p.candidates, state.k, state.cap, 's');
  const tbl = el('table');
  tbl.innerHTML = '<thead><tr><th>Recipe</th><th>Band</th><th class="num">score s</th><th class="num">x</th></tr></thead>';
  const tb = el('tbody');
  for (const c of picked) {
    const tr = el('tr');
    tr.innerHTML = `<td>${esc(c.name)}</td><td>${bandName(c.b)}</td><td class="num">${fmt(c.s, 6)}</td><td class="num">1.0</td>`;
    tb.appendChild(tr);
  }
  tbl.appendChild(tb);
  const w = el('div', 'scroll-x');
  w.style.marginTop = '1.1rem';
  w.appendChild(tbl);
  out.appendChild(w);
  const cs = el('p', 'hint');
  cs.style.marginTop = '1rem';
  cs.textContent = 'Every other candidate has x = 0. Complementary slackness residuals — ' +
    Object.entries(p.dual.complementary_slackness).map(([k2, v]) => `${k2}: ${Number(v).toExponential(2)}`).join(', ') +
    `. Holds: ${p.dual.complementary_slackness_holds}.`;
  out.appendChild(cs);
  return out;
}

/* ---------------------------------------------------------------- history */

function historyBands(p) {
  const nB = nBands();
  const counts = new Array(nB).fill(0);
  p.history.forEach((h) => { counts[h.band] = (counts[h.band] || 0) + 1; });
  const total = counts.reduce((a, b) => a + b, 0) || 1;
  const box = el('div', 'beta');
  counts.forEach((n, i) => {
    const row = el('div', 'brow-b');
    row.appendChild(el('span', null, bandPlain(i)));
    const track = el('div', 'bt');
    const fill = el('div', 'bf');
    fill.style.width = `${(n / total) * 100}%`;
    fill.style.background = bandFill(i);
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el('span', 'bv', String(n)));
    row.appendChild(el('span', 'bs', bandRange(i)));
    box.appendChild(row);
    if (n) growBar(fill, { delay: 100 + i * 70 });
  });
  return box;
}

function viewProfile(p) {
  const out = el('div');
  out.appendChild(el('p', 'headline',
    `Everything the system knows about this person: ${p.n_positive_history} recipes they rated ` +
    `highly before ${DATA.meta.history_cutoff}. Nothing after that date was used — that would be looking at the answer key.`));
  const row = el('div', 'stat-row');
  row.appendChild(stat('Recipes rated highly', String(p.n_positive_history), 'used to build their taste profile'));
  row.appendChild(stat('As of', DATA.meta.history_cutoff, 'the "before" date'));
  out.appendChild(row);
  const sec = section('What kind of cooking they go for',
    `Across the ${p.history.length} recipes shown below. This is the shape the shortlist is being matched against.`, 'slots');
  sec.appendChild(historyBands(p));
  out.appendChild(sec);
  const tbl = el('table');
  tbl.innerHTML = '<thead><tr><th>Card</th><th class="num">Minutes</th><th>Divider</th></tr></thead>';
  const tb = el('tbody');
  for (const h of p.history) {
    const tr = el('tr');
    tr.innerHTML = `<td>${esc(h.name)}</td><td class="num">${h.minutes}</td><td>${bandPlain(h.band)}</td>`;
    tb.appendChild(tr);
  }
  tbl.appendChild(tb);
  const w = el('div', 'scroll-x');
  w.style.marginTop = '1.4rem';
  w.appendChild(tbl);
  out.appendChild(w);
  if (p.history.length < p.n_positive_history) {
    out.appendChild(el('p', 'hint', `Showing ${p.history.length} of ${p.n_positive_history} — this page only carries a small sample of each person's history.`));
  }
  const priv = el('p', 'hint');
  priv.style.marginTop = '.8rem';
  priv.textContent = 'The real Food.com account behind this profile is never shown or stored anywhere on this page.';
  out.appendChild(priv);
  return out;
}

/* ---------------------------------------------------------------- evidence */

const COLUMN_PLAIN = {
  method: 'Approach', stage: 'Test stage', k: 'Picks', cap: 'Variety limit',
  n_users_evaluated: 'People tested', n_users_with_positives: 'People with a real match',
  mean_recall_at_k: 'Hit rate', mean_ndcg_at_k: 'Ranking quality',
  mean_bands_represented: 'Avg. dividers used', mean_cap_violations: 'Rule breaks',
  pct_exact_size_ok: '% picked exactly 6', pct_feasible: '% had a valid list',
  failure_rate_pct: '% failed', mean_candidates: 'Recipes considered',
  mean_reduction_ratio: 'Shortlist vs. full catalogue', mean_scoring_seconds: 'Scoring time (s)',
  mean_solve_seconds: 'Solving time (s)', mean_total_seconds: 'Total time (s)',
  metric: 'Measuring', method_a: 'Approach A', method_b: 'Approach B',
  n_paired_users: 'People compared', mean_a: 'A\'s score', mean_b: 'B\'s score',
  mean_absolute_difference: 'Difference', ci_low: 'Range (low)', ci_high: 'Range (high)',
  ci_level: 'Confidence', n_bootstrap_resamples: 'Resamples', seed: 'Random seed',
  interval_excludes_zero: 'Real difference?',
  n_users: 'People', n_infeasible: 'No valid list', n_exact_size_ok: 'Picked exactly 6',
  n_feasible: 'Had a valid list', n_failed_on_feasible_input: 'Failed anyway',
  note: 'Note', sweep: 'Test type',
};
const SWEEP_PLAIN = { length_sweep: 'List length', cap_sweep: 'Variety limit' };
const plainCol = (c) => COLUMN_PLAIN[c] || c.replace(/_/g, ' ');
const dejargon = (s) => Object.keys(METHOD_PLAIN).reduce((acc, code) => acc.split(code).join(methodPlain(code)), s);
const plainCell = (col, v) => {
  if (col === 'method' || col === 'method_a' || col === 'method_b') return methodPlain(v);
  if (col === 'sweep') return SWEEP_PLAIN[v] || v;
  if (col === 'interval_excludes_zero') return v ? 'Yes' : 'No';
  if (typeof v === 'number') {
    if (col.includes('pct') || col === 'ci_level') return Number.isInteger(v) ? `${v}` : v.toFixed(1);
    return Number.isInteger(v) ? String(v) : v.toFixed(4);
  }
  return esc(dejargon(String(v == null ? '' : v)));
};

function tableFrom(rows, title) {
  const out = el('div');
  if (!rows || !rows.length) { out.appendChild(el('p', 'hint', `${title}: not available in this export.`)); return out; }
  const h = el('h4', 'sub-h');
  h.textContent = title;
  out.appendChild(h);
  const cols = Object.keys(rows[0]);
  const tbl = el('table');
  tbl.innerHTML = '<thead><tr>' + cols.map((c) => `<th class="${typeof rows[0][c] === 'number' ? 'num' : ''}">${esc(plainCol(c))}</th>`).join('') + '</tr></thead>';
  const tb = el('tbody');
  for (const r of rows) {
    const tr = el('tr');
    tr.innerHTML = cols.map((c) => {
      const num = typeof r[c] === 'number' && !['method', 'method_a', 'method_b'].includes(c);
      return `<td class="${num ? 'num' : ''}">${plainCell(c, r[c])}</td>`;
    }).join('');
    tb.appendChild(tr);
  }
  tbl.appendChild(tb);
  const w = el('div', 'scroll-x');
  w.appendChild(tbl);
  out.appendChild(w);
  return out;
}

function moreDetails(summary, ...bodies) {
  const d = document.createElement('details');
  d.className = 'more';
  const sm = document.createElement('summary');
  sm.textContent = summary;
  d.appendChild(sm);
  const body = el('div', 'more-body');
  bodies.forEach((b) => body.appendChild(b));
  d.appendChild(body);
  return d;
}

function viewEvidence(_p, opts = {}) {
  const out = el('div');
  const sink = opts.working || out;
  const b = DATA.benchmark || {};
  if (!Object.keys(b).length) {
    const d = el('div', 'banner banner-block');
    d.innerHTML = '<strong>No benchmark run is included in this export.</strong> Nothing has been substituted for it.';
    out.appendChild(d);
    return out;
  }
  const paired = (b.paired_differences || []).find((r) => r.metric === 'recall_at_k' && r.method_a === 'AI_LP' && r.method_b === 'POPULARITY_LP');
  if (paired) {
    out.appendChild(intervalPlot({ diff: paired.mean_absolute_difference, lo: paired.ci_low, hi: paired.ci_high,
      leftLabel: 'favours "Most popular"', rightLabel: 'favours "Our method"' }));
    const aBetter = paired.mean_absolute_difference >= 0;
    const better = aBetter ? 'Our method' : 'The popularity approach';
    const worse = aBetter ? 'the popularity approach' : 'our method';
    const tail = paired.interval_excludes_zero ? '— a gap unlikely to be down to chance.' : ', though the gap here is small enough it could be chance.';
    const finding = el('div', 'banner banner-info');
    finding.style.marginInline = 'auto';
    finding.innerHTML = `<strong>The honest finding:</strong> ${better} found real future favourites more often than ${worse} did in this test ${tail} A personalised, taste-matched pick did not out-perform "just show what's popular" here — an honest result, reported plainly rather than hidden.`;
    sink.appendChild(finding);
    const how = el('p', 'sec-sub');
    how.style.marginInline = 'auto';
    how.textContent = 'The dot is the measured difference in hit rate. The bar is the range the true difference is 95% likely to sit in. If that bar crossed the centre line we could not rule out "no difference at all".';
    sink.appendChild(how);
  }
  const mc = (b.method_comparison || []).filter((r) => Number.isFinite(r.mean_recall_at_k));
  if (mc.length) {
    const sec = section('Hit rate, all four approaches',
      `Out of the recipes each person actually rated highly in the year after their cutoff, what share turned up in the ${mc[0].k} we picked. Three of the four scored exactly zero, and that is shown as zero rather than rounded away.`, 'rising');
    sec.appendChild(valueBars(mc.map((r) => ({ label: methodPlain(r.method), value: r.mean_recall_at_k })), { format: (v) => v.toFixed(4), highlight: methodPlain('AI_LP') }));
    const nd = el('p', 'sec-sub');
    nd.style.margin = '1.3rem 0 .5rem';
    nd.textContent = 'Ranking quality (NDCG) — the same picture, weighted so a good recipe nearer the top of the list counts for more.';
    sec.appendChild(nd);
    sec.appendChild(valueBars(mc.map((r) => ({ label: methodPlain(r.method), value: r.mean_ndcg_at_k })), { format: (v) => v.toFixed(4), highlight: methodPlain('AI_LP') }));
    sec.style.maxWidth = '760px';
    sec.style.marginInline = 'auto';
    sec.style.width = '100%';
    sink.appendChild(sec);
  }
  const note = el('div', 'banner banner-warn');
  note.style.marginInline = 'auto';
  note.innerHTML = '<strong>What this does and doesn\'t show.</strong> It shows whether picks matched recipes people actually rated well later. It does <em>not</em> show whether having fewer choices made anyone less stressed, more confident, or happier with their meal — nobody was surveyed or timed. The "less choice is easier" idea is why we built this the way we did; it isn\'t something this test measured.';
  sink.appendChild(note);
  const bodies = [
    tableFrom(b.method_comparison, 'How each approach did, on average'),
    tableFrom(b.paired_differences, 'Head-to-head comparison, with confidence ranges'),
  ];
  const ciNote = el('div', 'banner banner-info');
  ciNote.style.margin = '.75rem 0 1.25rem';
  ciNote.innerHTML = '"Real difference?" = No means the range we calculated includes "no difference at all" — so we can\'t rule that out from this test alone.';
  bodies.push(ciNote);
  bodies.push(tableFrom(b.sensitivity_length, 'What happens with a longer or shorter list'));
  bodies.push(tableFrom(b.sensitivity_cap, 'What happens with a looser or tighter variety rule'));
  bodies.push(tableFrom(b.feasibility, 'How often each approach could produce a valid list'));
  const more = moreDetails('See the detailed numbers', ...bodies);
  more.style.maxWidth = '900px';
  more.style.marginInline = 'auto';
  more.style.width = '100%';
  sink.appendChild(more);
  return out;
}

/* ---------------------------------------------------------------- credits */

function renderCredits() {
  const host = $('#credits');
  if (!host) return;
  host.innerHTML = '';
  const items = [];
  if (STOCK) {
    Object.values(STOCK).flat().forEach((it) => {
      if (!it || !it.file) return;
      if (!document.querySelector(`img[src*="${it.file}"]`)) return; // credit only what this page shows
      items.push(`<li><a href="${esc(it.source)}">${esc(it.title || it.file)}</a> by ${esc(it.creator || 'unknown')}, ` +
        `<a href="${esc(it.license_url)}">${esc(String(it.license).toUpperCase())} ${esc(it.license_version || '')}</a>, via Openverse.</li>`);
    });
  }
  if (hasPhotos()) {
    items.push(`<li>Recipe photographs are the images Food.com publishes for each recipe shown (${Object.keys(PHOTOS.recipes).length} recipes), ` +
      'fetched once for this academic page and self-hosted. Not affiliated with Food.com.</li>');
  }
  host.innerHTML = items.length ? `<ul>${items.join('')}</ul>` : '<p class="hint">No photographs on this page.</p>';
}

/* ---------------------------------------------------------------- wiring */

const VIEWS = {
  shortlist: { build: viewShortlist, update: updateShortlist },
  try: { title: 'Try it yourself', build: viewTry },
  compare: { title: 'Four ways to pull', build: viewCompare },
  profile: { title: 'Their cards', build: viewProfile },
  solved: { title: "How it's solved", build: viewSolved },
};

/* The box: the board is the page. */
function renderDemo() {
  const host = $('#view');
  if (!host) return;
  const p = DATA.profiles[state.profile];
  const working = $('#view-working');
  const same = lastRender.view === 'shortlist' && lastRender.profile === state.profile;
  if (same) updateShortlist(p, host, working);
  else {
    host.innerHTML = '';
    if (working) working.innerHTML = '';
    host.appendChild(viewShortlist(p, { working, landscapeInline: true }));
  }
  lastRender = { view: 'shortlist', profile: state.profile };
  const count = $('#boxcount');
  if (count) { count.innerHTML = ''; count.appendChild(viewBoxCount(p)); }
}

/* Sheets: Four ways, How it's solved, Try it, Their cards open over the board and close back to it. */
const sheetState = { open: null, returnTo: null };

function renderSheet() {
  const body = $('#sheet-body');
  const v = VIEWS[sheetState.open];
  if (!body || !v) return;
  body.innerHTML = '';
  body.appendChild(v.build(DATA.profiles[state.profile]));
}

function openSheet(name) {
  const sheet = $('#sheet');
  if (!sheet || !VIEWS[name] || name === 'shortlist') return;
  sheetState.open = name;
  sheetState.returnTo = document.activeElement;
  $('#sheet-title').textContent = VIEWS[name].title;
  renderSheet();
  sheet.hidden = false;
  document.body.classList.add('sheet-open');
  sheet.scrollTop = 0;
  const close = $('#sheet-close');
  if (close) close.focus();
  if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
}

function closeSheet() {
  const sheet = $('#sheet');
  if (!sheet || sheet.hidden) return;
  sheet.hidden = true;
  document.body.classList.remove('sheet-open');
  sheetState.open = null;
  if (location.hash) history.replaceState(null, '', location.pathname);
  if (sheetState.returnTo && sheetState.returnTo.focus) sheetState.returnTo.focus();
}

/* A mount with a working: the host takes the artefact, `<id>-working` takes the rest. */
function mount(id, build, extra = {}) {
  const host = $(`#${id}`);
  if (!host) return;
  const working = $(`#${id}-working`);
  const text = working ? working.querySelector(':scope > .text') : null;
  host.innerHTML = '';
  if (working) { working.innerHTML = ''; if (text) working.appendChild(text); }
  host.appendChild(build(DATA.profiles[state.profile], { working, ...extra }));
}

function renderMethod() {
  mount('board', viewShortlist, { k: DATA.meta.k_default, cap: DATA.meta.b_default });
  requestAnimationFrame(() => document.dispatchEvent(new CustomEvent('handful:board')));
  mount('lpp', viewLpp);
  mount('slice', viewSlice);
  mount('certline', viewDual);
  mount('receipt', viewReceipt);
}

function renderAll() {
  renderTry();
  renderMethod();
  renderDemo();
  if (sheetState.open) renderSheet();
  document.querySelectorAll('[data-live="profile"]').forEach((n) => { n.textContent = DATA.profiles[state.profile].label; });
}

function bindControls() {
  const k = $('#k'), cap = $('#cap');
  state.k = DATA.meta.k_default; state.cap = DATA.meta.b_default;
  if (k) { k.min = DATA.meta.k_range[0]; k.max = DATA.meta.k_range[1]; k.value = state.k; }
  if (cap) { cap.min = DATA.meta.b_range[0]; cap.max = DATA.meta.b_range[1]; cap.value = state.cap; }
  const setVals = () => { const kv = $('#k-val'), cv = $('#cap-val'); if (kv) kv.textContent = state.k; if (cv) cv.textContent = state.cap; };
  setVals();

  const demoFirst = DATA.profiles.findIndex((p) => hasRefusal(p, state.k, state.cap));
  state.profile = demoFirst >= 0 ? demoFirst : 0;

  document.querySelectorAll('select[data-profile]').forEach((sel) => {
    sel.innerHTML = '';
    DATA.profiles.forEach((p, i) => { const o = el('option', null, p.paper_example ? `${p.label} (paper example)` : p.label); o.value = String(i); sel.appendChild(o); });
    sel.value = String(state.profile);
    sel.addEventListener('change', () => {
      state.profile = +sel.value;
      document.querySelectorAll('select[data-profile]').forEach((o) => { if (o !== sel) o.value = sel.value; });
      tryReset();
      renderAll();
    });
  });

  const onSlide = () => { setVals(); renderMethod(); renderDemo(); if (sheetState.open && sheetState.open !== 'try') renderSheet(); };
  if (k) k.addEventListener('input', () => { state.k = +k.value; onSlide(); });
  if (cap) cap.addEventListener('input', () => { state.cap = +cap.value; onSlide(); });
  const reset = $('#reset');
  if (reset) reset.addEventListener('click', () => {
    state.k = DATA.meta.k_default; state.cap = DATA.meta.b_default;
    if (k) k.value = state.k; if (cap) cap.value = state.cap;
    onSlide();
  });

  document.querySelectorAll('[data-sheet]').forEach((b) => b.addEventListener('click', () => openSheet(b.dataset.sheet)));
  const close = $('#sheet-close');
  if (close) close.addEventListener('click', closeSheet);
  const sheet = $('#sheet');
  if (sheet) {
    sheet.addEventListener('click', (e) => { if (e.target === sheet) closeSheet(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !sheet.hidden) closeSheet(); });
    // A link from the story can open the box on a named view: /demo/#try, /demo/#solved.
    const wanted = (location.hash || '').replace('#', '');
    // /demo/#try predates the standalone page and is printed in the handover: honour it.
    if (wanted === 'try') { location.replace('/try/'); return; }
    if (VIEWS[wanted] && wanted !== 'shortlist') openSheet(wanted);
  }
}

/* The floating control. */
function bindChrome() {
  const onScroll = () => document.body.classList.toggle('past-fold', window.scrollY > window.innerHeight * 0.7);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // The floating pill repeats a CTA the page already shows in the flow (the
  // pending note's own clipped text, "the box" section's own two big buttons).
  // Rather than sit on top of them, it steps aside while either is in view.
  const hideTargets = document.querySelectorAll('.pending, .btn-row');
  if (hideTargets.length && 'IntersectionObserver' in window) {
    const visible = new Set();
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => { if (e.isIntersecting) visible.add(e.target); else visible.delete(e.target); });
        document.body.classList.toggle('pill-yield', visible.size > 0);
      },
      { rootMargin: '-10% 0px -10% 0px' }
    );
    hideTargets.forEach((el) => io.observe(el));
  }
}

function banners() {
  const host = $('#banners');
  if (!host) return;
  host.innerHTML = '';
  if (DATA.meta.is_synthetic) {
    const b = el('div', 'banner banner-block');
    b.innerHTML = '<strong>SYNTHETIC FIXTURE — NOT RESEARCH DATA.</strong> This build is pointed at a generated test dataset, not the Food.com files. Every recipe name, score and shortlist here is fabricated for software testing and must not be cited.';
    host.appendChild(b);
  }
}

function footNote() {
  const host = $('#foot-note');
  if (!host) return;
  const m = DATA.meta;
  host.innerHTML = `${esc(m.extract_note)}<br><br>Dataset: ${esc(m.dataset.name)}, version ${esc(m.dataset.version)}. ` +
    `Licence: “${esc(m.dataset.licence)}”. Encoder: <code>${esc(m.encoder.model_id)}</code>. Built ${esc(m.generated_utc)}. No data is collected by this page.`;
}

function liveNumbers() {
  const den = DATA.meta.denominators;
  document.querySelectorAll('[data-num]').forEach((n) => {
    const key = n.dataset.num;
    const v = key === 'catalogue' ? den.n_catalogue_recipes
      : key === 'users' ? den.n_ranking_eligible_users
        : key === 'eligible' ? den.n_history_eligible_users
          : key === 'combos' ? DATA.meta.verification.combinations_checked : null;
    if (v == null) return;
    // Only a stat tile marked data-count animates. A number inside a sentence is set at
    // once, so the sentence is never briefly wrong.
    if (n.hasAttribute('data-count')) countUp(n, v, fmtInt, { duration: 1100 });
    else n.textContent = fmtInt(v);
  });
}

function fatalDataError(e) {
  const host = $('#view') || $('#try') || document.body;
  host.innerHTML = '<div class="banner banner-block"><strong>The demo data has not been exported yet.</strong><br>' +
    'Run <code>python scripts/export_demo.py</code> after the pipeline has produced results, then redeploy. ' +
    `Nothing has been substituted for it.<br><br><span class="mono">${esc(e.message)}</span></div>`;
}
function fatalRenderError(e) {
  const host = $('#view') || $('#try') || document.body;
  host.innerHTML = '<div class="banner banner-block"><strong>The data loaded, but this view failed to draw.</strong><br>' +
    `The export is fine — this is a bug on the page.<br><br><span class="mono">${esc(e && e.message ? e.message : e)}</span></div>`;
  if (window.console) console.error(e);
}

const getJSON = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);

Promise.all([
  fetch('/assets/data.json').then((r) => { if (!r.ok) throw new Error(`data.json returned ${r.status}`); return r.json(); }).catch((e) => { fatalDataError(e); return null; }),
  Promise.resolve(null), // recipe photographs are off; see the photographs note above
  getJSON('/img/stock/manifest.json'),
]).then(([d, photos, stock]) => {
  if (!d) return;
  DATA = d;
  PHOTOS = photos;
  STOCK = stock;
  try {
    banners();
    bindControls();
    bindChrome();
    footNote();
    liveNumbers();
    mount('evidence', viewEvidence);
    renderCredits();
    renderAll();
    bindReveals();
    renderCredits(); // again, so photos added by the views are credited too
    document.body.classList.add('is-ready');
  } catch (e) {
    fatalRenderError(e);
  }
});
