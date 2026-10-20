# DESIGN.md — Handful

The visual world, recorded as built so no session re-derives it. Rewritten 2026-09-08 at the
end of the ceiling pass (D-029) and recomposed 2026-09-09 (D-032); the direction is D-029's,
the composition is D-032's.

**`project_mode`: `independent`.** This is Rish and Khushi's academic project, not a Reidify
surface and not client work. Reidify's charcoal/bone/chrome/copper identity **never appears
here**. The principles transfer; the values do not.

**Direction owner:** this file, by candidate-and-roll (below). **Engine owners:** CSS, the Web
Animations API, GSAP and the field runtime, with disjoint property ownership (the "Engines"
section and `docs/MOTION_SPEC.md`). Two vendored libraries, no framework (D-034).

`PRODUCT.md` and `VOICE.md` do not exist at the project root. The product facts live in
`docs/` and the Release 2.0 spec; the voice is the one in `site/` and the handover package.
Both are worth writing; neither was in scope for D-029.

---

## The direction: the recipe card index

**Seed** `e824c2b` (`git rev-parse --short HEAD` at the start of the pass).
`0xe824c2b = 243,420,203`; `243,420,203 mod 7 = 5`; remainder 5 is ordinal **6 of 7**.
The contract is printed as a comment at the top of `<body>` in both pages:
`DIRECTION CONTRACT · seed e824c2b · 0xe824c2b mod 7 = 5 · form: the recipe card index (6 of 7) · D-029`.

**The rejected generic draft.** A warm research landing page: cream ground, a serif display
face, a metric strip of three big numbers, four same-size band cards in a row, a coloured
left border on every callout, a photograph behind the headline. It is what the site would
have become by preference — and it fails the portability test: swap the wordmark and it is
any food-tech company's page. Named and refused before the candidates were generated.

**The seven candidates**, all from inside this project's own world, in the resonance order
used for the roll. (This list was reconstructed after a context reset during the pass; the
contract comment in the pages is the primary record of the roll and its result.)

1. The menu — courses, dotted leaders, prices as scores, 86'd for a refusal.
2. The cookbook spread — a set page, numbered method steps, photographs in the layout.
3. The kitchen order rail — the shortlist as tickets on a rail, pulled in order.
4. The ratings ledger — the person's history as a ruled account book, the shortlist a
   balance.
5. The dinner table — six places set, the candidates on a sideboard.
6. **The recipe card index** — every recipe a card, the four bands the coloured dividers in
   the box, the shortlist the six cards pulled out, a refusal a card stamped and put back.
7. The solver's tableau — the simplex tableau as the page grid, pivots as chapter turns.

The roll landed on 6. It was not the preference (the preference was 2, the D-027 choice),
which is the point of rolling.

### Why the card index holds

The metaphor is the model. A card is a candidate; a divider is a preparation-time band; the
cap is "at most three from behind any one divider"; the optimum is the six pulled; the
mechanism the project exists to show — a card that scored well enough being refused because
its divider is full — is a card stamped **86'D** and put back. Every word on both pages
("card", "divider", "the box", "pulled", "put back") is the same word the diagram uses, so
the reader is never translating between the picture and the text.

**Materials, not decoration.** Card stock (`--paper`) for anything that is a card; the table
it sits on (`--ground`) for the page; the tin (`--box`, dark) for the one artefact that must
subtract — the box count. A red header rule on a card (`--rule-red`) and faint blue body
rules (`--rule-blue`) are printed on index cards; they are texture here and never a border
or an accent. Coloured tabs on the dividers are the band scale. Typewriter ink (`--mono`)
for what was typed on the cards: counts, minutes, scores, the programme. Pencil
(`--pencil`) for the score in the corner.

**Portability test, per screen.** The opener is a box with six cards pulled from it; the
rule is the four dividers with their caps printed on them; the pull is the board with a
stamped card; the programme, the slice and the certificate are the method; the result is
the interval plot; limits is one sentence the project had to write. None of it moves to
another site with the wordmark swapped.

## Surface modes

