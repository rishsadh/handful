/* The deal (D-034): the six cards arrive on the story's board as it scrolls into view,
 * scrubbed by the page, one after another, from above - where the box is.
 *
 * GSAP + ScrollTrigger, vendored under /assets/vendor. Desktop and tablet only, and only
 * when motion is not reduced; on a phone the cards simply appear in place. GSAP owns
 * transform/opacity on [data-flight] elements; CSS never transitions those there.
 */
(function () {
  if (!window.gsap || !window.ScrollTrigger) return;
  const gsap = window.gsap;
  gsap.registerPlugin(window.ScrollTrigger);

  const mm = gsap.matchMedia();
  let live = null;

  function build() {
    const board = document.querySelector('#board .board');
    if (!board) return;
    const chips = [...board.querySelectorAll('.chip')];
    if (!chips.length) return;
    if (live) { live.kill(); live = null; }
    chips.forEach((c) => c.setAttribute('data-flight', ''));
    gsap.set(chips, { y: -180, rotate: -5, opacity: 0 });
    live = gsap.timeline({
      scrollTrigger: {
        trigger: board,
        start: 'top 92%',
        end: 'top 38%',
        scrub: 0.6,
        invalidateOnRefresh: true,
      },
    });
    chips.forEach((c, i) => {
      live.to(c, { y: 0, rotate: 0, opacity: 1, duration: 1, ease: 'power2.out' }, i * 0.18);
    });
  }

  mm.add('(min-width: 900px) and (prefers-reduced-motion: no-preference)', () => {
    build();
    const onBoard = () => { build(); window.ScrollTrigger.refresh(); };
    document.addEventListener('handful:board', onBoard);
    return () => {
      document.removeEventListener('handful:board', onBoard);
      if (live) { live.kill(); live = null; }
      document.querySelectorAll('[data-flight]').forEach((c) => {
        c.removeAttribute('data-flight');
        c.style.transform = '';
        c.style.opacity = '';
      });
    };
  });

  addEventListener('load', () => window.ScrollTrigger.refresh());
})();
