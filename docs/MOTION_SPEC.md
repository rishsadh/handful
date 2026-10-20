# MotionSpec v1 — Handful, the archive at night (D-034)

Written before any motion code, as the authority requires. The personality is taken from
the evidence in `DESIGN.md` (the recipe card index; one warm light; cards with weight), not
from habit.

**Superseded in part by D-039 (2026-09-11):** the opener no longer carries six cards of its
own. The hero's six-card fan implied six *specific* things before any specific thing was
true - the actual six, computed for a real person, appear for the first time in "the pull"
section, which already existed further down the page. The field/canvas and its lighting,
drift and scroll-tied zoom below are unchanged; only the `.pull-card` fan and its GSAP
entrance are retired. `flight.js`'s scrubbed reveal of the board's own `.chip` elements
(the "the pull" section, not the opener) is unaffected by this and still applies as
written.

```yaml
schema: reidify.motion-spec.v1
project_mode: independent
surface: handful.netlify.app - the story (/), the box (/demo/), try it (/try/)
purpose: >
  Make the scale of the problem visible and the pull of six cards physical, so the
  project's first argument is seen before it is read; then keep those six cards as one
  continuous object down the page so the story reads as one thing being handled.
narrative_beat: >
  1. The box: a field of cards receding into the dark. 2. The pull: six come forward into
  the light and resolve into real photographs. 3. The deal: the same six travel down the
  page and land on the board. 4. Everything else is still.
motion_personality: precise
hierarchy:
  - the field and the six cards (the signature; the only large motion on the site)
  - the pull's small form: the board re-slotting with FLIP, the 86'd stamp
  - paths drawing once (interval plot, slice line), counts on data-count only
  - feedback on controls: sliders, sheet open/close, tap
  - nothing else moves
engine: gsap
elements:
  - name: the field (canvas, fixed behind the opener)
    properties: [uEnter, uScroll, uPtr]      # owned by field.js on the canvas, nothing else touches it
    trigger: first intersection (enter), the opener's own scroll travel (scrub), pointer (point)
  - name: the six pulled cards (DOM, real photographs, placed on the field's plates)
    properties: [transform, opacity]          # owned by GSAP; CSS may never transition these on them
    trigger: enter after the field (staggered), then ScrollTrigger scrub from the opener to the board
  - name: the board rows (demo and story)
    properties: [transform, opacity]          # owned by WAAPI FLIP on slider change, as today
    trigger: slider input
  - name: interval plot, slice segment, bars
    properties: [stroke-dashoffset, transform]  # WAAPI drawPath/growBar, once, as today
    trigger: first view
  - name: counts marked data-count
    properties: [textContent]                 # WAAPI countUp, as today; never on a number in prose or a proof
    trigger: first view
  - name: everything with color, background, border, shadow
    properties: [color, background-color, border-color, box-shadow]   # CSS only
    trigger: hover, focus, state
timing: {duration_ms: 640, delay_ms: 220, easing: "cubic-bezier(.2,.7,.3,1)"}   # the pull; stagger 110ms per card
continuous:
  - {name: the field's drift, kind: oscillating, period_ms: 60000, easing: linear}   # uT, sub-perceptual, stops off-screen
  - {name: the field's travel, kind: progress, period_ms: 0, easing: linear}         # uScroll, scrubbed by the opener's travel
interruption_behavior: >
  Scroll scrubs are stateless (progress in, position out), so reversing direction just
  reverses. The entrance runs once and is never replayed. A slider input during a FLIP
  cancels the running FLIP and starts a new one from the current positions.
responsive_behavior:
  desktop: the full spec - field, pull, flight to the board, pointer parallax
  tablet: as desktop, no pointer parallax, DPR capped at 1.25
  mobile: >
    the field runs, DPR capped at 1.0 and frame-time governed by field.js; the six cards
    enter in place with the same stagger but do not fly between screens (they simply
    appear on the board); no pinning; no pointer parallax
reduced_motion: >
  field.js resolves the entrance to its final frame immediately and stops the drift; the
  six cards render in their resting positions; no flight; FLIP snaps; paths are drawn;
  counts are set. The page is complete with zero animation - this is the same branch
  D-025 required and it stays.
static_fallback: >
  If WebGL2 or the shader is unavailable (field.js onFail), the opener shows a still
  image of the same composition (E01/E02 from the generated set; until those exist, a
  CSS ground) and the six cards in their resting positions. Nothing depends on the canvas.
performance_risks:
  - a full-viewport fragment shader on a mid-range phone in a classroom: mitigated by
    field.js's measured-frame-time resolution governor, maxDpr 1.0 on mobile, and the
    canvas stopping when off-screen or the tab is hidden
  - a ScrollTrigger-scrubbed flight of six DOM elements: transform/opacity only, on a
    fixed overlay layer with will-change, no layout reads per frame
  - the generated grounds as full-bleed images: AVIF/WebP, responsive sizes, loading=lazy
    below the fold, and the evidence must be readable before any of them arrive
qa:
  - zero console errors and zero horizontal overflow at 1440, 1280 and a true 390 (CDP)
  - zero Animation objects running after settle; ScrollTrigger instances killed on unload
  - the six cards land exactly on the board's slots at every breakpoint (measured, not eyeballed)
  - reduced-motion emulation: 0 animations, opacity 1, transform none, counts final
  - onFail path exercised by disabling WebGL: the still shows, nothing throws
  - a throttled mobile profile (4x CPU) keeps the opener above 30fps and first content under 2s
  - contrast-over-media on every piece of type that sits over the field or a ground
evidence:
  - DESIGN.md (the card index; one light; materials with weight) - observed
  - Rish's six references, measured: full-bleed 6/6, dark ground 6/6, artefact is a canvas 6/6, luminance range > 0.45 6/6 - observed
  - "students on their phones in class" - stated by Rish, 2026-09-10
  - what a classroom's phones and network actually are - unknown; hence the conservative mobile branch
approval_boundary: >
  Vendoring field.js and GSAP was approved by Rish on 2026-09-10 (supersedes D-025's
  refusal of a library; the reason is the scrubbed flight, which WAAPI cannot express
  as a single reversible progress). Generated imagery is produced by Rish in ChatGPT from
  IMAGE_HANDOFF_FOR_CHATGPT.md; none is fetched by this build. No recipe photograph is
  ever generated.
```

## Rejected effects

Parallax on anything read; scroll-jacking or pinned copy; a loader that hides content;
scramble or split-text on headings; any loop that carries no information; any motion that
implies choosing was faster, easier or better - that would be a claim the study does not
make. The field's drift is the one continuous motion and it is sub-perceptual.

## Ownership map (one owner per element and property)

| Element | transform / opacity | colour / border / shadow | stroke-dashoffset | textContent |
|---|---|---|---|---|
| canvas.field | field.js (uniforms) | — | — | — |
| .pull-card (the six) | GSAP | CSS | — | — |
| .brow / .chip (board) | WAAPI FLIP | CSS | — | — |
| charts | WAAPI | CSS | WAAPI | — |
| [data-count] | — | — | — | WAAPI |
| everything else | CSS (hover lift on .card only) | CSS | — | — |

The stylesheet enforces the first rule for WAAPI elements with
`[data-anim]{transition-property: background-color, border-color, color, box-shadow, fill, stroke}`;
the same rule is extended to `[data-flight]` for the GSAP-owned cards.