| Surface | Mode | Visitor's success |
|---|---|---|
| `site/` — the story | **Read** | Following the argument one screen at a time — the rule, the pull, the programme, the slice, the certificate, the result, limits — then opening the box |
| `site/try/` — try it yourself | **Operate** | Feeling the difference between sixty options and six, on a phone, in a minute - then being told plainly why that feeling is not evidence (D-033) |
| `site/demo/` — the box | **Operate** | Choosing a person, moving the two rules, and seeing *why* six particular cards were pulled and which one was stamped and put back |
| `app/` — the Streamlit demo | **Operate** | Inspecting a real profile, shortlist and LP solution locally |

One stylesheet and one script serve both web pages, so they cannot drift. The story hands
off with a call to action ("Open the box"); the box can open on a named view from a link
(`/demo/#try`, `/demo/#solved`, `/demo/#compare`, `/demo/#profile`). There is no presenter mode and no speaker notes
(removed 9 Oct 2026, D-041): the pages are written to be read.

## Composition (D-032): one artefact per screen, the working one layer down

The pages are not documents with a skin. Each screen is one picture and one sentence; the
rigour sits directly beneath it behind a quiet "Method detail" line (`<details
class="working">`) that opens in place. Nothing an examiner needs leaves the page; it is
sequenced. Spacing is unequal on purpose: `--screen-y` (14vh) between screens, tight inside a
screen. Two screens are dark (the opener and the certificate) so the page has range.

The story's screens, and what the reader must be able to say after each:

| Screen | The artefact | The sentence |
|---|---|---|
| The opener (dark) | The title, then the six pulled cards held as a hand; the box count as one line | "A handful of recipes, not a thousand." |
| The rule | One photograph strip: four dividers, the cap printed on each | "At most three from behind any one divider." |
| The pull | The board for the worked person, one card stamped 86'D | "Six pulled. One good card put back." |
| The programme | The linear programme, set large | "Maximise match. Exactly six. At most three per divider." |
| The graphical method | The draggable slice | "The best answer is always a corner." |
| Duality (dark) | The certificate as one line | "Nothing better exists, and this proves it." |
| The result | The interval plot alone | "Popularity beat us, and we say so." |
| The box | The button | "Pull the six yourself." |
| Limits | One line, large | "Choice overload is the motivation, never the finding." |

A tenth, short screen ("Done, and what comes next") closes the story; the status
detail itself lives under Limits.

