# Decision log

Every choice that could reasonably have gone another way, with its reason and its status.
A methodological change needs an entry here, an approver, and a `protocol_version` bump in
`config/research.yaml`.

**Approval columns are honest.** `Rish (implementation)` means a technical decision Rish is
entitled to make. `PENDING — Khushi` or `PENDING — instructor` means the decision is
recorded but **not yet approved**, and nothing downstream should be treated as settled.

---

## D-001 — Repository location

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

The build lives at `C:\Users\HP\dev\foodcom-research`, not inside the
`Reidify-Studio\Projects\Menu Choice Overload Research Demo` folder the session started in.

**Why.** The machine's workspace contract states that all git repos live under
`C:\Users\HP\dev\` and that a repo must never be created inside `Reidify-Studio\`, which is
a cloud-synced assets area where git breaks. The handoff requires a git-tracked repository
(it asks for `git status`, `.gitignore` and code-revision recording in run manifests). The
two source PDFs stay where they are — they are reference assets, not code.

**Consequence.** The Source-of-Truth PDFs and the code are in different trees. The PDFs are
referenced by path from this repo, not copied into it.

## D-002 — GitHub remote: private, resolved

**Date:** 2026-09-06 · **Status:** RESOLVED — Rish authorised it the same session

Remote is `https://github.com/reidifydesign/handful`, **private**, default branch `main`.

**Why private.** Run directories can contain pseudonymous Food.com user ids, the dataset
licence position is not yet established, and this is unpublished academic work that Khushi
has to submit. None of those is a reason for the code to be secret forever — it is a reason
not to make it public before the licence and the submission are settled.

The local branch was renamed from `build/initial-pipeline` to `main` before the first push,
since this is the mainline of a fresh repository with nothing to endanger.

## D-003 — Python 3.12 rather than 3.11

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

The handoff targets 3.11 "unless the existing project establishes another supported
version". No project existed; the machine has 3.12.10 and no 3.11. `requires-python` is
`>=3.11`, so 3.11 remains supported.

**Recorded in every run manifest** under `python`, so the interpreter is never a hidden
variable.

## D-004 — `tasks.py` alongside the Makefile

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

`make` is not installed on this machine. The `Makefile` is provided for parity with the
specification but delegates to `python tasks.py <target>`, which is the entry point that
actually works here and on any platform.

## D-005 — `all` excludes `final`

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

`python tasks.py all` runs audit → clean → splits → embeddings → validate → results-pack and
**stops**. The final test set is used once, after the configuration is frozen; chaining it
into a convenience target is how a test set gets spent by accident. `final` additionally
requires `config/FROZEN.lock` to exist and match, and requires the test suite to pass.

## D-006 — torch and sentence-transformers are an optional extra

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

They are a ~2.5 GB install and are needed only for real scoring runs. The test suite uses a
deterministic hash-based test encoder instead, so the whole suite runs in a light
environment.

**Guard.** `harness.evaluate_stage` refuses to produce results from any encoder whose
provenance says `is_research_grade: false`, unless a test explicitly opts in. The test
encoder therefore cannot leak into a research number by accident.

## D-007 — Tag whitelist is seeded, not exhaustive

**Date:** 2026-09-06 · **Owner:** Rish (implementation) · **Status:** to complete after the audit

`config/tag_rules.yaml` is a genuine whitelist — `unknown_tag_policy: exclude` — with deny
rules evaluated first and absolutely. The allow list is seeded from documented Food.com tag
families because the real tag vocabulary cannot be inspected before the data arrives.

**Action needed.** After `python tasks.py audit`, read `reports/audit/tag_vocabulary.csv`
(every tag, its frequency and its current whitelist status) and extend `allow_exact` from
that evidence. Do not guess tag names.

**Deny rules are deliberate.** Duration tags (`time-to-make`, `*-minutes-or-less`,
`*-hours-or-less`, `weeknight`) are excluded because they encode the preparation-time band —
the exact axis the LP constrains. Admitting them would confound the relevance score with the
constraint dimension.

## D-008 — Nutrition retained, unverified, unused

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

The seven-value array is parsed, length-checked and retained. `units_verified: false` and
`used_in_core_model: false`. It is commonly documented as calories plus six
percentage-daily-value fields, not gram quantities, and that has not been verified against
the downloaded release. No conversion, no nutritional claim, and no place in the LP.

## D-009 — No IQR trimming of long durations

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

Long `minutes` values are **flagged** above 24 h, never auto-deleted. Marinating, chilling
and slow cooking are legitimate, and an IQR rule would quietly delete much of band G4 —
which would then make the band cap look effective for the wrong reason.

## D-010 — Conflicting recipe ids are quarantined

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

Rows sharing an id but disagreeing on name, minutes, submitted, ingredients or steps go to
`data/interim/quarantine/`. Keep-first would silently choose a version of a recipe with no
basis for the choice. Identical repeats collapse to one row. Counts are in the ledger.

## D-011 — Earliest event wins; tied conflicts are seen but unlabelled

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

For repeated `(user, recipe)` pairs the earliest event is retained, so a later contradicting
rating is never averaged into earlier history. Tied earliest dates with different ratings
make the pair unusable as a label (`label_eligible = false`) but the recipe still counts as
**seen** — the user demonstrably encountered it, so recommending it later would not be novel.

## D-012 — Canonical tie-break for equally optimal sets

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

POPULARITY_LP produces ties in bulk (most recipes have zero positive reviews) and the solver
may return any equally optimal set, which makes runs irreproducible.

**Resolution:** recompute the optimum with the documented lexicographic rule (score
descending, then recipe id ascending) and accept it **only after** confirming its objective
equals the LP's within tolerance; otherwise the run records a structural failure. Scores are
never perturbed — perturbing them would change the objective silently.

## D-013 — Exact band pruning for the primal only

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

At most the top `b_g` candidates per band are kept before solving. Exact for this structure:
no optimum can use a `(b_g+1)`-th best candidate in a band, since it could be swapped for a
better-scoring one in the same band without touching a constraint. Evaluation denominators
still use the full catalogue.

**Superseded in part on 2026-09-07 — see D-024.** This entry originally said reported dual
certificates come from the full *unpruned* problem. They still describe the full problem,
but they are no longer obtained by solving it unpruned, because that is not computationally
viable at catalogue scale.

## D-014 — Failure vs infeasibility are reported separately

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

A method failing on a *feasible* input is charged recall zero in the primary table. A
*structurally infeasible* profile is reported separately with its coverage loss. A
common-success table, restricted to users where every method worked, accompanies the primary
table rather than replacing it.

## D-015 — Demo profile labels

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

The demo shows `profile-0007`-style labels. Raw Food.com user ids are not printed on any
screen, and review text is never rendered. Cohort ids stay inside run directories.

## D-016 — Synthetic fixture safety

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

Synthetic data exists only for unit tests and the smoke run. Three independent guards stop
it being mistaken for research: the encoder provenance carries `is_research_grade: false`
and the harness refuses it; the synthetic config's provenance fields carry
`SYNTHETIC-FIXTURE-NOT-RESEARCH-DATA`; and the demo renders a permanent red banner on every
screen when pointed at such a workspace.

## D-017 — Streamlit light theme pinned

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

`.streamlit/config.toml` pins `base = "light"`. Without it Streamlit follows the viewer's OS
dark-mode preference and renders the app's dark text white on the light surfaces the demo's
CSS defines — invisible. Found by running the demo, not by reading the code.

## D-042 - The data extract stays public, on a stated quotation basis and with a removal contact

**Date:** 2026-10-09 · **Owner:** Rish (decision), implementation by Rish's agent · **Status:** approved (Rish, 9 Oct 2026: keep the database and the study, no permission request)

The demo extract (`site/assets/data.json`) stays live and unchanged in content. What changes
is how the site describes it. The note no longer says the page "must not be published open
to the web" (the site has been public since the 7 Sep decision under D-021, so that sentence
contradicted the page it sat on). It now states what the extract is: about 1,300 recipe
titles with reported cooking time and band, well under 1% of the 230,541-recipe catalogue,
shown only to illustrate the study, with the source and licence stated and a contact
(hello@reidify.design) for anyone who holds rights in anything shown.

**Why.** No permission request will be made. The safest position that does not need one is a
small, attributed, non-substitutable quotation for research illustration, not a copy of the
dataset: titles and times only, no ingredients, steps, text, ratings or user ids; the extract
is not in git, not in either GitHub repo, and is marked noindex; the benchmark numbers are
derived statistics. This is a risk judgement, not a licence: the dataset licence still grants
no redistribution rights and the note says so. It is not legal advice.

