/* Vendored from reidify-agent-skills/artifacts/field.js (zero-dependency WebGL2 fields).
 * One local change: COMMON is exported at the end so Handful can compose its own fragment
 * ("the box") on the same helpers, entrance and grade. Upstream fixes should be re-applied here. */
/**
 * Reidify artifact fields.
 *
 * A surface that has to win contains something made for it. Writing a shader
 * from scratch is harder than not, so the default becomes a blank page and no
 * rule survives that. This exists so the made thing is the easy option.
 *
 * Zero dependencies, one file, raw WebGL2. Drop it in, call mount().
 *
 *   import { mount, FIELDS } from './field.js';
 *   const field = mount(canvas, FIELDS.litDepth, {
 *     items: [{ x:-0.46, y:0.16, z:0.30, w:0.40 }, ...]
 *   });
 *   field.destroy();
 *
 * Every lesson in here was paid for in a build that shipped broken:
 *
 *  - the framebuffer is cleared every frame, or blending composites each frame
 *    onto the last and an animation smears its own history across the canvas
 *  - no layout property is read inside the render loop, because clientWidth
 *    forces a synchronous layout on every frame while smooth scroll is running
 *  - a failed shader compile is console.error, not warn, because a warn is
 *    invisible and the page runs silently on its fallback while reporting clean
 *  - resolution is governed by measured frame time, because the same shader is
 *    cheap on a GPU and ruinous on a software rasteriser
 *  - it stops drawing when off screen and when the tab is hidden
 *  - prefers-reduced-motion resolves to a still frame rather than a faster one
 */

const VERT =
  '#version 300 es\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.0-1.0,0,1);}';

/** Shared GLSL. Kept in one place so a fix lands in every field at once. */
const COMMON = `#version 300 es
precision highp float;
out vec4 O;
uniform vec2 uRes; uniform float uT; uniform vec2 uPtr; uniform float uScroll;
uniform vec4 uItem[6]; uniform int uCount; uniform vec3 uInk; uniform vec3 uLight;
uniform vec2 uLightPos;
uniform vec4 uMark;   // xy centre, z scale, w strength
uniform float uEnter; // 0 to 1, starts when the field is first seen
uniform float uGridY; // where the run of plates sits, so type has room below
uniform float uPlate; // plate height as a multiple of its width

float hash(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));
  q+=dot(q,q.yzx+33.33); return fract((q.x+q.y)*q.z);}
float nz(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<4;i++){s+=a*nz(p);p=p*2.05+vec2(3.1,1.7);a*=.5;}return s;}
float sdSeg(vec2 p,vec2 a,vec2 b,float r){vec2 pa=p-a,ba=b-a;
  float t=clamp(dot(pa,ba)/dot(ba,ba),0.,1.);return length(pa-ba*t)-r;}
float sdBox(vec2 p,vec2 b){vec2 d=abs(p)-b;return length(max(d,0.))+min(max(d.x,d.y),0.);}
float falloff(vec2 a,vec2 b,float k){float d=length(a-b);return 1.0/(1.0+d*d*k);}
// The identity layer.
//
// reidify-v2 read thinner than the E-hybrid it was meant to improve on, and the
// difference was this: the mark sat on top of the field as a DOM element rather
// than inside it. A mark composited over a scene is a sticker. A mark cut into
// the scene, catching the same light and carrying the same grain, is identity.
//
// markSdf is a no-op by default and withMark() replaces its body, so every
// field gains the layer without any field knowing about it.
float markSdf(vec2 p){ return 1e9; }
vec3 markLayer(vec3 c,vec2 uv){
  if(uMark.w<=0.0) return c;
  vec2 p=(uv-uMark.xy)/max(uMark.z,1e-4);
  float d=markSdf(p)*max(uMark.z,1e-4);
  float px=1.6/uRes.y;
  float inside=smoothstep(px,-px,d);
  float edge=smoothstep(px*2.4,0.0,abs(d));
  // lit by the scene's own source, so the mark belongs to the space
  vec2 toL=normalize(uLightPos+uPtr*0.15-uv);
  float sheen=smoothstep(-0.7,0.7,dot(normalize(p+1e-5),toL));
  float pl=falloff(uv,uLightPos+uPtr*0.15,3.0);
  vec3 face=mix(vec3(0.030,0.033,0.042),uLight*0.60,sheen*(0.35+pl*0.9));
  c=mix(c,face,inside*0.90*uMark.w);
  c+=vec3(1.0,0.90,0.76)*edge*(0.35+sheen*1.6)*(0.4+pl*1.4)*uMark.w;
  return c;
}
// The motion vocabulary. Three verbs, and every field speaks all three:
//   enter   — the field arrives, once, when it is first actually seen
//   uScroll — 0 to 1 as the field travels through the viewport
//   uPtr    — eased pointer, already smoothed by the runtime
// A field that is simply present at t=0 reads as a background image. The
// reference set reveals; nothing in it is just there.
float ease(float x){ return x<0.5 ? 4.0*x*x*x : 1.0-pow(-2.0*x+2.0,3.0)/2.0; }
float enter(){ return ease(clamp(uEnter,0.0,1.0)); }
// staggered arrival: element i of n starts later and still finishes on time
float enterAt(float i,float n){
  float span=0.55, step=(1.0-span)/max(n-1.0,1.0);
  return ease(clamp((uEnter-i*step)/span,0.0,1.0));
}
vec3 grade(vec3 c,vec2 uv){
  // The measured defect across every surface built here was luminance range,
  // not hue: everything sat between 0.02 and 0.16 and nothing caught the light.
  //
  // Two attempts on 30 Aug 2026 to make this ground-aware both failed, measured
  // across three grounds and three fields. Baseline is six of nine pairs under
  // the 0.45 range floor. A vignette falling toward the ground colour held the
  // count at six while collapsing the light cases from 0.435 to 0.106; a
  // subtractive light model for pale grounds took the count to seven. This
  // curve is the measured best of the three.
  //
  // It is not ground-blind and the field matters more than the curve:
  // gridInDepth grades 0.569 on paper against 0.308 on black, flowField the
  // reverse at 0.583 dark and 0.435 light. Pick the field for the ground; see
  // artifacts/README.md. Do not tune this curve to fix a field mismatch.
  //
  // No backticks in here. This string is a JS template literal and one closed
  // it, which blanked every field and cost a debugging round.
  c=pow(max(c,0.0),vec3(0.82));
  c*=clamp(1.0-0.60*dot(uv,uv),0.0,1.0);
  return c+(hash(gl_FragCoord.xy)-0.5)*0.028;
}
`;