The box: the board is the page. The two sliders sit above it with large values; the other
views (*Four ways*, *How it's solved*, *Try it*, *their cards*) open as sheets over the
board and close back to it, and `/demo/#<view>` opens one directly. Chips carry a
photograph, a name and a score; minutes and divider appear on hover. The 86'D stamp is the
only red on either page.

Chrome: a wordmark, and on the story a single floating pill ("Open the box") that appears
once the opener has scrolled away. No chapter nav.

**The phone (D-033).** Both pages are checked at a true 390px, not merely for overflow.
The header is one scrollable row of pills; an empty board slot is a hairline rather than a
box; sliders are full width; sheets are full-bleed with a sticky head. `/try/` is designed
phone-first because that is where a classroom will open it.

**Recipes with no photograph.** 209 of the 470 recipes in the extract have none on
Food.com, which was confirmed against the source pages rather than assumed. Their cards
show the recipe's initial on its divider colour. No stock photograph is ever substituted
for a dish - see the photography rule above.

## The register (D-034): the archive at night

The vocabulary above is unchanged. The *register* changed on 2026-09-11 from a warm paper
document to the table at night: a generated, lamp-lit wooden table sits fixed under every
page; everything made of paper - cards, the board's rows, the working sheets, the sheets
that open over the box - stays paper. One light, upper-left, warm. Depth where the argument
lands (the opener, the box screen), paper where reading happens. The luminance range this
produces is the point: 0.867 on the story's first screen at 1440, 0.925 on the box, 0.846
on try, against a reference median of 0.849.

**Surface tokens.** `--fg`, `--fg-2`, `--fg-muted`, `--rule`, `--link` are set dark on the
ground and reset to ink on `.card`, `.working-body`, `.sheet-panel`, `.brow`, `.chart`,
`.bill`, `.slice`, `.banner` and the other paper surfaces, so a component never needs to
know which ground it is on. New components take colour from these five, never from `--ink`
or `--on-box` directly.

**The opener.** Full-bleed. `opener.js` mounts the field runtime on a generated still of
index cards receding into the dark (`img/gen/field-still-*`), lights it, breathes with the
pointer and moves into it as the page scrolls; the six real, photographed cards sit on the
runtime's plate positions in front of it; the title is a thin layer over the dark lower
third. Where WebGL2 is missing the same still is a CSS background. On a phone the still is
the tall variant and the six cards are a grid under the title.

**The deal.** On the story, `flight.js` (GSAP + ScrollTrigger) deals the six onto the
board as it scrolls into view, scrubbed by the page, one after another, from above. Phones
and reduced motion get the cards in place.

**Generated imagery, and the rule.** Grounds, the four divider scenes, the box prop, the
86'd stamp impression and the opener still are generated (OpenAI GPT Image via ChatGPT,
2026-09-10, from `IMAGE_HANDOFF_FOR_CHATGPT.md`), converted to responsive WebP under
`img/gen/` with a `manifest.json` carrying source, prompt and model, and credited as
generated in the colophon. The rule, which does not bend: generation only where the image
is an invention - atmosphere, a category, a prop, a texture. **A generated image never
stands in for a recipe.** The 209 recipes without a Food.com photograph show their initial
on their divider's colour.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--paper` | `#fbf5ea` | Card stock: every surface that is a card |
| `--ground` | `#f1e8d8` | The table the box sits on: page ground |
| `--box` | `#2a211b` | The tin: the box count, the programme blocks |
| `--ink` | `#1c1611` | Typewriter ink: headings, primary text |
| `--ink-2` | `#3a322b` | Body text |
| `--muted` | `#6e6258` | Secondary text, captions. 5.2:1 on paper |
| `--pencil` | `#4b4642` | The score pencilled in the corner |
| `--line` / `--line-2` | `#e2d7c5` / `#ece3d3` | Card edges, hairlines |
| `--rule-red` | `#c9463b` | The header rule printed on a card. A material, never an accent |
| `--rule-blue` | `rgba(96,140,184,.22)` | The body rules. Texture, never a border |
| `--accent` | `#1f6b3a` | **The only accent.** Chosen, a link, our method, a green pen tick |
| `--stop` | `#a3232a` | The red ink stamp: 86'd, refused, must-not |
| `--warn` | `#8a5200` | The pending state and the "does not show" callout |

Every text colour on paper and ground was computed, not eyeballed: the lowest is `--muted`
on `--paper` at 5.2:1; body ink is above 13:1. Non-text UI (card edges over ground, the
slider track, band fills with their line) clears 3:1 with the line colour as the edge.

### The band scale — an ordinal encoding, validated

Bands are ordered, so they get one hue stepping in lightness with cooking time. The scale
was run through the `dataviz` validator in `--ordinal` mode and passes (the earlier
amber-to-rust ramp failed it: adjacent ΔE 10.7, light end 1.63:1).

| Band | Fill | Line | Wash |
|---|---|---|---|
| Quick, ≤15 min | `#f28b67` | `#ae593a` | `#fdece5` |
| Fast, 15–30 | `#cf6c49` | `#974426` | `#fbe6dd` |
| Moderate, 30–60 | `#ae4e2a` | `#81300f` | `#f8e0d6` |
| Long, over an hour | `#8d2f04` | `#6a1a00` | `#f4dacf` |

Rules: band colour never sets text; every fill carries its line as a hairline so the light
end clears 3:1 as an object; the scale is outside the accent's hue so the two cannot be
confused; each band also has a dial icon (quarter, half, three-quarter, full) so the order
reads without colour.

### Photographs, and the one rule that governs them

- **Per-recipe photographs** come only from Food.com's own page for that recipe id, via
  `scripts/fetch_recipe_images.py` (og:image, CDN transform `w_480,h_360,c_fill,q_80`),
  self-hosted under `site/img/recipes/<id>.jpg`, gitignored, deployed from the local
  directory, credited "Photographs: Food.com, for the exact recipe shown." A photograph of a
  different dish beside a real recipe name is a fabricated visual claim and is forbidden.
  Where no photograph exists the card shows ruled stock and its divider tab, never a
  substitute. The manifest gates every render.
- **Ambience photographs** (the hero, the four divider cards) are CC-BY from Openverse via
  `scripts/fetch_stock_images.py`, self-hosted under `site/img/stock/`, credited by creator
  and licence in the image-credits block. Never beside a specific recipe.