**Impact.** No run, number or claim changes. `export_demo.py` carries the new note, the
Dataset line on the story page is reworded to match, and the deployed `data.json` must be
the one carrying the new note (it is deployed by hand, not from git). If anyone with rights
objects, remove the extract, switch the demo to the synthetic export, and record it here.

---

## D-041 - Presenter mode and speaker notes are removed; the look is unchanged

**Date:** 2026-10-09 · **Owner:** Rish (implementation) · **Status:** approved (Rish, 9 Oct 2026)

The story page loses its presenter mode: the Present button, the P / arrow-key handlers, the
seven hidden speaker notes, the footer's keyboard instructions, and the CSS and script that
served them. The footer now reads "Independent research. Not affiliated with Food.com. No
data is collected by this page."

**Why.** The page is now read as a piece of published research, not delivered to a room. A
presenter control and notes addressed to a speaker are the clearest sign of a course
submission. The design itself was explicitly kept ("no visual change at all").

**Impact.** No run, number or claim changes. Visual output verified against the previous
build by full-page pixel diff at 1440 and 390 on `/`, `/demo/` and `/try/`: `/demo/` and
`/try/` are identical; on `/` only the removed Present button (desktop) and the footer line
differ. The collapsible blocks stay (method, not presentation) and are relabelled "Method
detail". Headings and informal lines were reworded to a researcher's register (Rish approved
the list, 9 Oct 2026); the footer GitHub link now points at the public copy,
`rishsadh/handful`, which 404s until launch on 20 Oct; the repo is licensed MIT
(LICENSE added, pyproject aligned), matching the public copy.

---

## D-039 - The hero's card fan is retired; the opener becomes pure atmosphere

**Date:** 2026-09-11 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

D-036 curated six real, photographed recipes for the hero rather than one profile's literal
pull. Rish's next call went further: even curated real photos in the hero implied "these
six are the answer" before any answer had been given, and asked for the opener to become
atmosphere only, with the real six-recipe reveal happening exclusively where it already
lived - the "pull" section further down the page.

**What this meant concretely.** The `.pull-card` fan - six DOM cards placed on the field
shader's plate positions via `cells()`, entering with a GSAP stagger - is removed from the
opener entirely. `opener.js` now only mounts the shader against a still image; no items, no
plate placement, no card entrance. `viewDeck()`, `HERO_SHOWCASE`, and the now-dead
`.deck`/`.pull-layer`/`.pull-card`/`.deck-line` CSS are deleted rather than left dormant.
The `.pnote` and heading copy were rewritten to stop describing cards that no longer appear
in the hero and instead point at where the real pull happens.

**The background image also changed, on Rish's separate objection:** the existing
`field-still-wide/tall` (a flat grid of blank cards receding into darkness) read as
diagrammatic rather than immersive. Generated a replacement - an overflowing wooden
card-index box at night, close and tactile rather than a schematic grid - via the
`higgsfield-generate` skill and its Soul Location model (the skill's own routing table
calls this "best-in-class for environments and locations without a person in frame").

**Two rejected generations, in order:** the first render had legible pseudo-handwriting on
several cards and off-palette blue divider tabs - both hard violations of the image
brief's own rules (`IMAGE_HANDOFF_FOR_CHATGPT.md`: "cards are blank or ruled only," no
colour outside the four established divider hues). Corrected the prompt to insist on bare
cards and only the established orange/rust/brick-red tabs, and re-generated; the result
passed. A first attempt at the portrait crop was rejected too, for an ambiguous blurred
shape in one corner that could read as an out-of-focus hand under the project's own "no
hands" rule - regenerated clean rather than argued into acceptability. Both accepted images
are recorded in `img/gen/manifest.json` under `hero-archive-wide` / `hero-archive-tall`
with their real prompts and the model used; the old `field-still-wide/tall` files are left
in place, unused for now, available for a future surface rather than deleted.

**Verification.** `node --input-type=module --check` on `opener.js` (module syntax, so the
plain form would have silently passed regardless - see D-035). Confirmed in the browser,
both breakpoints: no console errors, no reference to the removed elements anywhere in
`app.js`/`opener.js`/`style.css`, the title's contrast scrim still holds against the new
image, `.opener.no-field`'s CSS fallback background updated to match. 187 tests pass, 1
skipped - untouched, this is presentation only.

**Not verified.** The new image's look on a real phone, same standing gap as every prior
motion/visual pass this project has shipped.

**Impact.** Presentation only. No protocol, run, or result changes. The one thing this
decision changes about the site's own claims: the hero no longer asserts anything about a
specific recipe at all, which if anything narrows the site's claims rather than widening
them.

## D-037 - The demo page's controls were broken by a class name collision with the opener's canvas

**Date:** 2026-09-11 · **Owner:** Rish (implementation) · **Status:** fixed

Rish reported the box page's profile dropdown looked broken and the sliders for
shortlist length and the divider cap had disappeared. Real bug, and it long predates
this report - it shipped with D-034 and nobody noticed until now.

**The cause.** D-034 styled the opener's WebGL canvas with `.field{position:absolute;
inset:0;...}` on the story page. `.field` was already the wrapper class every control
on the demo page uses - `<div class="field">` around "Whose box," each slider, and the
reset buttons (`site/demo/index.html`, `.controls-line`). The canvas rule applied to
those wrappers too, collapsing the sliders and the reset row to a full-viewport
absolutely-positioned box pinned to the top of the page. The profile dropdown looked
fine only by accident: a D-035 rule, `.field:has(#profile)`, added for the brass
label-holder prop, is more specific than a bare `.field` selector and happened to
override `position:absolute` back to `position:relative` for that one control. The
other three `.field` wrappers had no such rule and stayed broken.

**The fix.** Renamed the canvas's class to `.field-canvas` throughout
(`site/index.html`, `style.css`'s three rules that referenced it) and left `#field` as
its id, since `opener.js` only queries it by id. `.field` is now exclusively the
form-control wrapper it always was everywhere else on the site.

**Verification.** Confirmed via direct DOM measurement, not a screenshot: `#k`, `#cap`
and `#profile` all read `position: static` with sane widths (~230px) and document
positions after the fix, both locally and on the redeployed production site. Functional
check: switching the profile select changes the rendered board, and moving the `k`
slider updates its live value label. The story page's opener canvas still mounts
correctly under its new class (`.opener.has-field` set, `position: absolute; inset: 0`
intact). 187 tests pass, 1 skipped (unaffected - this is CSS only). Re-ran the
generated-image usage audit while here: unchanged at 31 of 38 roles placed, and
directly HTTP-checked all 31 referenced files on the live site - all resolve.

**Impact.** Presentation and interaction only. No protocol, data, or result changes.

## D-036 - The hero showcases the box, not one profile's literal pull; more of the generated set placed

**Date:** 2026-09-11 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

Rish's instruction: stop tying the opener's six cards to whichever profile's LP output
happens to be loaded, and use six recipes that have real photographs and look appetizing
instead. The prompt for this was direct - a screenshot of "quick and elegant french toast"
sitting in the hero as a no-photo initial card, with the question "why don't you replace it
with one which actually has an image?"

**Why a plain swap wasn't the answer.** The hero's six cards were `solve(p.candidates, ...)`
for `state.profile` - literally the same computed function as the board further down. No
profile in the dataset resolves to 6/6 photographed picks while still showing the 86'd
refusal (checked against all ten: best is 5/6, twice). Swapping the default profile would
only relocate the placeholder to a different specific recipe, and the existing copy
explicitly says these six are "chosen for one real person" - untrue the moment the six are
picked for looking good rather than computed.

**What changed.** `viewDeck()` in `app.js` no longer calls `solve()`; it renders a fixed
`HERO_SHOWCASE` of six real, photographed candidates drawn from across the ten profiles'
own real candidate rows - real id, real name, real minutes, real band, real match score for
whoever it was scored against - picked for having an actual Food.com photograph and, after
looking at the actual images (not just judging by name), for looking like food someone would
want to eat: roasted garlic cream sauce, broccoli grape and chickpea salad, chicken taco
salad, yummy veggie or turkey chili, grilled corn and tomato salad, chorizo enchiladas: two
Quick, one Fast, two Moderate, one Long - close to the "at most three" spread without
claiming to demonstrate the rule, which is section 2's job.

Nothing about a real recipe or its photograph was invented; what changed is that these six
are curated for the opener rather than solved for a person. The copy was corrected to match:
the `.pnote` no longer claims the hero is "chosen for one real person" and instead points at
where that literal computation actually lives - the "pull" section further down, which still
runs `state.profile` through the real `solve()`, honest placeholder included when that is
genuinely what it computes. The `.deck-line` under the cards was reworded off "cards this
person has not already tried" (no longer true - there is no "this person" in the hero now)
to "cards in the box," using the same real catalogue count the figures block above it already
shows.

**Image-usage audit, asked for directly.** Grepped every `/img/gen/<role>` reference across
the three HTML pages, `style.css`, and `app.js` against the 38-role manifest: 29 placed, 9
not. Two of the nine had a genuine, specific anchor and were placed in this pass -
`prop-pencil` beside the working note's own sentence, "a card's match score - pencilled in
its corner -", on the programme screen; `prop-box-open` at the top of `/demo/`, pairing with
the closed `prop-box-full` already on the story's "Pull the six yourself" section (closed
box as the teaser, open box where you actually are). The remaining seven -
`ground-paper-wide` (a fourth ground with no fourth page to sit on), `prop-card-blank`,
`prop-card-ruled`, `prop-stack`, `tex-grain`, `tex-kraft`, `tex-linen` - stay out. Every
paper surface already carries `tex-cardstock`; stacking three more textures on top of it
would be the effect-stacking the design ceiling explicitly rules out, not a gap. 31 of 38 is
the honest number now, not "all of them."

**Verification.** 187 tests pass, 1 skipped - untouched by this, since nothing in
`tasks/`, `scripts/`, or the data pipeline changed. `node --check app.js` clean. Confirmed
in a real page load that `HERO_SHOWCASE`'s six ids resolve to their real photographs (no
404s, no wrong-dish substitution) and that the "pull" section's board is still built from
`state.profile`'s live `solve()`, unaffected by this change. The GSAP entrance and the
`contrast-over-media`/pixel-sampling work from D-035 were not re-run, because nothing that
would move their result changed - the six DOM elements are the same shape, same classes,
same score-chip and no-photo markup, only different underlying recipes.