/**
 * litDepth — objects at real depths, lit by a source in the scene.
 * Items carry content: pass the same array to your DOM labels so a word can
 * never drift from the thing it names.
 */
const litDepth = COMMON + `
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  float px=1.4/uRes.y;
  vec3 col=uInk;
  vec2 lp=uLightPos+uPtr*0.16;
  float lit=falloff(uv,lp,7.0);

  vec2 fp=uv*2.6+vec2(uT*0.028,uT*0.012);
  vec2 g=fract(fp)-0.5;
  float lat=smoothstep(0.475,0.5,max(abs(g.x),abs(g.y)));
  col+=vec3(0.10,0.14,0.17)*lat*smoothstep(1.25,0.15,length(uv))*(0.35+lit*1.9);
  col+=uLight*pow(lit,2.0)*0.55*mix(0.25,1.0,enter());

  for(int i=0;i<6;i++){
    if(i>=uCount) break;
    vec4 it=uItem[i];
    float persp=1.0/(0.55+it.z*1.15);
    vec2 c=it.xy-uPtr*0.05*(1.0-it.z);
    vec2 q=(uv-c*persp)/persp;
    float d=sdBox(q,vec2(it.w*0.5,it.w*0.34));
    float inside=smoothstep(px/persp,-px/persp,d);
    float edge=smoothstep(px*2.2/persp,0.0,abs(d));
    vec2 toL=normalize(lp-c*persp);
    float sheen=smoothstep(-0.55,0.55,dot(normalize(q+1e-5),toL));
    float pl=falloff(c*persp,lp,4.0);
    vec3 face=mix(vec3(0.030,0.033,0.042),vec3(0.20,0.175,0.165),sheen);
    face=mix(face,uLight*0.62,sheen*sheen*(0.35+pl*0.9));
    float dim=mix(0.42,1.0,it.z);
    float e=enterAt(float(i),float(uCount));
    col=mix(col,face,inside*0.95*dim*e);
    col+=vec3(1.0,0.88,0.70)*edge*(0.35+sheen*1.7)*(0.4+pl*1.6)*dim*e;
  }
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

/**
 * resolvingLattice — planes receding into depth. Far away a cell is only a
 * coordinate; near, it resolves into form. Depth carries the idea.
 */
const resolvingLattice = COMMON + `
float glyph(vec2 p){
  float r=0.055;
  float d=sdSeg(p,vec2(-0.26,-0.50),vec2(-0.26,0.50),r);
  d=min(d,sdSeg(p,vec2(-0.26,0.50),vec2(0.13,0.50),r));
  d=min(d,sdSeg(p,vec2(0.13,0.50),vec2(0.27,0.36),r));
  d=min(d,sdSeg(p,vec2(0.27,0.36),vec2(0.27,0.14),r));
  d=min(d,sdSeg(p,vec2(0.27,0.14),vec2(0.13,0.00),r));
  d=min(d,sdSeg(p,vec2(0.13,0.00),vec2(-0.26,0.00),r));
  d=min(d,sdSeg(p,vec2(0.01,0.00),vec2(0.30,-0.50),r));
  return d;
}
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  vec2 p=uv-uPtr*0.06;
  vec3 col=uInk;
  float t=uT*0.09+uScroll*0.6;
  float ent=enter();
  for(int i=0;i<8;i++){
    float fi=float(i);
    float z=fract(t+fi*0.125);
    float sc=mix(9.0,0.85,z*z);
    float fade=smoothstep(0.0,0.16,z)*smoothstep(1.0,0.72,z);
    vec2 q=p*sc; vec2 id=floor(q+0.5); vec2 c=q-id;
    if(hash(id+fi*17.0)<0.42) continue;
    float d=glyph(c*1.25);
    float pxs=2.4*sc/uRes.y;
    float res=smoothstep(0.30,0.85,z);
    float form=mix(smoothstep(pxs*1.2,0.0,abs(d)-0.012)*0.55,smoothstep(pxs,-pxs,d),res);
    vec3 tint=mix(vec3(0.30,0.52,0.60),vec3(0.95,0.92,0.86),res);
    tint=mix(tint,uLight,smoothstep(0.72,1.0,z)*0.55);
    col+=tint*form*fade*mix(0.16,0.62,res)*enterAt(fi,8.0);
  }
  col+=vec3(0.035,0.042,0.055)*smoothstep(1.1,0.0,length(uv))*0.7*mix(0.3,1.0,ent);
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