No text sits over a photograph on either page, so `tools/contrast-over-media.mjs` had
nothing to measure in this pass; if a chapter opener ever puts type on a photograph, run it.

## Type

Three faces, each with one job:

- **Newsreader** (400/500/600, optical size on) — the printed face: display, headings,
  ledes, the chapter subtitles, the bill.
- **Inter** (400–700) — the interface and running text: body, labels, controls, tables.
- **Courier Prime** (400/700) — what was typed on the cards: counts, minutes, scores, the
  programme, the pending state.

The ramp (D-032): display `clamp(3rem, 7.5vw, 6.5rem)` = 104px at 1440 and 48px on a phone,
tracking −0.05em; the sentence on each screen `clamp(2rem, 4.6vw, 3.6rem)`; h3 1.5rem;
body 18px (1.125rem); small 15px; label 12px. Largest-to-smallest: **8.7×** (104/12). Running measure: `p`, `.prose` and `.chapter-sub` are capped at **52ch**, which in
Inter at 17px sets 70 characters a line (measured, not assumed: `ch` is the width of a zero,
so 62ch had set 85). More space above every heading than below it.

Known gap, carried: the fonts are served from Google Fonts rather than self-hosted. Closing
it needs the licence position recorded and the files vendored under `/assets/`; the CSP's
`font-src`/`style-src` would tighten with it.

## Motion — MotionSpec v1, as built

**Personality:** a card being pulled from a box. Short, decisive, no bounce, one easing
everywhere (`cubic-bezier(.2,.7,.3,1)`), and nothing loops. Motion exists to make structure,
causality and feedback legible; it never decorates and never hides content until a script
runs (everything is in the DOM at rest; reveals start from 25% opacity, not 0).

**The signature moment: the pull.** On the hero and on the box's board, the six cards rise
out of the box — `translateY(46px) → 0`, 640ms, staggered 220 + 110·i ms — and rest. The
same gesture, smaller, when a slider moves: the board re-slots with FLIP (measured before
and after, transform only), so a card visibly moves from one divider to another, and a card
that scored well enough but lost its slot is struck through and stamped 86'D. That stamp is
the research contribution and it is the one place the red ink moves.

**Supporting micro-interactions, each carrying one fact:**

- No chapter fades (removed under D-032): the pull is the only entrance motion on the story.
- Path draw: the interval plot's confidence bar and the slice's constraint line draw once
  (`stroke-dashoffset`, 560–600ms) and rest. A hairline that resolves, per the reference set.
- Count-up: only elements carrying `data-count` (the box counts, the catalogue funnel) count
  up, 1.1–1.4s. No number in prose, in the certificate or in a proof ever animates — a
  briefly wrong number in a proof is a wrong proof.
- Landscape marks settle in (300ms, 5ms stagger), chosen last so the eye lands on them.
- Hover reveals, not decorates: a chip lifts and shows its photograph and score; a landscape
  dot names its recipe; a bill line names its divider. Lift is on the inner `.card`, so a
  parent the engine moves never shares a transform with a CSS hover.
- The draggable slice: the point follows the pointer along `x_A + x_B = 1` with no easing,
  because a lag would misreport where the objective is being evaluated.

**Reduced motion is a branch, not a variant.** `prefers-reduced-motion: reduce` makes
`anim()` return before it starts; the finished state is what the DOM already holds. Verified
by emulation: 0 animations, opacity 1, transform none, every count at its final value.

**Refused:** parallax on anything read, floating shapes, scramble text, an identical fade
on every section, any loop that carries nothing. The one scroll-scrubbed sequence (the deal)
is an enhancement over a page that is complete without it: on a phone, with reduced motion,
or without GSAP, the cards are simply there.

## Engines

One owner per element and property, disjoint by construction:

