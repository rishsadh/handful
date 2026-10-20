/* The box: the opener's field (D-039).
 *
 * A WebGL2 fragment on the framework's field runtime, lighting and slowly pulling into a
 * single generated still: an overflowing card-index box at night, the 230,064 cards this
 * person could be handed, made visible as atmosphere. No specific card is shown here - the
 * six real, computed ones for a real person appear for the first time in "the pull"
 * section further down the page, which is where the actual claim is made. The hero's job
 * is only to open on a scene worth pulling something out of.
 *
 * Ownership: field.js owns the canvas's uniforms. Nothing else touches it.
 */
import { mount, COMMON } from '/assets/field.js';

const THE_BOX = COMMON + `
uniform sampler2D uTex; uniform vec2 uTexAspect;
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  float e=enter();
  // cover-fit; the pull is a slow move into the box; the pointer nudges the view
  float zoom=1.0+uScroll*0.16+(1.0-e)*0.06;
  vec2 st=(gl_FragCoord.xy/uRes-0.5)/uTexAspect/zoom - uPtr*0.010;
  vec2 t=clamp(st+0.5,0.002,0.998);
  vec3 src=texture(uTex,vec2(t.x,1.0-t.y)).rgb;
  vec2 lp=uLightPos+uPtr*0.14;
  float lit=falloff(uv,lp,4.5);
  vec3 col=src*(0.70+lit*0.60)*mix(0.30,1.0,e);
  // the lower third stays dark so the title and the figures sit on it
  col*=mix(1.0,0.50,smoothstep(0.02,-0.42,uv.y));
  col+=uLight*pow(lit,2.2)*0.08*e;
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

const phone = () => matchMedia('(max-width: 899px)').matches;

function boot() {
  const opener = document.querySelector('#open');
  const canvas = document.querySelector('#field');
  if (!opener || !canvas) return;

  const still = new Image();
  still.decoding = 'async';
  still.src = phone() ? '/img/gen/hero-archive-tall-w1080.webp' : '/img/gen/hero-archive-wide-w1600.webp';
  const start = () => {
    mount(canvas, THE_BOX, {
      items: [],
      image: still,
      ink: [0.10, 0.075, 0.06],
      light: [0.96, 0.74, 0.48],
      lightPos: [-0.36, 0.34],
      maxDpr: phone() ? 1.0 : 1.25,
      enterMs: 1400,
      onFail() { opener.classList.add('no-field'); },
    });
    opener.classList.add('has-field');
  };
  if (still.complete && still.naturalWidth) start();
  else { still.addEventListener('load', start, { once: true }); still.addEventListener('error', () => opener.classList.add('no-field'), { once: true }); }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