**Not verified, and why.** Frame rate and the field's visual behaviour on a real phone -
unchanged from D-034/D-035, still the one thing only a device in the room can confirm. The
GSAP entrance timing itself was exercised via a forced tween-seek rather than watched play
out in real time, because this environment's browser pane does not advance `requestAnimationFrame`
reliably for a backgrounded tab - a known limitation (see `project_verify_390_needs_cdp`),
not something this change could have introduced or fixed.

**Impact.** Presentation only. No protocol value, run, metric, dataset, or claim about the
LP's actual output changes. The worked demonstration - the literal answer for one real
person, refusal included - still lives entirely in the "pull" section, unchanged.

---

## D-035 - Real bugs, real fixes, and the rest of the generated set actually used

**Date:** 2026-09-11 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

Rish's verdict on D-034: "not at all close to being done" - barely any of the forty
generated images were placed, and the box page's subheading was visibly misaligned. Both
true. This entry fixes what was actually wrong, including two defects D-034's own
verification missed.

**The box-head bug, and why it was missed.** `.box-head{padding:2.6rem 0 1.4rem}` is a
shorthand on the *same element* as `.wrap{padding-inline:var(--gutter)}` - the `0` for
left/right in the shorthand silently zeroed the wrap's side gutters on every element
combined with `.box-head`. It is not new to this pass: it has existed since D-032. It
stayed invisible because the title is short centred text that never reaches the edge
regardless of padding; only a longer line - the count line - actually touches the zeroed
edge, and D-034 lengthened that line ("cards profile-0005 has not tried...") without
anyone scrolling to the box page at native width to look. Fixed by switching to
`padding-block`, which cannot collide with `padding-inline` on the same element.

**A second, worse regression, found while fixing the first.** D-034's cleanup regex for
the retired hand-of-cards CSS block was written to match "the deck (opener)" through "the
divider strip", and a `.deck-line`/`.countline` rule that had been added in between (in
D-033, for the box's own count line) sat inside that span and was deleted along with the
code it was meant to remove. The count line was left with almost no styling of its own,
inheriting only a colour rule from an unrelated compound selector - which is what made the
alignment bug look worse than one bad property. Restored as one rule, with the alignment
fix folded in from the start (`margin: 0 auto`, not `0`).