| Engine | Owns | Addresses |
|---|---|---|
| CSS | `background`, `border-color`, `color`, `box-shadow`, `fill`, `stroke`, hover, focus, `:has`, layout, the `.card` lift on hover | Anything |
| Web Animations API (`viz.js`: `anim`, `riseIn`, `flip`, `drawPath`, `countUp`, `growBar`) | `transform`, `opacity`, `stroke-dashoffset`, every count-up | **Only** elements carrying `data-anim` |
| GSAP 3.15 + ScrollTrigger (`flight.js`, `opener.js`; vendored under `assets/vendor/`) | `transform`, `opacity` | **Only** elements carrying `data-flight`: the six pulled cards, and the story board's chips |
| field runtime (`field.js`, vendored from the framework) | the canvas's uniforms: enter, scroll, pointer, light | `canvas#field` only |

**The invariant, now enforced in the stylesheet:**
`[data-anim]{transition-property:background-color,border-color,color,box-shadow,fill,stroke}`
— a CSS transition on such an element can never name `transform` or `opacity`. `anim()`
defers one frame and refuses a detached node, so no `Animation` is ever left `running` on an
element that never mounted (that was the cause of the earlier 10px misalignment).

Two vendored libraries, both same-origin under the site's `script-src 'self'`: GSAP (the
scrubbed flight of the six cards, which WAAPI cannot express as one reversible progress)
and the framework's field runtime (the opener's canvas). D-025's refusal is superseded by
D-034 with that reason; nothing is fetched from a third party and nothing is sent.

## The artefacts

Authored SVG and DOM, drawn from `assets/data.json`, carrying content rather than decorating
it:

1. **The hand** (opener): the six pulled cards fanned like a hand of cards, photograph, name
   and score, the box count as one line beneath.
2. **The board** (the six): four divider rows, `cap` slots each, `k` filled, the refused
   card struck and stamped. It *is* the model.
3. **The score landscape**: every candidate by match against reported minutes; chosen
   ringed, refused hollow. "Why those, and what it turned down."
4. **The interval plot**: the paired difference against the zero line.
5. **The two-variable slice**: the unit square, the constraint segment, the vertex optimum,
   draggable.
6. **The certificate**: primal, dual, gap, and the shadow-value bars.
7. **The bill**: the six itemised with dotted leaders and totalled.
8. **The funnel**: catalogue → untried → shortlist, log-scaled, labelled as such.

## Rules this project keeps

- **No eyebrow or kicker above a heading.** The chapter tab is structure, not a kicker: it
  is the divider the chapter sits behind.
- **No gradient text.** Emphasis is weight and size.
- **Icons are authored SVG** at one stroke weight. Never emoji, never unicode glyphs.
- **One accent, sparingly.** Green marks chosen, a link, or our method — nothing else. Red
  ink is a stamp, never a highlight.
- **Unequal space.** Tight within a group, generous between; more above a heading than
  below.
- **No cards-in-a-row as page structure.** The four divider cards in the problem chapter
  are the four bands with their caps printed on them, which is information; anywhere a row
  of equal cards would only be layout, it is not used.
- **Numbers are typed.** Tabular figures everywhere digits line up; `en-GB` grouping.

## Truth constraints on any surface

Binding, and they outrank visual ambition:

- No fabricated recipe, score, metric, count or result. Every value rendered comes from
  `assets/data.json`, which `scripts/export_demo.py` writes from a real run. A diagram with
  no data behind it renders its empty state; it is never filled with a plausible number.
- No claim about choice overload, stress, confidence, decision speed, satisfaction,
  nutrition or allergy safety as an outcome. Motion must not imply one either — nothing
  animates to suggest relief or delight at being given fewer options.
- Review text is never rendered. Raw user ids are never shown.
- Khushi's introduction is pending and renders as an explicit `[[CONFIRM: ...]]` block in
  the mono register the content never uses. Nothing plausible stands in for it.
- Where the honest result is unflattering, it is stated plainly with the same visual weight
  a favourable one would get.

## Still to come

- Self-host the three faces (licence position first).
- The phone opener's luminance range (0.395) is below the bar; the tall still's lit area sits
  above the cards. A phone-specific crop or a second light would fix it.
- 23 of the 40 generated roles are unused (extra grounds, the raw card-blank/ruled props,
  the box-open state, the pencil, the stack of forty) - catalogued in `img/gen/manifest.json`,
  not yet placed (D-035).
- `PRODUCT.md` and `VOICE.md` at the root.
- Khushi's introduction into the pending block.
- A larger extract, if the licence position ever allows it: the box count is real but the
  candidates a slider can reach are a minimal extract, and the page says so.
