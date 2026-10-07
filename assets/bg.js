/* SimuCanarias · shared animated background ("aurora"). Vanilla WebGL1, no dependencies.
 *
 * Usage on any page:
 *   <canvas id="aurora" aria-hidden="true"></canvas>
 *   <script src="assets/bg.js" defer></script>
 * It auto-mounts on <canvas id="aurora"> and also exposes window.mountAurora(canvas) -> { destroy() }.
 *
 * The canvas is fixed behind the content (z-index:-1, pointer-events:none). Give the page colour to
 * <html> (not to an opaque <body> background), otherwise the body background covers the canvas.
 *
 * - Soft moving colour blobs (indigo / blue / cyan / faint amber) over the page background + subtle grain.
 * - DPR capped at 1.5, ~30 fps, paused while the tab is hidden.
 * - prefers-reduced-motion: renders one static frame (re-rendered on resize / theme change).
 * - Light theme (prefers-color-scheme: light or <html data-theme="light">): lighter, low-opacity blobs.
 * - No WebGL (or shader failure / context loss): CSS radial-gradient fallback on the canvas itself.
 */
(function () {
  'use strict';
  if (window.mountAurora) return;

  var MAX_DPR = 1.5;
  var FRAME_MS = 1000 / 30;
  var T0 = 11; // seconds: start from a pleasant composition instead of t = 0

  var VERT = 'attribute vec2 aPos;void main(){gl_Position=vec4(aPos,0.0,1.0);}';
  var FRAG = [
    '#ifdef GL_FRAGMENT_PRECISION_HIGH',
    'precision highp float;',
    '#else',
    'precision mediump float;',
    '#endif',
    'uniform vec2 uRes;',
    'uniform vec2 uC[4];',      // blob centres (computed on the CPU, in "height" units)
    'uniform float uLight;',    // 0 = dark theme, 1 = light theme
    'uniform float uSeed;',     // grain seed, changes every frame
    'float hash(vec2 p){p=fract(p*vec2(0.1031,0.1030));p+=dot(p,p.yx+33.33);return fract((p.x+p.y)*p.x);}',
    'float blob(vec2 p,vec2 c,float r){vec2 d=p-c;return exp(-dot(d,d)/(r*r));}',
    'void main(){',
    '  vec2 uv=gl_FragCoord.xy/uRes;',
    '  float asp=uRes.x/uRes.y;',
    '  vec2 p=vec2((uv.x-0.5)*asp,uv.y-0.5);',
    '  vec3 col=mix(vec3(0.0235,0.0392,0.0902),vec3(0.957,0.969,0.992),uLight);',
    '  vec4 a=mix(vec4(0.62,0.28,0.17,0.07),vec4(0.15,0.12,0.10,0.07),uLight);',
    '  float s=mix(1.0,0.9,uLight);',
    '  col=mix(col,vec3(0.118,0.227,0.541),blob(p,uC[0],0.62*s)*a.x);',
    '  col=mix(col,vec3(0.145,0.388,0.922),blob(p,uC[1],0.50*s)*a.y);',
    '  col=mix(col,vec3(0.024,0.714,0.831),blob(p,uC[2],0.46*s)*a.z);',
    '  col=mix(col,vec3(0.961,0.620,0.043),blob(p,uC[3],0.34*s)*a.w);',
    '  float v=smoothstep(1.15,0.25,length((uv-0.5)*vec2(1.0,1.2)));',
    '  col*=mix(0.78+0.22*v,1.0,uLight);',
    '  float g=hash(gl_FragCoord.xy+uSeed)-0.5;',
    '  col+=g*mix(0.028,0.018,uLight);',
    '  gl_FragColor=vec4(col,1.0);',
    '}'
  ].join('\n');

  var FALLBACK_DARK =
    'radial-gradient(60% 50% at 18% 12%, rgba(30,58,138,.55), transparent 70%),' +
    'radial-gradient(50% 45% at 86% 26%, rgba(37,99,235,.28), transparent 70%),' +
    'radial-gradient(55% 45% at 55% 96%, rgba(6,182,212,.16), transparent 70%),' +
    'radial-gradient(35% 30% at 92% 90%, rgba(245,158,11,.07), transparent 70%), #060a17';
  var FALLBACK_LIGHT =
    'radial-gradient(60% 50% at 18% 12%, rgba(30,58,138,.12), transparent 70%),' +
    'radial-gradient(50% 45% at 86% 26%, rgba(37,99,235,.10), transparent 70%),' +
    'radial-gradient(55% 45% at 55% 96%, rgba(6,182,212,.10), transparent 70%),' +
    'radial-gradient(35% 30% at 92% 90%, rgba(245,158,11,.07), transparent 70%), #f4f7fd';

  function mq(q) {
    try { return window.matchMedia(q); } catch (e) { return { matches: false }; }
  }
  function onMq(m, fn) {
    if (!m) return;
    if (m.addEventListener) m.addEventListener('change', fn);
    else if (m.addListener) m.addListener(fn);
  }
  function offMq(m, fn) {
    if (!m) return;
    if (m.removeEventListener) m.removeEventListener('change', fn);
    else if (m.removeListener) m.removeListener(fn);
  }

  // Blob centres: slow independent orbits, periods ~20-40 s.
  function centres(t, asp, out) {
    var w = Math.max(asp, 0.6);
    out[0] = -0.42 * w + 0.22 * w * Math.sin(t * 0.21);       out[1] = 0.30 + 0.12 * Math.cos(t * 0.17);
    out[2] = 0.38 * w + 0.18 * w * Math.cos(t * 0.19 + 1.3);  out[3] = 0.16 + 0.15 * Math.sin(t * 0.23 + 0.4);
    out[4] = 0.08 * w + 0.30 * w * Math.sin(t * 0.16 + 2.1);  out[5] = -0.30 + 0.12 * Math.cos(t * 0.26 + 1.7);
    out[6] = 0.52 * w + 0.14 * w * Math.sin(t * 0.29 + 4.0); out[7] = -0.38 + 0.10 * Math.cos(t * 0.20 + 2.5);
    return out;
  }

  function mountAurora(canvas) {
    if (!canvas || canvas.nodeName !== 'CANVAS') return null;
    if (canvas.__aurora) return canvas.__aurora;

    var st = canvas.style;
    st.position = 'fixed'; st.top = '0'; st.left = '0'; st.width = '100%'; st.height = '100%';
    st.zIndex = '-1'; st.pointerEvents = 'none'; st.display = 'block';
    canvas.setAttribute('aria-hidden', 'true');

    var mqLight = mq('(prefers-color-scheme: light)');
    var mqReduce = mq('(prefers-reduced-motion: reduce)');
    var root = document.documentElement;
    function isLight() {
      var t = root.getAttribute('data-theme');
      if (t === 'light') return true;
      if (t === 'dark') return false;
      return !!mqLight.matches;
    }

    var gl = null, prog = null, buf = null, loc = {}, usingFallback = false;
    var raf = 0, running = false, last = 0, prevNow = 0, elapsed = 0, seed = 0, destroyed = false;
    var cbuf = new Float32Array(8);

    function applyFallback() {
      usingFallback = true;
      canvas.classList.add('aurora-fallback');
      st.background = isLight() ? FALLBACK_LIGHT : FALLBACK_DARK;
    }

    function compile(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); return null; }
      return s;
    }

    function init() {
      if (!gl || gl.isContextLost()) return false;
      var vs = compile(gl.VERTEX_SHADER, VERT), fs = compile(gl.FRAGMENT_SHADER, FRAG);
      if (!vs || !fs) return false;
      prog = gl.createProgram();
      gl.attachShader(prog, vs); gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;
      gl.useProgram(prog);
      buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW); // one big triangle
      var aPos = gl.getAttribLocation(prog, 'aPos');
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
      loc.res = gl.getUniformLocation(prog, 'uRes');
      loc.c = gl.getUniformLocation(prog, 'uC[0]') || gl.getUniformLocation(prog, 'uC');
      loc.light = gl.getUniformLocation(prog, 'uLight');
      loc.seed = gl.getUniformLocation(prog, 'uSeed');
      canvas.width = 0; // force a resize on next draw
      return true;
    }

    function resize() {
      var dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      var w = Math.max(1, Math.round((canvas.clientWidth || window.innerWidth) * dpr));
      var h = Math.max(1, Math.round((canvas.clientHeight || window.innerHeight) * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w; canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
    }

    function draw() {
      if (usingFallback || !prog || gl.isContextLost()) return;
      resize();
      var t = T0 + elapsed / 1000;
      gl.uniform2f(loc.res, canvas.width, canvas.height);
      gl.uniform2fv(loc.c, centres(t, canvas.width / canvas.height, cbuf));
      gl.uniform1f(loc.light, isLight() ? 1 : 0);
      gl.uniform1f(loc.seed, (seed = (seed + 37.7) % 997));
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function loop(now) {
      if (!running) return;
      raf = requestAnimationFrame(loop);
      if (now - last < FRAME_MS - 1) return;
      elapsed += Math.min(now - prevNow, 100); // time only advances while visible
      prevNow = now; last = now;
      draw();
    }

    function start() {
      if (running || destroyed || usingFallback || !prog) return;
      if (mqReduce.matches || document.hidden) { draw(); return; }
      running = true;
      last = 0; prevNow = performance.now();
      raf = requestAnimationFrame(loop);
    }
    function stop() { running = false; cancelAnimationFrame(raf); }

    function onVisibility() { if (document.hidden) stop(); else start(); }
    function onReduce() { stop(); start(); }
    function onTheme() { if (usingFallback) applyFallback(); else if (!running) draw(); }
    function onResize() { if (!running && !usingFallback && prog) draw(); }
    function onLost(e) { e.preventDefault(); stop(); prog = null; }
    function onRestored() { if (init()) start(); else applyFallback(); }

    try {
      var attrs = { alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: false, preserveDrawingBuffer: false, powerPreference: 'low-power' };
      gl = canvas.getContext('webgl', attrs) || canvas.getContext('experimental-webgl', attrs);
    } catch (e) { gl = null; }
    if (!gl || !init()) applyFallback();

    var themeObserver = null;
    if (window.MutationObserver) {
      themeObserver = new MutationObserver(onTheme);
      themeObserver.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    }
    onMq(mqLight, onTheme);
    onMq(mqReduce, onReduce);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('resize', onResize);
    if (gl) {
      canvas.addEventListener('webglcontextlost', onLost, false);
      canvas.addEventListener('webglcontextrestored', onRestored, false);
    }
    start();

    var api = {
      destroy: function () {
        destroyed = true; stop();
        if (themeObserver) themeObserver.disconnect();
        offMq(mqLight, onTheme); offMq(mqReduce, onReduce);
        document.removeEventListener('visibilitychange', onVisibility);
        window.removeEventListener('resize', onResize);
        canvas.removeEventListener('webglcontextlost', onLost, false);
        canvas.removeEventListener('webglcontextrestored', onRestored, false);
        delete canvas.__aurora;
      }
    };
    canvas.__aurora = api;
    return api;
  }

  window.mountAurora = mountAurora;

  function auto() { var c = document.getElementById('aurora'); if (c) mountAurora(c); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auto);
  else auto();
})();