/**
 * treatedImage — a generated source, treated until it belongs to the project.
 * Four of sixteen measured award sites carry the fold on imagery rather than a
 * canvas. Raw generative output is not one of them: duotone, grain and
 * displacement are what turn a render into part of a design.
 * Pass { image: HTMLImageElement }.
 */
const treatedImage = COMMON + `
uniform sampler2D uTex; uniform vec2 uTexAspect;
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  vec2 t=(gl_FragCoord.xy/uRes-0.5)*uTexAspect*0.94+0.5;
  float warp=fbm(uv*2.2+uT*0.02+uScroll*0.4);
  t+=vec2(warp-0.5,fbm(uv*2.2-uT*0.02)-0.5)*0.035;
  vec3 src=texture(uTex,clamp(t,0.006,0.994)).rgb;
  float l=dot(src,vec3(0.2126,0.7152,0.0722));
  l=pow(l,0.85);
  vec3 col=mix(uInk,uLight,smoothstep(0.10,0.92,l));
  col=mix(col,vec3(l),0.18);
  float lit=falloff(uv,uLightPos+uPtr*0.14,5.0);
  col*=(0.55+lit*1.1)*mix(0.42,1.0,enter());
  col+=vec3(0.9,0.85,0.78)*smoothstep(0.80,1.0,l)*0.35*enter();
  float scan=smoothstep(0.48,0.5,fract(gl_FragCoord.y*0.5));
  col*=1.0-scan*0.045;
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;


/**
 * gridInDepth — real work arranged on a curved grid receding into space.
 * The move `k95.it` makes, and the one every studio portfolio in the reference
 * set that scored well is doing in some form.
 *
 * The canvas draws the space, the lighting and the cell plates. **The work
 * itself stays in the DOM**, placed by `cells()`, because that keeps real
 * images accessible, indexable and cacheable while the GPU handles atmosphere.
 * That split is the architecture Shopify's team states outright.
 */
const gridInDepth = COMMON + `
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  float px=1.4/uRes.y;
  vec3 col=uInk;
  vec2 lp=uLightPos+uPtr*0.14;
  float lit=falloff(uv,lp,5.0);
  col+=uLight*pow(lit,2.2)*0.42*mix(0.25,1.0,enter());

  // the ground plane, curving away
  vec2 gp=uv*3.0+vec2(uT*0.03+uScroll*0.9,uScroll*0.35);
  vec2 gg=fract(gp)-0.5;
  float lat=smoothstep(0.482,0.5,max(abs(gg.x),abs(gg.y)));
  col+=vec3(0.09,0.12,0.15)*lat*smoothstep(1.3,0.1,length(uv))*(0.3+lit*1.6);

  // plates across, curved in z so the outer ones fall away
  float n=float(max(uCount,1));
  // the run keeps its total width, so three works read as three large plates
  // rather than as five plates with two missing
  float gap=1.50/n, hw=gap*0.383, hh=hw*uPlate;
  // everything here is normalised by height, so on a narrow viewport the run
  // ran past both edges. Fit it to the width instead.
  float runW=(n-1.0)*gap+2.0*hw;
  float fit=min(1.0,(uRes.x/uRes.y)*0.92/max(runW,1e-4));
  gap*=fit; hw*=fit; hh*=fit;
  for(int i=0;i<6;i++){
    if(i>=uCount) break;
    float fi=float(i)-(n-1.0)*0.5;
    float curve=fi*fi*(0.055*25.0/(n*n))*fit;
    float z=0.62-curve;
    float persp=1.0/(0.55+z*1.15);
    vec2 c=vec2(fi*gap,uGridY-curve*0.5)-uPtr*0.045*(1.0-z);
    vec2 q=(uv-c*persp)/persp;
    float d=sdBox(q,vec2(hw,hh));
    float inside=smoothstep(px/persp,-px/persp,d);
    float edge=smoothstep(px*2.0/persp,0.0,abs(d));
    vec2 toL=normalize(lp-c*persp);
    float sheen=smoothstep(-0.6,0.6,dot(normalize(q+1e-5),toL));
    float pl=falloff(c*persp,lp,3.2);
    vec3 face=mix(vec3(0.028,0.031,0.040),vec3(0.17,0.155,0.150),sheen);
    face=mix(face,uLight*0.55,sheen*sheen*(0.30+pl*0.8));
    float dim=mix(0.45,1.0,z);
    float e=enterAt(float(i),n);
    col=mix(col,face,inside*0.92*dim*e);
    col+=vec3(1.0,0.88,0.72)*edge*(0.30+sheen*1.5)*(0.4+pl*1.5)*dim*e;
  }
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