**A syntax-check that was never checking anything.** Every "`node --check opener.js && echo
ok`" run this session, across both D-034 and the start of this pass, returned success
regardless of the file's actual content - confirmed by appending literal garbage
(`***invalid $$$ ((`) to the file and getting the same silent success. `opener.js` and
`field.js` both use `import`/`export`; `node --check` on a bare `.js` file assumes
CommonJS, and rather than erroring on the module syntax it appears to abandon validation
of the rest of the file. `node --input-type=module --check < file` is the correct
invocation for these two; `flight.js`, `app.js` and `viz.js` are true classic scripts and
plain `node --check` genuinely validates them, as it always claimed to. Re-running the
correct check against opener.js found a real syntax error, introduced by this pass's own
first attempt at a fix (a multi-line comment where only the first line carried `//`) -
fixed, then re-verified with the correct command.

**The title's contrast was not guaranteed, and failed under real measurement.**
`contrast-over-media` (which D-034's report ran and called passing) failed the opener's
h1 on a repeat run at 1440px - 2.93:1 against a floor of 3, worst pixel 1.53:1 - because
the shader's own lower-third dimming is a function of screen position only; the field's
drift, the pointer-eased light position and the scroll-tied zoom all move what is actually
behind the text at any instant, and the one capture D-034 quoted happened to land on a
dark frame. A `text-shadow` was added first and did not fully close it; the real fix is a
CSS-level scrim (`.opener::after`, a fixed dark gradient sitting between the canvas and
the content layer, independent of anything the shader computes) that guarantees the
result regardless of the field's state. Re-run five times after, at three widths: the
title has not failed once since.

**A real accessibility question, resolved by removing an effect rather than tuning it.**
The four outer cards in the opener's fan carried `opacity: 0.82` for a depth illusion.
Opacity on a parent compounds with every descendant's own paint, including a child that
believes itself opaque, so this measurably thinned the score badges and no-photo
initials on exactly those four cards. Removed: every card now renders at full opacity,
and the depth cue is carried by size alone (`cells()`'s existing width curve), which
does not have this failure mode. This did not turn out to be the cause of the score-badge
readings `contrast-over-media` still reports (below) - it is kept anyway, on its own
merits, since a UI element should not become less accessible as a side effect of an
unrelated depth cue.

**The score-badge and card-initial "failures" are a tool artifact, and this time it is
proven rather than assumed.** After every fix above, `contrast-over-media` still reports
low ratios for the "89%"/"90%" score chips and the no-photo cards' "Q"/"FAST". Rather than
recording that as a known limitation the way the D-034 report did, the actual composited
pixel was sampled directly from a real screenshot at the score chip's own reported
bounding rect: `rgb(251,245,234)` under the digits, `rgb(135,129,123)` on the glyphs -
`--paper` and a value close to `--pencil`, exactly as declared, and unambiguously high
contrast. The tool's sample does not correspond to what is on screen.

**Eight more of the forty generated roles, each doing one job.** Real cardstock texture
(multiply-blended, low enough to leave every declared colour and contrast ratio
unchanged) on every paper surface, replacing flat token colour with the actual material.
A photographed receipt strip behind the bill. The brass label holder framing "Whose box".
A paperclip on the pending block - Khushi's introduction is, literally, a note clipped to
the page. The physical stamp beside its own impression on a full divider row. The four
divider tabs as photographed cards, illustrating "the rule" screen's own paragraph about
them. A fanned fifty-odd-card stack opening the try page. None of the 40 roles is used
decoratively; each is named to the sentence or the concept it illustrates. 17 of 40 roles
are now placed (up from 9); the remainder (extra grounds, the raw card-blank/ruled props,
the box-open state, the pencil, the stack) are catalogued in `img/gen/manifest.json` and
left for a future pass rather than forced in.

**Verification, quoted.** Zero console errors, zero horizontal overflow, zero broken
images on all three pages at 1440 and a true 390 - checked after every fix in this entry,
not once at the end. The opener's title verified clean across five repeated
`contrast-over-media` runs. Reduced motion: 0 animations, opacity 1, transform none,
counts final, field renders its still frame. 187 tests pass, 1 skipped.

**Not verified, and why.** Frame rate on a real phone, unchanged from D-034 - still the
one thing only a device in the room can confirm. The remaining 23 unused generated roles
have not been placed; that is a scope decision, not an unverified claim.

**Impact.** Presentation and one real code-quality finding (the syntax-check gap) worth
carrying forward to any future JS module added to this project: check module files with
`node --input-type=module --check < file`, not the bare form. No protocol value, run,
metric or claim changes.

## D-034 - The archive at night: the ceiling pass, with two engines and generated atmosphere

**Date:** 2026-09-11 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish (scope, engines and imagery approved 2026-09-10)

Both pages and the try page are recomposed to a new register while the vocabulary of
D-029 (cards, dividers, the box, pulled, put back, 86'd) stays exactly as it is in the
paper, the deck and Khushi's script. Two engines are vendored under `/assets/` and a set
of generated images is introduced under a strict rule about what may be generated.

**Why.** Rish's brief: "an Awwwards-winning experience... pushed to the absolute limits of
design," measured against his own six reference sites (phantom.land, fantasy.co, k95.it,
cipher.tv, rejouice.com, lusion.co). Those six agree on four things the D-032 pages did
not do: full-bleed (6/6), a dark or mid ground (6/6), a luminance range above 0.45 (6/6,
median 0.849), and an artefact that is a canvas or an image rather than type (6/6). The
opener was a contained 1240px column of photographs on a dark block; the rest was paper.

**The register.** The table at night. A generated lamp-lit table sits fixed under every
page (`.ground`); everything made of paper - cards, the board's rows, the working sheets,
the sheets that open over the box - stays paper and resets a small set of surface tokens
(`--fg`, `--fg-2`, `--fg-muted`, `--rule`, `--link`), so a component never has to know
which ground it is on. The opener is full-bleed: the field runtime (`field.js`, vendored
from the framework, one local export added) lights and slowly moves into a generated still
of index cards receding into the dark, and the six real, photographed cards sit on the
runtime's plate positions in front of it. The title is a thin layer over the dark lower
third. Measured on the first screen at 1440: luminance spread **0.867** (D-032: 0.387);
the box **0.925**; try **0.846**. The phone opener sits at 0.395 - the tall still's lit
area is above the six cards - and is the one number below the bar, accepted for now.

**Engines.** Three owners, disjoint, written in `docs/MOTION_SPEC.md` before any motion
was implemented: `field.js` owns the canvas uniforms; **GSAP 3.15** (vendored,
`ScrollTrigger` included, licence note beside it) owns `transform`/`opacity` on the six
pulled cards and, on the story only, on the board's chips as they are dealt in scrubbed
by the page; WAAPI keeps the board's FLIP on slider input, the path draws and the
`data-count` counts. CSS keeps colour, border, shadow and the hover lift. `[data-flight]`
carries the same transition-property guard as `[data-anim]`. **This supersedes D-025's
refusal of a library:** the reason is the scrubbed, reversible flight of the six onto the
board, which WAAPI cannot express as a single progress value. GSAP's `matchMedia` gives a
phone the entrance without the flight and gives reduced motion nothing but the rest state.
The first procedural attempt at the field - rows of cards drawn in GLSL - was tried,
captured, and replaced by the generated still because the still was better; the shader
now does light, breath and the pull rather than drawing cards.

**Generated imagery.** Rish generated 50 images in ChatGPT (GPT Image, 2.0 by the files'
own provenance) from `IMAGE_HANDOFF_FOR_CHATGPT.md`; ChatGPT's own QA report accompanies
them. The rule, taken from the framework's generative standard: generation only where the
image is an invention - atmosphere, a category scene, a prop, a texture. **No generated
image ever stands in for a recipe.** The four CC-BY divider photographs are replaced by
generated category scenes (a toaster, a pan, a tray, a pot) because a category is not a
data record and the previous photographs were of dishes not in the study at all. 40 roles
are converted to responsive WebP under `site/img/gen/` with a `manifest.json` carrying
source file, prompt and model; the colophon credits them as generated and says none
depicts a recipe. The four stock photographs remain in the repository but are no longer
referenced; the credits list only what a page shows. The tick (C16) is unused - the site's
tick is drawn SVG.

**Verification, quoted.** Zero console errors and zero horizontal overflow on all three
pages at 1440 and a true 390; zero broken images; the six cards land on the plates
(measured rects: x 75-1190, y 252-293 at 1440); the entrance runs; the still cover-fits
after correcting for the runtime's inverted aspect uniform on portrait canvases.
`contrast-over-media` on the story: every heading, figure and control over the field or
the table passes (title 4.63:1 at floor 3; body labels 6-8:1). Its remaining flags are the
score chips on the cards: the tool samples the photograph behind the chip and cannot see
the chip's own opaque paper - the real ratio is pencil on paper, above 7:1 - so those are
recorded as false positives; the initial and band label on a no-photograph card were real
flags and are hardened. 187 tests pass, 1 skipped.

**Not verified, and why.** Frame rate on a real mid-range phone in a classroom: the
runtime governs resolution by measured frame time and caps DPR at 1.0 there, but only a
device can confirm it. The GSAP flight was verified in a headless browser by scrolling to
the board, not with a pointer on a real screen. Hover reveals are unchanged from D-032.

**Impact.** Presentation only. No protocol value, run, metric or claim changes. New:
`site/assets/field.js`, `opener.js`, `flight.js`, `vendor/gsap.min.js`,
`vendor/ScrollTrigger.min.js`, `vendor/LICENSE-gsap.txt`, `site/img/gen/*`,
`docs/MOTION_SPEC.md`. `DESIGN.md` records the register, the engine map and the imagery
rule.

## D-033 - Try it yourself becomes its own page, the phone becomes a first-class surface

**Date:** 2026-09-10 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

Three changes, all presentation: a standalone `/try/` page, a real mobile pass on both
existing pages, and a designed state for recipes that have no photograph.

**Why.** Khushi will ask a classroom to open the demonstration on their own phones. Rish's
verdict on the current build: the site "is not optimized for the phone at all", and the
three-round demonstration "feels incomplete... like a three step demo which has no real
value behind it".

**The phone.** The header collapsed into a ragged block of raw text links; both are now a
single scrollable row of tappable pills. The board wasted most of a phone screen on empty
slots - an empty slot is now a 10px hairline, so all four dividers, the six cards and the
86'd stamp fit in roughly one and a half screens instead of four (page height 3512px to
3022px, with far more of it carrying content). Sliders are full-width with larger values,
the two side links are real tap targets, sheets go full-bleed with a sticky header, and
`--screen-y` drops from 6rem to 3.6rem at the small end. Two CSS blocks were moved to the
end of the sheet because base component rules declared later were winning on equal
specificity - the reason is written above them.

**`/try/`.** Its own URL, printable and typeable: `handful.netlify.app/try`. An opening
screen that says what will happen and how long it takes, three rounds with a progress
indicator, and a result screen that shows the visitor's own three times before explaining
why one person's times are not evidence. **The round order is now shuffled per visitor**,
which removes the warm-up flaw a fixed order guaranteed; the debrief was rewritten to say
so rather than continuing to list it as a defect. The long round now shows a shuffled 60
rather than the top 60 by our own score. `/demo/#try` redirects here, so the URL already
printed in the handover still works.

**Recording.** Each completed run posts one anonymous row through Netlify Forms - a
same-origin POST, no database, no third party, exported as CSV from the Netlify dashboard.
The row holds the three times, which card was picked in each round, the shuffled order, the
profile, viewport size and a random per-tab session string. No name, no login, no
identifier that outlives the tab. The intro screen states plainly that this is recorded and
that nothing identifies the visitor.

**On what that data is and is not.** It is not part of this study and cannot enter the
validation paper: these are classmates in a room, not a recruited, randomised, consented
sample. It exists so a future study - properly approved - has a working instrument and a
sense of what the numbers look like. Rish's instruction was to collect without a consent
gate; the notice is one line on a screen the visitor is already reading, not a gate, and it
is what keeps the data usable for that future study at all.

**Photographs.** Confirmed by fetching the pages directly: Food.com genuinely has no
photograph for 206 of the 209 recipes the fetcher could not resolve (the remaining 3 are
dead pages). Their pages carry only the site's generic share graphic. Nothing further can
be scraped. Stock photography beside a real recipe name was considered and refused again -
it would contradict D-027 and the paper's own statement about image provenance. Instead the
no-photograph card is now designed: the recipe's own initial set large on its divider's
colour, over the hatch, with a title attribute saying that Food.com has no photograph for
it. 261 of the 470 recipes in the extract have real photographs; the other 209 now look
deliberate rather than broken.

**Impact.** Presentation and one new page. No protocol value, run, metric or claim changes.

## D-032 - One artefact per screen; the rigour one layer down

**Date:** 2026-09-09 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

Both pages are recomposed. Each screen of the story is one artefact and one sentence, with
everything that explains it directly beneath under a quiet "The working" disclosure that
opens in place; presenter mode opens every working at once. The box's board becomes the
page itself, with the two sliders above it and the other views opening as sheets over it.
The direction (the recipe card index, D-029) does not change; the composition does.

**Why.** Rish's verdict on the D-029 pages: "not where I want it to be" - the goal is
"clean, minimal, well structured, well spaced out, pleasing to look at, not cluttered",
and, when pressed for a designer's answer rather than a menu of options, the diagnosis was
that both pages were documents wearing a design: four or five things on every screen, the
metaphor applied as texture rather than structure, evenly medium spacing, and the demo laid
out as an admin dashboard (sidebar, tab row, content well). The second constraint, stated
by Rish in the same breath, was that the pages stay educationally valid. Layering is the
reconciliation: a textbook page has one figure and one sentence at the top and the
derivation below it. Nothing is deleted; it is ordered.

**What changed.**

- The story: ten sections become nine screens plus a one-line status: the opener (dark: the
  title, then the six pulled cards held as a hand of cards, the box count as one line -
  Rish's one correction to the first cut, which had a wide count tin over a row of six), the rule (one photograph strip with the four
  dividers and their caps), the pull (the board for the worked person with the stamped
  card), the programme, the graphical method, duality (dark: the certificate as one line),
  the result (the interval plot alone), the box (the button), limits (one line). Every
  paragraph, list, table, credit and licence note that used to sit on the page is under the
  relevant working. Speaker notes unchanged, one per screen.
- The box: no sidebar, no tabs. The board fills the page; the sliders sit above it with
  large values; *Four ways*, *How it's solved*, *Try it* and *their cards* open over the
  board and close back to it; `/demo/#<view>` still opens one directly. Raw variables sit
  at the end of How it's solved. The box count is a line, not a tin.
- Chips: photograph, name, score; minutes and divider on hover. Red rules off every card;
  the 86'D stamp is the only red. Empty slots fade to 40%.
- Type: display up to 104px at −0.05em; body 18px; the sentence on each screen at up to
  58px. Chapter fade-ins removed; the pull is the only entrance motion.
- Chrome: wordmark plus one floating pill on the story; the box's header carries the three
  view links and a way back.
- `viewLpp`, `viewDual`, `viewEvidence` and `viewShortlist` take an optional `working`
  sink; `certLine` replaces the three certificate boxes; `mount(id)` fills `#<id>` with the
  artefact and `#<id>-working` with the rest; sheets replace `VIEWS` tabs.

**Verification, quoted.** Zero console errors, zero horizontal overflow, zero running
animations after settle and zero broken images on both pages at 1440 and a true 390 (CDP
emulation); all four sheets open from a hash with content and close cleanly; presenter
mode opens 7/7 workings and shows the first note; the pill appears past the fold.
`tools/palette.py` on the first screens: story 1440 luminance 0.135, spread **0.841**, ink
16.4% (a dark opener, matching the reference set's 6/6 dark-or-mid ground and >0.45
range); story 390 spread 0.417; the box 1440 spread 0.151, ink 2.0% - the tool page is
paper, and is allowed to be. 187 tests pass, 1 skipped.

**Not verified, and why.** Hover states and the slider's FLIP re-slotting were exercised in
a browser earlier in the pass, not captured headless (no pointer). The fonts are still
served from Google Fonts.

**Impact.** Presentation only. No protocol value, run, metric or claim changes. The
explanation sheet and the handover's `07_DEMO_GUIDE.md` are rewritten for screens and
sheets rather than chapters and tabs. `DESIGN.md` gains a Composition section; D-029's
direction and engine map stand.

## D-031 - The Results Pack's Tables 1-3 were always PENDING; fixed at the source

**Date:** 2026-09-09 · **Owner:** Rish (implementation) · **Status:** approved

`docs/RESULTS_PACK.md` (and its handover copy, `05_RESULTS_PACK.md`) marked Tables
1-3 (raw dataset audit, cleaning ledger, split and eligibility) as PENDING even though the
audit, clean and splits stages had all completed. This was not stale documentation - it was
a bug in `build_results_pack`: it looked for `t01_raw_dataset_audit.csv`,
`t02_cleaning_exclusion_ledger.csv` and `t03_split_and_eligibility.csv` inside the
validation/final run's own `tables/` directory, but those three tables are produced by the
audit, clean and splits stages, each its own timestamped run directory. They would have
read PENDING regardless of whether every upstream stage had actually finished.

**Why it matters.** `04_CALCULATIONS_WORKED.md` separately cited the real numbers (231,637
raw recipes, 230,541 cleaned, 20,389 validation-eligible users) sourced correctly from the
run directories and from `docs/DATA_AUDIT.md`. That created an apparent contradiction
between two handover files describing the same pipeline stage - one said PENDING, the
other quoted the finished result - which was not a question of which file to trust; both
were reporting the truth as each script understood it, and the Results Pack's script was
wrong.

**Fix.** `src/foodcom/reporting/results_pack.py` now resolves the most recently completed
audit/clean/splits run no later than the consuming run's own start time
(`_latest_stage_run`), falls back to it only when the table is not already present beside
the run it was given, and prints which run each table actually came from when that differs
from the main run id. Regenerated: `docs/RESULTS_PACK.md` now shows Table 1 from
`audit-20260906T164448Z-4c524298`, Table 2 from `clean-20260906T165026Z-269a4986`, and
Table 3 from `splits-20260906T165247Z-781726a4` - all three matching `04_CALCULATIONS_
WORKED.md` and `10_DATA_AUDIT.md` exactly. The handover copy is re-synced.

**Impact.** Reporting only. No protocol value, run, metric or claim changes; nothing here
touches `assets/data.json`, the site, or any evaluated number. 187 tests pass, 1 skipped.

## D-030 - The original-plan-vs-built story comes off the public pages

**Date:** 2026-09-08 · **Owner:** Rish (decision) · **Status:** approved by Rish

The story page's "The gap" chapter - "what we pictured" vs "what we built," the four-day
window, the lack of recruited participants - is removed from `site/index.html`. The
few other places that named the same constraint (the problem chapter's pointer to "Try it
yourself," the "where it stands" future-work item, and the demo's "why this is a demo and
not research" banner in `app.js`) are reworded to drop the internal reasoning while keeping
every truth-constraint disclosure (no participant recruited, no survey run, what a live
study would still need) intact.

**Why.** Rish's instruction: the internal planning history - the deadline, the access
problem, what was originally pictured - is his and Khushi's business, not the audience's.
It belongs in the paper's methodology section and in this project's own internal record
(this log, `DESIGN.md`'s history, the handover package Khushi uses to write that section),
not read aloud from a public page or spoken in presenter mode to a classroom. Removing it
does not touch any truth constraint: the page still states plainly, in the limits chapter
and in the "Try it yourself" banner, that no participant was recruited, no survey was run,
and choice overload was never measured - it simply no longer explains *why* the study
took this shape instead of the one first pictured.

**Impact.** Presentation only. `DESIGN.md`'s chapter table drops "The gap" row to match the
built page (now seven chapters, not eight). No protocol value, run, metric or claim
changes. The handover package (`04_CALCULATIONS_WORKED.md`, `08_LIMITATIONS.md`,
`01_WHAT_CHANGED_AND_WHY.md`) is unaffected and keeps the full constraint history - Khushi
needs it to write the paper's own limitations and methodology sections, which is a
different audience and a different disclosure obligation than a live public page.

## D-029 - The ceiling pass: the direction is rolled, not chosen, and the pages are rebuilt on it

**Date:** 2026-09-08 · **Owner:** Rish (work order), implementation by Rish · **Status:** approved by the work order

Both pages are rebuilt under `reidify-design-authority` to a direction chosen by
candidate-and-roll rather than by preference. The direction is **the recipe card index**:
seed `e824c2b`, `0xe824c2b mod 7 = 5`, ordinal 6 of 7. The contract is a comment in both
pages' markup. `DESIGN.md` is rewritten as-built with the rejected draft, the seven
candidates, the tokens, the type ramp, MotionSpec v1 and the engine map.

**Why.** Rish's verdict on the D-028 pages was that they felt cramped, under-photographed
and short of a narrative; the demo still explained itself with paragraphs; and the Cookbook
direction of D-027 had been picked by preference, which the authority's bootstrap does not
allow for a direction. The work order (Mode A on the design, Mode B on the repository)
asked for the roll, a chapter structure, a motion thesis written before implementation, a
type ramp, and a demo a stats student can read by looking.

**What changed.**

- The direction: card stock, a red header rule and blue body rules as material, coloured
  divider tabs as the band scale, typewriter ink for what was typed on the cards, a dark
  tin for the box count. Every word on the pages ("card", "divider", "the box", "pulled",
  "put back", "86'D") is the diagram's own word.
- The chapters: the story reads as eight dividers with tabs (opening, the problem, the gap,
  the method, the result, the box, limits, where it stands); the demo is "The box" with
  six tabs renamed to the metaphor - *The six*, *Try it yourself*, *Four ways to pull*,
  *Their cards*, *How it's solved*, *Raw variables*. Presenter notes are untouched.
- The motion thesis: one signature moment, the pull (six cards rising out of the box,
  640ms, staggered), and its small form on every slider move (FLIP re-slotting, the 86'D
  stamp). Supporting motion carries one fact each. Reduced motion is a branch. Recorded as
  MotionSpec v1 in `DESIGN.md` before the pull was implemented.
- The type ramp: Newsreader for the printed face, Inter for the interface, Courier Prime
  for what was typed; display 76px tracking -0.045em, body 17px, 6.3x; running measure
  capped at 52ch, which is 70 characters in Inter (62ch had measured 85).
- The band scale re-stepped as a single-hue ordinal ramp and passed through the `dataviz`
  validator; the amber-to-rust ramp of D-025 failed it and is superseded.
- The demo explains itself by artefact: the board, the landscape, the colour strips with a
  swatch key, the history bars, the certificate and the bill. Where a paragraph had been
  doing that job (the compare tab's "coloured by divider" sentence) it is replaced by the
  thing itself; the one sentence left under each view names the state, not the encoding.
- A dark box-count strip on the demo so its first screen has range (luminance spread
  0.717, from 0.211).
- 390px was finally verified for real. Both the browser pane and headless Edge clamp the
  window to ~588px and crop the capture, so every earlier "390" check was a 588 layout. A
  CDP script (`Emulation.setDeviceMetricsOverride`) gives a true 390 and exposed four
  overflows: collapsed grids using `1fr` (which is `minmax(auto,1fr)`), the profile
  `<select>` sizing to its longest option, the box-count number, and the menu-card title.
  All fixed; both pages now measure `scrollWidth == 390`.

**Verification, quoted.** Craft floor at 1440/1280/390: lowest text contrast 5.2:1
(`--muted` on paper), body ink above 13:1; measure 70 characters in `.prose` at 1280 and
1440, 43 at 390; display 76px / label 12px = 6.3x; tracking -3.42px at 76px = -0.045em.
`tools/palette.py` on the first screens: home 1440 spread 0.737, ink 13.1%; demo 1440
spread 0.717, ink 7.2%; home 390 spread 0.593, ink 11.1%; demo 390 spread 0.354, ink 6.9%.
Zero console errors on both pages; zero horizontal overflow at all three widths; zero
`Animation` objects `running` after settle; zero broken images (14 on the story, 5 on the
demo at load). Reduced motion emulated: 0 animations, opacity 1, transform none.
`impeccable`'s detector on the stylesheet reported nothing; no disagreement to record.
`contrast-over-media.mjs` was not run because no text sits over an image.

**Not verified, and why.** The candidate list in `DESIGN.md` was reconstructed after a
context reset mid-pass; the roll, its seed and its result are recorded in the pages
themselves and are not in doubt, the ordering of the six other candidates is from memory.
The fonts are still served from Google Fonts. Hover states were exercised in a browser at
1280 but not captured headless, because a headless capture has no pointer.

**Impact.** Presentation only. No protocol value, no run, no metric and no claim changes;
`assets/data.json` and its contract with `scripts/export_demo.py` are untouched. The
explanation sheet and the handover package's demo guide are updated to the final tab and
chapter names. D-027's direction record is superseded; D-025's engine rule and D-028's
two-page split stand.

## D-028 - The story and the demo are two pages again

**Date:** 2026-09-08 · **Owner:** Rish (decision) · **Status:** approved by Rish

The single page from D-027 splits: the story stays at `/`, and the interactive demo returns
to `/demo/` as a standalone page. The story's fifth course becomes a demo section - a preview
card of the six picks and a call to action that opens the demo.

**Why.** Rish's verdict on the D-027 page was that it "feels too cluttered." He is right
about the cause: one page was trying to be both a narrative that is read and a tool that is
operated. The sticky control panel, the embedded "Try it yourself," and the full board,
landscape and funnel stack are what a presenter operates, and on a page meant to be read they
compete with the argument. Khushi's ask on the 8 September call was a seamless flow without
tab-switching *between a landing page and a demo she had to hunt for*; a clear hand-off from
the story to a demo page on the same site satisfies that without the weight.

**What each page carries.**

- `/` - hero, the problem (the four courses, with a pointer to Try it yourself), the gap, the
  method (the three lenses and the bill at the protocol defaults, with a person picker and no
  sliders), the result, the demo section, limits, status. Presenter mode stays here.
- `/demo/` - sticky controls (person, how many, max per course) and six tabs: Their picks,
  Try it yourself, Compare approaches, What they've liked, How it's solved (the three lenses
  driven by the sliders), The raw variables. A story link can open a named tab
  (`/demo/#try`, `/demo/#solved`).

One stylesheet (`assets/style.css`) and one script serve both, so the two pages cannot drift
apart visually or in what they compute. The D-027 redirects are removed; `/demo/` is a real
page again and keeps its `noindex` from D-021.

**Impact.** None on the research. No number, claim or data path changes. The explanation
sheet and the handover demo guide are updated to the two URLs.

## D-027 - One page, a cookbook direction, and photographs

**Date:** 2026-09-08 · **Owner:** Rish (decision), implementation by Rish · **Status:** approved by Rish

The project page and the demo become one page. The visual direction changes to a cookbook
with menu elements. Photographs are introduced under a strict sourcing rule.

**Why.** On the 8 September call Khushi, who presents this, asked for four things: colour and
food, no tab-switching between a landing page and a demo, a narrative order (intro, methods,
results, demo), and her own calculations shown on screen. She also said the current page
"feels very boring." The existing project page was, separately, out of date: it still stated
that no results existed and that the demo could only run locally, both false since 7 September.

Three directions were offered and Rish chose: **the Cookbook, with Menu elements integrated
where they explain something.** Recorded in `DESIGN.md`.

**On the single page.** `/demo/` is retired in favour of `/#demo`; the old URL redirects (301)
because it is printed in documents already handed to Khushi. The demo's scripts and data
extract move to `/assets/`. The root page's Content-Security-Policy changes from
`script-src 'none'` to `script-src 'self'` with `connect-src 'self'`, approved by Rish; no
third-party script or outbound connection is admitted. The data extract gets its own
`X-Robots-Tag: noindex` because D-021's licence position has not changed.

**On photographs.** Two sources, kept apart:

1. *Per-recipe.* The dataset has no images. A stock photograph of some other dish beside a
   real recipe name would be a fabricated visual claim, which the truth constraints forbid.
   The only honest per-recipe image is the one Food.com publishes for that recipe id. Rish
   accepted the terms-of-service risk of fetching those and chose to proceed. The fetch is
   limited to the ~470 recipes the demo can show, at 480px, once, at 1.2 s intervals, and the
   files are self-hosted with a "Photo: Food.com" credit. Where a fetch fails the card shows
   no photograph; nothing is substituted.
2. *Ambience.* Openly licensed (`by`/`cc0`) photographs from Openverse for the hero, section
   openers and one illustration per preparation-time band. Every one is credited by creator
   and licence on the page. They are never placed beside a specific recipe.

**Rejected.** Hotlinking (blocked by CSP and fragile). Stock images beside recipe names
(dishonest). Generated food imagery (same problem, plus a generative standard this project has
no need to take on).

**Impact.** None on the research. No pipeline file, protocol parameter, metric, population or
claim is touched; `data.json` is unchanged and moves path only. The six demo views keep their
content. The explanation sheet and the handover package's demo guide will need their URLs and
"six tabs" wording updated once the page ships; noted in `TASK_STATUS.md`.

## D-026 - The demo shows the experiment we could not run, and labels it as a demonstration

**Date:** 2026-09-08 · **Owner:** Rish (implementation) · **Status:** approved by Rish

`site/demo/` gains a "Try it yourself" tab. It runs the original study design - show a menu,
time the choice, compare a long menu against two six-item shortlists - on whoever is looking
at the screen.

**Why.** The project was originally conceived as a human timing experiment: present a menu,
measure how long a person takes to choose, and compare that against a random shortlist and
an optimised one. It became an offline retrieval study for two reasons only: a four-day
window, and no access to recruited participants. The Release 2.0 handoff spec was rewritten
around those constraints and, correctly, forbade surveys, participants and decision timers.

The cost of that rewrite was that the finished demo no longer resembles the question the
project is named after, and a reader who does not already know this will assume the study
measured choosing speed. It did not, and cannot. Explaining that in prose had already been
tried - it is in `LIMITATIONS.md`, in the Results Pack, on the evidence tab and in the
explanation sheet - and a reader still has to take it on trust.

Letting someone feel the difference between sixty options and six, and then telling them
directly that feeling it is not evidence, teaches the limitation better than another
disclaiming paragraph. It also gives Khushi and a classroom the original idea in thirty
seconds rather than a description of it.

**On the deviation.** The spec says "no decision timers" and "this demo collects nothing."
The second still holds absolutely: the timer runs in the visitor's browser, the result is
rendered to them, and nothing is stored, transmitted or exported. No value from it can reach
`data.json`, a run directory, the Results Pack or the paper.

The first is a deliberate, recorded deviation. The spec's ban existed to stop a timer being
used to manufacture participant data or imply a measured outcome. This does the opposite: the
debrief screen names four reasons the number is worthless as evidence - one self-selected
person, who knows what is being tested, in a fixed unrandomised order, with nothing recorded
- and states that a real version needs recruited participants, randomisation, consent and
ethics approval.

**Rejected alternative.** Simulating or generating plausible participant times. That would be
fabricated research data, which the spec forbids outright and which no framing could make
acceptable.

**Impact.** None on the research. No pipeline file, protocol parameter, metric, population or
claim is touched. `data.json` is unchanged and `protocol_version` is not bumped. The tab is
additive; the existing five tabs keep their names, order and content.

## D-025 - The demo becomes a visual instrument, and the engine rule changes with it

> **Engine refusal superseded by D-034 (2026-09-11):** GSAP is vendored for the scrubbed flight of the six cards, and field.js for the opener's canvas. The reduced-motion branch and the one-owner-per-property rule from this entry stand.

**Date:** 2026-09-07 · **Owner:** Rish (implementation) · **Status:** approved

`site/demo/` gains authored diagrams, a band data-scale and motion. `DESIGN.md`'s engine
rule moves from "CSS, exclusively" to "CSS plus the Web Animations API, with disjoint
property ownership."

**Why.** The demo is presented live to a classroom that has not read the paper. Its job is
to make the *mechanism* legible in the seconds someone is looking at it, and a table of
numbers does not do that. The specific thing worth seeing - a high-scoring recipe being
refused because its preparation-time band is already full - was, until now, only inferable
by comparing two tables before and after moving a slider. It is the research contribution,
and it was the one thing the page did not show.

The alternative was to leave the demo as a set of tables and explain the mechanism verbally.
That puts the entire burden on the presenter and loses the audience that stops reading.

**On the engine.** No animation library is added. The Web Animations API is native to the
browser, so the page keeps its zero-dependency, nothing-fetched, nothing-sent property -
which is a research claim on this page, not a preference. Ownership is recorded in
`DESIGN.md` and is disjoint by construction: WAAPI owns `transform` and `opacity` on any
element carrying `data-anim`, and CSS transitions never name those two properties on such an
element. GSAP and Motion were considered and refused: neither earns a dependency here.

**On the band colour scale.** Four preparation-time bands gain a sequential amber-to-rust
ramp. This is a data encoding, not a second accent - the bands are an ordered variable and
the ramp encodes that order. Blue remains the only accent and continues to mean the proposed
method, a live value, or a link. Band colour is never used to set text.

**Impact.** None on the research. No pipeline file, protocol parameter, metric, population
or claim is touched; `data.json` and its contract with `scripts/export_demo.py` are
unchanged, and every number rendered still comes from the export. `protocol_version` is not
bumped, because nothing methodological moved. The five tab names are deliberately unchanged:
they are documented in the explanation sheet already handed to Khushi.

**Superseded.** `DESIGN.md`'s "Engine owner: CSS, exclusively" line, and its truth-constraint
note that no recipe, score or result exists yet - results now exist and are rendered from the
validation run.

## D-024 - Optimality proved by dual certificate, not by the unpruned simplex

**Date:** 2026-09-07 · **Owner:** Rish (implementation)

A worked-example run sat for six hours at 0.04 cores and had to be killed. Measured
afterwards, on the real problem and on a synthetic one of identical shape:

| step | time |
|---|---|
| primal, pruned | 0.92 s |
| certified dual | 0.22 s |
| primal, **unpruned** | >280 s, returns `success=False` |

This is a HiGHS limitation at 229,279 columns against 5 rows, not a property of our data.
`highs-ds` simply does not converge on that shape.

**What changed.** The pipeline no longer asks the full simplex to converge. Optimality on
the FULL problem is established the way linear-programming duality is meant to establish
it: exhibit a primal-feasible `x*`, exhibit a dual-feasible `(alpha, beta, gamma)` that
satisfies every one of the n constraints, and show the objectives are equal. Weak duality
then proves `x*` optimal. That is a **stronger** statement than a solver run terminating,
and it is checked against all 229,279 constraints rather than asserted.

`certified_dual` obtains the dual cheaply by solving it on a top-(b_g + margin)-per-band
subproblem and extending gamma in closed form as `max(0, s_i - alpha - beta_g(i))`.

**My first version of this was wrong, and testing caught it.** Keeping only the top `b_g`
per band disagreed with the directly solved dual on **22 of 273** random problems, worst
gap 0.57. Dropping the `(b_g+1)`-th item removes the constraint that pins `alpha + beta_g`
from below, so the reduced dual picks them too small and the extension then forces positive
gamma onto excluded high scorers. At `b_g + 1` the disagreement is **0 of 273** with a
worst gap of exactly zero. The shipped margin is 2.

**Guard against silent failure.** Strong duality is still checked against the full primal
objective on every worked example. If the reduced `(alpha, beta)` were ever not optimal for
the full problem, the objectives would disagree and the check would fail loudly.

## D-023 - Post-hoc rank diagnostic, disclosed as post-hoc

**Date:** 2026-09-07 · **Owner:** Rish (implementation) · **Status:** disclosed, not a
protocol change

Validation returned **Recall@6 = 0.000 for three of the four methods** (AI_LP, AI_TOPK,
RANDOM); only POPULARITY_LP was non-zero at 0.0103. The primary metric therefore barely
discriminates on this task, which is itself worth stating.

`scripts/rank_diagnostic.py` reports the rank of each user's best true positive under each
scorer. On a 60-user probe: AI score median rank **54,052** of ~230,000, popularity
**5,355**, random ~115,000. The AI model is clearly doing something - roughly twice as good
as chance - and is just as clearly far too weak to land a hit in six slots.

**It was written after seeing the zero, and that is disclosed here rather than buried.**
Three things keep it honest:

1. **Recall@6 stays primary and NDCG@6 secondary**, unchanged in `config/research.yaml`,
   both reported exactly as computed. Nothing is swapped.
2. **It lives outside the pipeline.** Neither `tasks.py validate` nor `tasks.py final`
   calls it, and it cannot alter a number in the Results Pack. The separation is
   structural, not a footnote.
3. **It is descriptive, not inferential.** No test, no interval, no significance claim.

**Why it earns its place.** "Recall@6 was zero" and "the model is inert" are different
claims, and the first does not license the second. Reporting only the zero would leave
Khushi unable to say which one the evidence supports.

**What it still cannot support:** anything about choice overload, satisfaction, decision
speed or any human outcome. It is a ranking position.

## D-022 - Evaluate every eligible user, not a 5,000 sample

**Date:** 2026-09-06 · **Owner:** Rish (implementation) · **Status:** APPROVED - Khushi,
2026-09-11 ("Approved - use all eligible users for the 2018 final evaluation, no 5,000
cap. Go ahead and run it.", relayed by Rish the same day)

`protocol.max_users` changed from `5000` to `null`.

**Why.** The specification says "use all eligible users when feasible" and offers the
5,000-user seeded sample only "if compute requires a cap". Measured against the real data,
compute does not require it:

| stage | history-eligible | rankable, capped at 5,000 | rankable, uncapped |
|---|---|---|---|
| validation | 20,389 | 202 | **812** |
| final | 20,557 | 126 | **530** |

The cap was costing four fifths of the evaluated population. It looked cheap because the
cohort is large, but only *ranking-eligible* users are ever scored or solved, so the
uncapped run costs minutes rather than hours.

**Why it matters.** 126 users is a thin denominator for a paired bootstrap on the final
test set; the intervals would be wide enough to make almost any comparison inconclusive,
and that would be an artifact of the cap rather than a finding about the methods.

**Why the rankable cohort is small either way.** The label windows are single years, and
only 27,004 (2017) and 20,609 (2018) interaction events fall in them across the whole
dataset. Most warm users simply have no eligible novel positive in a given year. That is a
property of the data and is reported as a denominator, not corrected for.

**This does not touch** the eligibility rule, the positive-rating definition, the windows,
or anything else. It removes a sampling step the specification had already marked optional.

## D-021 - The dataset licence forbids redistribution

**Date:** 2026-09-06 · **Owner:** verified from source · **Status:** DECIDED by the licence,
not by us

The Kaggle dataset page states its licence as **"Data files (c) Original Authors"**, on
**Version 2** (892.41 MB, 8 files, last updated ~2019). That is Kaggle's most restrictive
standard label: it asserts copyright and grants no reuse or redistribution rights.

`licence_permits_redistribution` is therefore recorded as **false** - a verified fact, no
longer an unknown.

**What this permits.** Downloading and analysing the data locally, and publishing
aggregate results, counts, metrics and figures. That is the entire research project, and
none of it is affected.

**What this forbids.** Mirroring the files anywhere, committing them, and publicly serving
a substantial extract of the recipe data. Review text was already excluded from everything
outward-facing.

**The consequence for the live demo.** A public page carrying hundreds of real recipe rows
is a substantial extract, so the static demo cannot simply be published open to the web.
Three ways forward, in order of preference:

1. **Password-protect the page.** The Netlify account is on Pro, which supports it. A link
   plus a password given to the class is not open publication. Combine with (2).
2. **Keep the extract minimal.** Export only what the demo needs - roughly 8 profiles and
   their candidate sets, names and reported minutes only, no review text, no user ids. A
   few hundred rows shown for academic illustration is a far weaker claim than a mirror.
3. **Run it locally on the presenting machine.** Zero distribution, but no link.

**This is Rish and Khushi's call, and a supervisor is the right person to confirm it.**
Academic use in a classroom is close to the centre of what fair dealing is for, but that is
not a judgement this repository should make silently. What the repository does is record
the licence exactly as stated and refuse to assume permission.

**Resolved 2026-09-07 - Rish's explicit decision.** Site-wide password protection was set
(Netlify Pro API, password [redacted]) and verified live (unauthenticated request
returned 401). Discovered afterward: Netlify password protection is site-wide only on this
plan - there is no path-level scoping - so it also blocked the public project page at `/`,
which was intended to stay openly readable. Presented Rish with three options (split into
two sites, keep the whole site password-gated, or remove the password); Rish chose to
**remove the password and publish the demo fully in the open**, judging the minimal
anonymised extract (10 profiles, no user ids, no review text, no raw ratings - names,
minutes, bands and derived relevance scores only) an acceptable risk for a time-boxed
academic classroom demo. Password removed and confirmed (`has_password: false`, both
`/` and `/demo/` return 200 unauthenticated). This overrides the password-protection
recommendation above; the minimal-extract discipline in option 2 remains in force
regardless.

## D-018 - The project is named Handful

**Date:** 2026-09-06 · **Owner:** Rish (approved the name from a shortlist)

Repository `reidifydesign/handful` (private), project page `handful.netlify.app`.

**Why.** "A handful of recipes, not a thousand" is the product in one line, so the name
does the explaining. It was chosen over four academic-register candidates (Cuisson, Paring,
Winnow, Bandcap) because Rish wants the option of this becoming a real consumer app later,
and a method-name reads wrong on an app store.

**What the name deliberately avoids.** No claim. "Handful" describes the output - a small
number of recipes - and says nothing about overload, stress or improvement. A name like
ChoiceCure would contradict the discipline the whole project is built on, and would be a
liability in the viva.

**Known minor collision:** a US sports-bra brand uses the word. Nothing in food tech or in
the recommender-systems literature.

**Not renamed:** the Python package stays `foodcom`, and the local working directory keeps
its original name. Renaming the package would churn imports across ~40 files for no
functional gain, and renaming the directory would break the virtualenv's absolute paths.
Both are cosmetic and can be done later if wanted.

## D-019 - The demo cannot be hosted on Netlify

**Date:** 2026-09-06 · **Owner:** Rish (implementation) · **Status:** stated, not a blocker

Rish asked for a Netlify site "for the actual demo". That is not possible, for three
independent reasons, and the site ships as a project page instead.

1. **Technical.** The demo is a Streamlit application - a live Python server that solves a
   linear programme per request. Netlify serves static files and JS/Go serverless
   functions. There is no Python runtime that could run it.
2. **Data.** The demo reads processed Food.com data. None exists yet (Gate 1), and the
   licence has not been recorded, so redistribution permission is unknown and therefore
   treated as no.
3. **Specification.** Release 2.0 states that public deployment is not authorised and that
   access and data redistribution must be checked before sharing.

**What shipped instead:** `site/index.html`, a static page carrying the research question,
the method, the model diagram, the evidence boundaries and the current blocked status, with
instructions to run the demo locally. It contains no data and no results.

**If a hosted demo is wanted later**, it needs a platform with a Python runtime (Streamlit
Community Cloud, Fly.io, Render, a container host) *and* a resolved licence position on
serving Food.com-derived content. That is a separate decision, not a deployment detail.

## D-020 - The project page's design world is recorded

**Date:** 2026-09-06 · **Owner:** Rish (implementation)

`DESIGN.md` now exists at the project root. It records `project_mode: independent`, the
token set, the type rules and the truth constraints, so the visual system is not re-derived
from scratch each session. The system itself was not invented - it already existed in
`app/components/theme.py` and was made explicit.

**Reidify's own palette is explicitly excluded.** This is not a Reidify surface.

---

## Open - require approval before the final run

| # | Decision | Needs |
|---|---|---|
| **A-001** | The 2017/2018 temporal windows are workable against the downloaded data | The audit's coverage verdict, then Khushi |
| **A-002** | Positive = 4–5; rating 0 = unknown | Khushi (methodology) |
| **A-003** | Warm-user eligibility ≥ 5 distinct historical positives | Khushi (methodology) |
| **A-004** | `k = 6`, `b_g = 3`, four bands at 15/30/60 minutes | Khushi + instructor (syllabus fit) |
| **A-005** | Recall@6 primary, NDCG@6 secondary; no p-values | Khushi + instructor |
| **A-006** | The restricted continuous LP with duality as the OR content | Instructor (syllabus fit) |
| **A-007** | Whether formal significance tests are required | Instructor — must be specified **before** the final test set is touched |
| **A-008** | Redistribution of raw data or review text | The Kaggle licence wording; currently unknown, therefore **no** |

---

## Template for new entries

```
## D-0NN — <short title>

**Date:** YYYY-MM-DD · **Owner:** <who> · **Status:** <approved / PENDING — who>

What changed, in one sentence.

**Why.** The reason, including what the alternative would have done.

**Impact.** Which runs, populations or numbers this affects. If it changes data identity,
cleaning, the split, the population, the model, a metric or a claim, bump
`protocol_version` and list the superseded run ids.
```