/**
 * flowField — a vector field drifting across the ground. The cheapest kind of
 * atmosphere that still reads as made rather than as a gradient.
 */
const flowField = COMMON + `
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  vec3 col=uInk;
  float t=uT*0.05+uScroll*0.85;
  vec2 p=uv*1.7;
  // two-step domain warp: cheap, and it reads as motion rather than as noise
  vec2 w=vec2(fbm(p+vec2(t,0.0)),fbm(p+vec2(0.0,-t)));
  float f=fbm(p+w*1.6);
  float ridge=1.0-abs(f-0.5)*2.0;
  float lit=falloff(uv,uLightPos+uPtr*0.15,4.5);
  col+=vec3(0.07,0.09,0.11)*smoothstep(0.25,0.95,f)*(0.5+lit*1.8);
  col+=uLight*pow(ridge,7.0)*(0.30+lit*1.5)*0.55*enter();
  col+=uLight*pow(lit,2.4)*0.35;
  // filaments: thin bright lines where the field folds
  float fil=smoothstep(0.90,1.0,ridge);
  col+=vec3(1.0,0.92,0.80)*fil*0.30*enterAt(1.0,2.0);
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

/**
 * grainAtmosphere — a committed ground, one light, and grain. Nothing else.
 * The reference set is polarised toward extreme grounds, and this is the
 * honest minimum that still clears the production floor: it is a made light,
 * not a CSS gradient.
 */
const grainAtmosphere = COMMON + `
void main(){
  vec2 uv=(gl_FragCoord.xy-0.5*uRes)/uRes.y;
  vec3 col=uInk;
  vec2 lp=uLightPos+uPtr*0.20;
  float lit=falloff(uv,lp,3.4);
  col+=uLight*pow(lit,1.7)*0.62*mix(0.18,1.0,enter());
  float drift=fbm(uv*1.1+vec2(uT*0.012+uScroll*0.5,-uT*0.008));
  col+=uLight*0.10*smoothstep(0.42,0.95,drift)*lit;
  col+=vec3(0.02,0.026,0.033)*smoothstep(0.30,0.95,drift);
  O=vec4(grade(markLayer(col,uv),uv),1.0);
}`;

export const FIELDS = { litDepth, resolvingLattice, treatedImage,
                        gridInDepth, flowField, grainAtmosphere };

/**
 * Marks — the geometry of a project's own mark, as a signed distance field.
 *
 * These are constructions, not a brand. A project writes its own and passes it
 * to withMark(); `monogram` is a worked example so the shape of the thing is
 * obvious. Return a signed distance for `p` in mark space, where the mark
 * occupies roughly -0.5 to 0.5.
 */
export const MARKS = {
  // an R built from segments: stem, bowl, leg. A demonstration of the form a
  // mark takes here, not a claim about anyone's identity.
  monogram: `
    float d=sdSeg(p,vec2(-0.22,-0.42),vec2(-0.22,0.42),0.055);
    d=min(d,sdSeg(p,vec2(-0.22,0.42),vec2(0.10,0.42),0.055));
    d=min(d,sdSeg(p,vec2(0.10,0.42),vec2(0.19,0.26),0.055));
    d=min(d,sdSeg(p,vec2(0.19,0.26),vec2(0.10,0.06),0.055));
    d=min(d,sdSeg(p,vec2(0.10,0.06),vec2(-0.22,0.06),0.055));
    d=min(d,sdSeg(p,vec2(-0.02,0.06),vec2(0.22,-0.42),0.055));
    return d;`,
  // a ring with a break in it — reads at any size, including a favicon
  aperture: `
    float r=abs(length(p)-0.34)-0.052;
    float cut=sdBox(p-vec2(0.30,0.0),vec2(0.16,0.10));
    return max(r,-cut);`,
  // three bars at unequal depth: the smallest possible statement of recession
  strata: `
    float d=sdBox(p-vec2(-0.02,0.20),vec2(0.34,0.045));
    d=min(d,sdBox(p-vec2(0.06,0.00),vec2(0.26,0.045)));
    d=min(d,sdBox(p-vec2(-0.10,-0.20),vec2(0.18,0.045)));
    return d;`,
};

/**
 * withMark — put a project's mark inside a field.
 *
 * Composes rather than forks: any field plus any mark. Throws rather than
 * silently returning the unmarked field, because a mark that quietly fails to
 * appear is exactly the defect this whole library exists to stop.
 *
 *   mount(canvas, withMark(FIELDS.gridInDepth, MARKS.aperture),
 *         { mark: { x: 0.42, y: 0.24, scale: 0.30, strength: 0.9 } })
 */
export function withMark(fragment, sdfBody) {
  const stub = 'float markSdf(vec2 p){ return 1e9; }';
  if (!fragment.includes(stub))
    throw new Error('withMark: fragment does not carry the mark layer');
  return fragment.replace(stub, `float markSdf(vec2 p){${sdfBody}
}`);
}

function compile(gl, type, src, label) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    // error, never warn: a warn is invisible and the page runs on its fallback
    console.error(`[field] ${label} failed to compile:\n` + gl.getShaderInfoLog(s));
    return null;
  }
  return s;
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {string} fragment  one of FIELDS
 * @param {object} [opts]
 *   items      [{x,y,z,w}]      up to 6, the content the field carries
 *   ink        [r,g,b] 0..1     ground
 *   light      [r,g,b] 0..1     the lit colour
 *   lightPos   [x,y]            in uv space, y up
 *   image      HTMLImageElement for treatedImage
 *   maxDpr     number           default 1.25
 *   onFail     () => void       called if WebGL2 or the shader is unavailable
 */
export function mount(canvas, fragment, opts = {}) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false });
  if (!gl) { opts.onFail?.(); return { destroy() {} }; }

  const vs = compile(gl, gl.VERTEX_SHADER, VERT, 'vertex');
  const fs = compile(gl, gl.FRAGMENT_SHADER, fragment, 'fragment');
  if (!vs || !fs) { opts.onFail?.(); return { destroy() {} }; }
  const prog = gl.createProgram();
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.error('[field] link failed:\n' + gl.getProgramInfoLog(prog));
    opts.onFail?.(); return { destroy() {} };
  }
  gl.useProgram(prog);
  gl.bindVertexArray(gl.createVertexArray());

  const U = {};
  for (const n of ['uRes','uT','uPtr','uScroll','uItem','uCount','uInk','uLight','uLightPos','uMark','uEnter','uGridY','uPlate','uTex','uTexAspect'])
    U[n] = gl.getUniformLocation(prog, n);

  const items = (opts.items || []).slice(0, 6);
  const flat = new Float32Array(24);
  items.forEach((it, i) => { flat[i*4]=it.x; flat[i*4+1]=it.y; flat[i*4+2]=it.z; flat[i*4+3]=it.w; });
  gl.uniform4fv(U.uItem, flat);
  gl.uniform1i(U.uCount, items.length);
  gl.uniform3fv(U.uInk, opts.ink || [0.020, 0.021, 0.028]);
  gl.uniform3fv(U.uLight, opts.light || [0.95, 0.72, 0.46]);
  gl.uniform2fv(U.uLightPos, opts.lightPos || [-0.34, 0.30]);
  gl.uniform1f(U.uGridY, opts.gridY ?? 0.04);
  // Plate height over width. The default is portrait, which suits a product or
  // a poster; a portfolio of websites wants landscape, or every screenshot gets
  // cropped through its own headline.
  gl.uniform1f(U.uPlate, opts.plateAspect ?? 1.304);
  const mk = opts.mark || {};
  gl.uniform4f(U.uMark, mk.x ?? 0, mk.y ?? 0, mk.scale ?? 0.3,
    opts.mark ? (mk.strength ?? 0.9) : 0);

  if (opts.image) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, opts.image);
    gl.uniform1i(U.uTex, 0);
  }

  // Layout is read here and on resize only. Never inside the frame loop.
  const maxDpr = opts.maxDpr ?? 1.25;
  let scale = 1, lw = 0, lh = 0, acc = 0, accN = 0;
  // cached in size(); project() and cells() return canvas-relative CSS px, so
  // neither the caller nor this file reads layout per frame
  let cw = 1, ch = 1;
  function size() {
    const d = Math.min(devicePixelRatio || 1, maxDpr) * scale;
    cw = canvas.clientWidth; ch = canvas.clientHeight;
    const w = Math.max(2, Math.round(cw * d));
    const h = Math.max(2, Math.round(ch * d));
    if (w !== lw || h !== lh) {
      canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); lw = w; lh = h;
      if (opts.image) {
        const ia = opts.image.naturalWidth / opts.image.naturalHeight, ca = w / h;
        gl.uniform2f(U.uTexAspect, ca > ia ? 1 : ia / ca, ca > ia ? ca / ia : 1);
      }
    }
  }
  size();

  let px = 0, py = 0, tx = 0, ty = 0, scroll = 0, visible = true, raf = 0;
  const fixed = getComputedStyle(canvas).position === 'fixed';
  // The entrance starts when the field is first actually seen, not at mount.
  // A hero that finished animating while it was still below the fold has not
  // animated at all, which is the commonest way this effect is wasted.
  const enterMs = reduce ? 0 : (opts.enterMs ?? 1100);
  let enterT0 = 0, entered = false;
  const t0 = performance.now(); let prev = t0;

  const onResize = () => size();
  const onPointer = (e) => { tx = (e.clientX/innerWidth-0.5)*2; ty = -(e.clientY/innerHeight-0.5)*2; };
  const onScroll = () => {
    // Progress of this element through the viewport, not of the document. A
    // section-scoped field wants its own travel; a fixed full-screen canvas
    // never moves, so that case falls back to the page.
    if (fixed) {
      const max = document.documentElement.scrollHeight - innerHeight;
      scroll = max > 0 ? Math.min(Math.max(scrollY / max, 0), 1) : 0;
    } else {
      // A layout read here is fine. The ban is on reading inside the frame
      // loop, where it forces a synchronous layout every frame under smooth
      // scroll; a scroll handler is already past layout.
      const r = canvas.getBoundingClientRect();
      const span = innerHeight + r.height;
      scroll = span > 0 ? Math.min(Math.max((innerHeight - r.top) / span, 0), 1) : 0;
    }
  };
  addEventListener('resize', onResize, { passive: true });
  if (!reduce) addEventListener('pointermove', onPointer, { passive: true });
  addEventListener('scroll', onScroll, { passive: true });

  let io;
  if ('IntersectionObserver' in window) {
    io = new IntersectionObserver((es) => {
      visible = es[0].isIntersecting;
      if (visible && !entered) { entered = true; enterT0 = performance.now(); }
    }, { threshold: 0 });
    io.observe(canvas);
  }
  if (!io) { entered = true; enterT0 = performance.now(); }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = now - prev; prev = now;
    if (!visible || document.hidden) return;

    acc += dt; accN++;
    if (accN >= 30) {
      const avg = acc / accN; acc = 0; accN = 0;
      const was = scale;
      if (avg > 26) scale = Math.max(0.45, scale * 0.82);
      else if (avg < 15) scale = Math.min(1, scale * 1.06);
      if (Math.abs(scale - was) > 0.004) size();
    }

    px += (tx - px) * 0.05; py += (ty - py) * 0.05;
    // Clear or blending composites this frame onto the last.
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(U.uRes, canvas.width, canvas.height);
    gl.uniform1f(U.uT, reduce ? 8.0 : (now - t0) / 1000);
    gl.uniform2f(U.uPtr, px, py);
    gl.uniform1f(U.uScroll, scroll);
    gl.uniform1f(U.uEnter, !entered ? 0 : enterMs <= 0 ? 1
      : Math.min((now - enterT0) / enterMs, 1));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  raf = requestAnimationFrame(frame);

  return {
    /**
     * Cell rectangles for gridInDepth, in screen px. Place real work here as
     * DOM <img> so the images stay accessible and cacheable while the canvas
     * carries the space and the light.
     */
    cells() {
      const h = ch, out = [], n = Math.max(1, Math.min(6, (opts.items || []).length || 5));
      let gap = 1.50 / n, hw = gap * 0.383, hh = hw * (opts.plateAspect ?? 1.304);
      const runW = (n - 1) * gap + 2 * hw;
      const fit = Math.min(1, (cw / ch) * 0.92 / Math.max(runW, 1e-4));
      gap *= fit; hw *= fit; hh *= fit;
      for (let i = 0; i < n; i++) {
        const fi = i - (n - 1) * 0.5;
        const curve = fi * fi * (0.055 * 25 / (n * n)) * fit, z = 0.62 - curve;
        const persp = 1 / (0.55 + z * 1.15);
        const cx = fi * gap - px * 0.045 * (1 - z);
        const cy = (opts.gridY ?? 0.04) - curve * 0.5 - py * 0.045 * (1 - z);
        out.push({
          left: cw * 0.5 + (cx - hw) * persp * h,
          top: h * 0.5 - (cy + hh) * persp * h,
          width: hw * 2 * persp * h, height: hh * 2 * persp * h,
          depth: z, opacity: 0.45 + 0.55 * z,
        });
      }
      return out;
    },
    /** project an item to screen px, so DOM labels sit on the thing they name */
    project(item) {
      const persp = 1 / (0.55 + item.z * 1.15);
      return {
        x: cw * 0.5 + (item.x - px * 0.05 * (1 - item.z)) * persp * ch,
        y: ch * 0.5 - (item.y - py * 0.05 * (1 - item.z)) * persp * ch,
        scale: persp,
      };
    },
    destroy() {
      cancelAnimationFrame(raf);
      removeEventListener('resize', onResize);
      removeEventListener('pointermove', onPointer);
      removeEventListener('scroll', onScroll);
      io?.disconnect();
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    },
  };
}

export { COMMON };
