#!/usr/bin/env python3
"""Build the static SEO pages of SimuCanarias (stdlib only, idempotent).

Reads data/exams/*.json and writes fully server-rendered pages to <site>/<slug>/index.html,
plus assets/seo.css and sitemap.xml. Then validates every page (one H1, JSON-LD parses,
title/description length, relative links and assets resolve, no fixed widths > 340px).

    python tools/build_seo.py           # build + validate
    python tools/build_seo.py --check   # validate only

Facts used here are taken from BOC n.º 57/2026 (Bases 21-23, Anexo II) and from the DGFP
nota informativa of 09/09/2026. Do not add numbers that are not in those sources.
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

SITE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
BASE = 'https://simucanarias.pages.dev'
LASTMOD = '2026-10-07'
OG_IMAGE = BASE + '/og.png'
GUMROAD = 'https://carrion840.gumroad.com/l/simucanarias?wanted=true'
PRICE = '5,99 €'
FREE_EXAM = 'c2-2022-libre-test2'
FREE_HREF = '../simulador#/exam/' + FREE_EXAM
SIM_HREF = '../simulador'
BOC_URL = 'https://sede.gobiernodecanarias.org/boc/boc-a-2026-057-948.pdf'
NOTA_URL = ('https://www.gobiernodecanarias.org/administracionespublicas/funcionpublica/docs_web/'
            'procesos_selectivos/procesos_2026/nota_informa_ejec_unico_C211L26_C211I26_C111L26_'
            'C111I26_E711L26_09092026.pdf')
TOTAL_QUESTIONS = 215  # all official questions in data/exams (checked in load_exams)

# Exam dates (DGFP nota informativa 09/09/2026, "previsión"). Canarias: WEST (+01:00) until 25/10.
DATES = {
    'C1': ('2026-10-17T10:00:00+01:00', 'sábado 17 de octubre de 2026', '10:00', 'C1 Administrativo · turno libre'),
    'PI': ('2026-10-17T16:00:00+01:00', 'sábado 17 de octubre de 2026', '16:00', 'C1 y C2 · promoción interna'),
    'C2': ('2026-10-31T10:00:00+00:00', 'sábado 31 de octubre de 2026', '10:00', 'C2 Auxiliar Administrativo · turno libre'),
}

ORG = {'@type': 'Organization', '@id': BASE + '/#org', 'name': 'SimuCanarias', 'url': BASE + '/'}

PAGES = [
    {'slug': 'test-auxiliar-administrativo-canarias', 'nav': 'Test Auxiliar Administrativo 2026',
     'blurb': 'Qué puedes hacer gratis, 10 preguntas oficiales de muestra y todos los recursos.'},
    {'slug': 'examen-auxiliar-administrativo-canarias-resuelto', 'nav': 'Examen Auxiliar (C2) resuelto',
     'blurb': 'El cuestionario oficial C2 de 2022 completo, con la plantilla del tribunal.'},
    {'slug': 'examen-administrativo-c1-canarias-resuelto', 'nav': 'Examen Administrativo (C1) resuelto',
     'blurb': 'La parte teórica oficial C1 (promoción interna 2024) con sus respuestas.'},
    {'slug': 'calculadora-nota-ejercicio-unico-canarias', 'nav': 'Calculadora de nota',
     'blurb': 'Tu nota en cada parte, la media y si eres apto, con la fórmula exacta de las bases.'},
    {'slug': 'penalizacion-ejercicio-unico-canarias', 'nav': 'Penalización y blancos',
     'blurb': 'Cuánto restan los fallos y cuándo compensa contestar si dudas.'},
    {'slug': 'fecha-examen-gobierno-canarias-2026', 'nav': 'Fechas del examen 2026',
     'blurb': 'Fechas, horas, plazas y cuenta atrás del ejercicio único.'},
]
SLUGS = [p['slug'] for p in PAGES]


# ----------------------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def cents(c):
    """Format hundredths as a Spanish decimal: 640 -> '6,40'."""
    sign = '−' if c < 0 else ''
    c = abs(int(round(c)))
    return f'{sign}{c // 100},{c % 100:02d}'


def mark1(a, f):  # Parte 1 · 50 preguntas · +0,20 · −0,20 por grupo completo de 3 fallos (Base 22.5)
    return max(0, (a - f // 3) * 20)


def mark2(a, f):  # Parte 2 · 25 preguntas · +0,40 · −0,40 por grupo completo de 2 fallos (Base 23.6)
    return max(0, (a - f // 2) * 40)


def jsonld(graph):
    data = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False, indent=1)
    return '<script type="application/ld+json">\n' + data.replace('</', '<\\/') + '\n</script>'


def url_of(slug):
    return f'{BASE}/{slug}/'


def page_of(slug):
    return next(p for p in PAGES if p['slug'] == slug)


def load_exams():
    exams = {}
    folder = os.path.join(SITE, 'data', 'exams')
    total = 0
    for name in sorted(os.listdir(folder)):
        if name.endswith('.json'):
            with open(os.path.join(folder, name), encoding='utf-8') as fh:
                d = json.load(fh)
            exams[d['id']] = d
            total += sum(len(b['questions']) for b in d['blocks'])
    assert total == TOTAL_QUESTIONS, f'question bank changed: {total} != {TOTAL_QUESTIONS}'
    return exams


def questions(exam):
    return [q for b in exam['blocks'] for q in b['questions']]


# ----------------------------------------------------------------------------- shared CSS
SEO_CSS = r"""/* SimuCanarias · seo.css — static guide / exam pages. GENERATED by tools/build_seo.py: edit there.
   Builds on assets/app.css tokens (glass dark/light). Mobile-first, no fixed widths. */
.skip { position: absolute; left: -9999px; top: 8px; z-index: 100; padding: 10px 14px; border-radius: 10px; background: var(--surface); color: var(--fg); }
.skip:focus { left: 8px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
header.site nav.top .btn.small { white-space: nowrap; }

.seo { padding-top: 14px; padding-bottom: 8px; }
.seo > section { margin: 30px 0; }
.seo > section > h2 { margin-bottom: 12px; }
.sec h2 { margin-top: 0; }
.sec h3 { margin-top: 18px; }
.sec ul, .sec ol { padding-left: 22px; margin: 0 0 12px; }
.sec li { margin: 6px 0; }
.sec ul.check { padding-left: 0; }

/* breadcrumb */
.crumbs ol { list-style: none; display: flex; flex-wrap: wrap; gap: 2px 8px; padding: 0; margin: 4px 0 6px; font-size: .86rem; color: var(--muted); }
.crumbs li { display: inline-flex; align-items: center; min-width: 0; }
.crumbs li + li::before { content: "›"; margin-right: 8px; opacity: .7; }
.crumbs a { color: var(--muted); text-decoration: none; display: inline-flex; align-items: center; min-height: 32px; }
.crumbs a:hover { color: var(--fg); text-decoration: underline; }

/* hero */
.hero { padding: 6px 0 4px; }
.eyebrow {
  display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0 0;
  font: 600 .8rem/1.4 var(--font-body); letter-spacing: .01em; color: var(--brand);
  padding: 4px 12px; border-radius: 999px; background: var(--brand-soft); border: 1px solid var(--brand-line);
}
.hero .lead { margin-bottom: 4px; }
.trust { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 0; margin: 12px 0 0; font-size: .88rem; color: var(--muted); }
.trust li::before { content: "✓"; color: var(--ok); font-weight: 800; margin-right: 6px; }
.when { margin: 14px 0 0; font-size: .9rem; color: var(--muted); }
.when strong { color: var(--fg); font-weight: 600; }
.when .days { color: var(--brand); font-weight: 600; }
.srcline { font-size: .86rem; color: var(--muted); margin: 10px 0 0; overflow-wrap: anywhere; }
.srcline a { color: var(--muted); }
.srcline a:hover { color: var(--fg); }

/* buttons */
.btn.xl { min-height: 56px; padding: 14px 24px; font-size: 1.06rem; border-radius: 16px; }
@media (max-width: 560px) {
  .cta-row .btn, .cta-band .btn, .pass .btn { width: 100%; }
}

/* cta band + pass card */
.cta-band { text-align: center; border-color: var(--brand-line); background: linear-gradient(135deg, var(--brand-soft), transparent 70%), var(--glass); }
.cta-band .cta-title { font: 800 clamp(1.2rem, 4vw, 1.5rem)/1.25 var(--font-head); letter-spacing: -.015em; margin: 0 0 8px; color: var(--fg); }
.cta-band .cta-row { justify-content: center; margin: 16px 0 8px; }
.cta-band .small { margin: 6px 0 0; }
.pass { border-color: color-mix(in srgb, var(--sun) 45%, transparent); background: linear-gradient(135deg, var(--sun-soft), transparent 70%), var(--glass); }
.pass .kicker { font: 700 .82rem/1.3 var(--font-body); letter-spacing: .04em; text-transform: uppercase; color: var(--warn); margin: 0 0 2px; }
.pass .price { margin: 4px 0 8px; }

/* tables */
.tw { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 8px 0 14px; }
table.t { width: 100%; border-collapse: collapse; font-size: .93rem; font-variant-numeric: tabular-nums; }
.t caption { text-align: left; font: 700 .98rem/1.3 var(--font-head); padding: 0 0 6px; color: var(--fg); }
.t th, .t td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.t th { font: 600 .8rem/1.3 var(--font-body); color: var(--muted); }
.t .n { text-align: right; white-space: nowrap; }
.t tr:last-child td { border-bottom: 0; }
@media (max-width: 400px) { table.t { font-size: .86rem; } .t th, .t td { padding: 8px 5px; } }
@media (max-width: 359px) {
  table.t { font-size: .8rem; } .t th, .t td { padding: 7px 3px; }
  header.site .logo { font-size: 1rem; gap: 8px; }
  header.site nav.top .btn.small { padding: 8px 10px; font-size: .86rem; }
}

/* quotes from the bases */
blockquote.base { margin: 12px 0; padding: 12px 16px; border-left: 4px solid var(--brand); background: var(--inset); border-radius: 0 12px 12px 0; }
blockquote.base p { margin: 0 0 4px; }
blockquote.base footer { font-size: .84rem; color: var(--muted); }

/* questions (static, read-only) */
.qa {
  background: var(--glass); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px; margin: 12px 0; box-shadow: var(--shadow); scroll-margin-top: 16px;
  -webkit-backdrop-filter: blur(14px) saturate(140%); backdrop-filter: blur(14px) saturate(140%);
}
.qa-stem { font-weight: 500; line-height: 1.6; white-space: pre-line; overflow-wrap: anywhere; margin: 0 0 10px; }
.qa .num { font-family: var(--font-head); font-weight: 800; color: var(--brand); margin-right: 4px; }
.opts { list-style: none; padding: 0; margin: 0; }
.opts li {
  display: flex; gap: 10px; align-items: flex-start; margin: 6px 0; padding: 10px 12px;
  background: var(--inset); border: 1px solid var(--line); border-radius: var(--radius-sm); line-height: 1.5;
}
.opts li > .t-opt { flex: 1; min-width: 0; overflow-wrap: anywhere; padding-top: 1px; }
.opts .l {
  flex: none; display: inline-grid; place-items: center; min-width: 28px; height: 26px; padding: 0 6px;
  border-radius: 8px; background: var(--glass-2); border: 1px solid var(--line); color: var(--muted);
  font: 700 .84rem/1 var(--font-head);
}
.opts li.ok { border-color: var(--ok); background: var(--ok-soft); }
.opts li.ok .l { background: var(--ok); color: var(--bg); border-color: transparent; }
.opts li.ok::after {
  content: "✓"; flex: none; align-self: center; display: grid; place-items: center; width: 22px; height: 22px;
  border-radius: 50%; background: var(--ok); color: var(--bg); font: 800 .75rem/1 var(--font-body);
}
.qa-key { margin: 8px 0 0; font-size: .86rem; color: var(--muted); }
.qa-key strong { color: var(--ok); }
body.hide-ans .opts li.ok { border-color: var(--line); background: var(--inset); }
body.hide-ans .opts li.ok .l { background: var(--glass-2); color: var(--muted); border-color: var(--line); }
body.hide-ans .opts li.ok::after, body.hide-ans .qa-key { display: none; }
.toggle { display: flex; align-items: center; gap: 10px; min-height: 44px; margin: 4px 0; cursor: pointer; font-weight: 500; }
.toggle input { width: 20px; height: 20px; margin: 0; accent-color: var(--brand); flex: none; }
.navwrap .navgrid a { text-decoration: none; }

/* reveal + faq */
details.reveal { margin: 10px 0 0; border-top: 1px dashed var(--line); padding-top: 6px; }
details.reveal > summary, details.faq > summary {
  display: flex; align-items: center; gap: 8px; min-height: 44px; cursor: pointer; list-style: none;
  font-weight: 600; -webkit-tap-highlight-color: transparent;
}
details.reveal > summary { color: var(--brand); }
details.reveal > summary::-webkit-details-marker, details.faq > summary::-webkit-details-marker { display: none; }
details.reveal > summary::before, details.faq > summary::before {
  content: ""; flex: none; width: 8px; height: 8px; margin: 0 4px 0 2px;
  border-right: 2px solid currentColor; border-bottom: 2px solid currentColor;
  transform: rotate(-45deg); transition: transform .2s ease; opacity: .75;
}
details.reveal[open] > summary::before, details.faq[open] > summary::before { transform: rotate(45deg); }
details.faq { border-bottom: 1px solid var(--line); padding: 2px 0; }
details.faq:last-child { border-bottom: 0; }
details.faq > div { padding: 0 0 10px 22px; }
details.faq > div p:last-child { margin-bottom: 0; }

/* link cards */
.links { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 12px; }
a.lcard {
  display: block; padding: 16px; border-radius: var(--radius); border: 1px solid var(--line); background: var(--glass);
  color: var(--fg); text-decoration: none; transition: border-color .15s ease, transform .15s ease, background-color .15s ease;
  -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
}
a.lcard:hover { border-color: var(--brand-line); background: var(--glass-2); transform: translateY(-1px); }
a.lcard strong { display: block; font: 700 1.02rem/1.3 var(--font-head); margin-bottom: 4px; }
a.lcard span { display: block; color: var(--muted); font-size: .9rem; line-height: 1.45; }
a.lcard span::after { content: " →"; color: var(--brand); }

/* share */
.share { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 26px 0 6px; }
.share > span { width: 100%; font-weight: 600; }
.share .btn { flex: 1 1 auto; }

/* calculator */
.calc fieldset { border: 1px solid var(--line); border-radius: var(--radius-sm); padding: 12px 14px 14px; margin: 0 0 14px; min-width: 0; background: var(--inset); }
.calc legend { font: 700 1rem/1.3 var(--font-head); padding: 0 6px; }
.calc .fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.calc label, .calc .flabel { display: block; font-size: .84rem; color: var(--muted); margin-bottom: 4px; }
.calc input, .calc output.box {
  display: block; width: 100%; min-height: 48px; padding: 10px 12px; font: 600 1.1rem/1.2 var(--font-body);
  font-variant-numeric: tabular-nums; color: var(--fg); background: var(--glass); border: 1px solid var(--line); border-radius: 12px;
}
.calc output.box { display: flex; align-items: center; color: var(--muted); }
.calc input:focus { outline: none; border-color: var(--brand); box-shadow: 0 0 0 3px var(--ring); }
.calc .res { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin: 12px 0 4px; }
.calc .mark { font: 800 1.9rem/1.1 var(--font-head); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.calc .detail { font-size: .88rem; color: var(--muted); margin: 4px 0 0; }
.calc .verdict { margin-top: 4px; }
.calc .mean { font: 800 2.2rem/1.1 var(--font-head); letter-spacing: -.03em; font-variant-numeric: tabular-nums; }

/* countdown */
.cd-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px; margin: 18px 0 0; }
.cd-card { padding: 16px; border-radius: var(--radius); border: 1px solid var(--line); background: var(--glass); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); }
.cd-card.main { border-color: var(--brand-line); background: linear-gradient(135deg, var(--brand-soft), transparent 75%), var(--glass); }
.cd-card .who { font-size: .86rem; color: var(--muted); margin: 0 0 4px; }
.cd-card .day { font: 800 1.25rem/1.25 var(--font-head); margin: 0; }
.cd-card .cd { display: block; margin-top: 6px; font: 700 .98rem/1.3 var(--font-body); color: var(--brand); font-variant-numeric: tabular-nums; }

/* footer */
.foot-links { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 0; margin: 0 0 14px; }
.foot-links a { display: inline-flex; align-items: center; min-height: 36px; text-decoration: none; }
.foot-links a:hover { text-decoration: underline; }
.foot-links a[aria-current] { color: var(--fg); }
"""

# ----------------------------------------------------------------------------- shared JS
SHARED_JS = r"""<script>
(function () {
  var now = Date.now();
  document.querySelectorAll('[data-days]').forEach(function (el) {
    var t = Date.parse(el.getAttribute('data-days'));
    if (isNaN(t)) return;
    var ms = t - now, d = Math.ceil(ms / 864e5);
    el.textContent = ms <= 0 ? ' (fecha ya pasada)' : ms < 864e5 ? ' (es hoy o mañana)' : ' (faltan ' + d + ' días)';
    el.hidden = false;
  });
  if (navigator.clipboard) document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.hidden = false;
    b.addEventListener('click', function () {
      navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function () {
        b.textContent = '¡Enlace copiado!';
        setTimeout(function () { b.textContent = 'Copiar enlace'; }, 1600);
      });
    });
  });
  var hide = document.getElementById('hide-ans');
  if (hide) {
    hide.closest('label').hidden = false;
    hide.addEventListener('change', function () { document.body.classList.toggle('hide-ans', hide.checked); });
  }
})();
</script>"""

COUNTDOWN_JS = r"""<script>
(function () {
  var els = document.querySelectorAll('[data-cd]');
  function tick() {
    var now = Date.now();
    els.forEach(function (el) {
      var t = Date.parse(el.getAttribute('data-cd'));
      if (isNaN(t)) return;
      var ms = t - now;
      if (ms <= 0) { el.textContent = 'Fecha prevista ya pasada'; el.hidden = false; return; }
      var m = Math.floor(ms / 6e4), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mi = m % 60;
      el.textContent = 'Faltan ' + d + ' d ' + h + ' h ' + mi + ' min';
      el.hidden = false;
    });
  }
  tick();
  setInterval(tick, 30000);
})();
</script>"""

CALC_JS = r"""<script>
(function () {
  function $(id) { return document.getElementById(id); }
  function fmt(c) { return (c / 100).toFixed(2).replace('.', ','); }
  var PARTS = [
    { k: '1', n: 50, g: 3, v: 20 },  // Parte 1: +0,20 · −0,20 por cada 3 fallos (Base 22.5)
    { k: '2', n: 25, g: 2, v: 40 }   // Parte 2: +0,40 · −0,40 por cada 2 fallos (Base 23.6)
  ];
  function num(el, max) {
    var raw = el.value.trim(), v = parseInt(raw, 10);
    if (isNaN(v)) v = 0;
    v = Math.max(0, Math.min(max, v));
    if (raw !== '' && String(v) !== raw) el.value = v;
    return v;
  }
  function part(p) {
    var aEl = $('a' + p.k), fEl = $('f' + p.k);
    var a = num(aEl, p.n);
    var f = num(fEl, p.n - a);
    aEl.max = p.n - f; fEl.max = p.n - a;
    var groups = Math.floor(f / p.g);
    // mark = max(0, value*a − value*floor(f/g)), in hundredths to avoid float noise
    var c = Math.max(0, (a - groups) * p.v);
    $('b' + p.k).textContent = p.n - a - f;
    $('m' + p.k).textContent = fmt(c);
    $('x' + p.k).textContent = a + ' × ' + fmt(p.v) + ' = ' + fmt(a * p.v) + ' · penalización ' + fmt(groups * p.v) +
      ' (' + groups + (groups === 1 ? ' grupo' : ' grupos') + ' de ' + p.g + ' fallos)';
    var free = p.g - 1 - (f % p.g);
    $('n' + p.k).textContent = a + f >= p.n ? 'Has contestado todas las preguntas.' :
      free === 0 ? 'El próximo fallo te resta ' + fmt(p.v) + '.' :
      'Te ' + (free === 1 ? 'queda 1 fallo' : 'quedan ' + free + ' fallos') + ' «gratis»: el siguiente grupo aún no está completo.';
    var t = $('t' + p.k), ok = c >= 500;
    t.className = 'tag ' + (ok ? 'ok' : 'bad');
    t.textContent = ok ? 'Parte superada (≥ 5)' : 'Parte no superada (< 5)';
    return c;
  }
  function run() {
    var c1 = part(PARTS[0]), c2 = part(PARTS[1]);
    var mean = Math.round((c1 + c2) / 2);
    $('mm').textContent = fmt(mean);
    var ok = c1 >= 500 && c2 >= 500 && mean >= 500, v = $('vv');
    v.className = 'verdict ' + (ok ? 'ok' : 'bad');
    v.textContent = ok ? 'APTO: superas las dos partes y la media.' :
      (c1 < 500 && c2 < 500) ? 'NO APTO: no llegas al 5 en ninguna de las dos partes.' :
      c1 < 500 ? 'NO APTO: necesitas al menos un 5 en la parte 1 (test).' :
      'NO APTO: necesitas al menos un 5 en la parte 2 (supuesto).';
  }
  ['a1', 'f1', 'a2', 'f2'].forEach(function (id) { $(id).addEventListener('input', run); });
  run();
})();
</script>"""

GH_REDIRECT = ('<script>if(/github\\.io$/.test(location.hostname)){location.replace("https://simucanarias.pages.dev"'
               '+location.pathname.replace(/^\\/simucanarias/,"").replace(/index\\.html$/,"")+location.search+location.hash)}</script>')
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' "
           "height='32' rx='8' fill='%230a5cc2'/%3E%3Ctext x='16' y='22' font-size='16' text-anchor='middle' "
           "fill='white' font-family='Arial' font-weight='bold'%3ES%3C/text%3E%3C/svg%3E")


# ----------------------------------------------------------------------------- page chrome
def breadcrumb_ld(slug, name):
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Inicio', 'item': BASE + '/'},
        {'@type': 'ListItem', 'position': 2, 'name': name, 'item': url_of(slug)},
    ]}


def article_ld(slug, headline, desc):
    return {'@type': 'Article', 'headline': headline[:110], 'description': desc, 'inLanguage': 'es',
            'datePublished': LASTMOD, 'dateModified': LASTMOD, 'image': OG_IMAGE,
            'author': ORG, 'publisher': ORG, 'mainEntityOfPage': url_of(slug), 'isAccessibleForFree': True}


def faq_ld(faqs):
    return {'@type': 'FAQPage', 'mainEntity': [
        {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'<[^>]+>', '', a)}}
        for q, a in faqs]}


def quiz_ld(slug, name, desc, exam, qs, level, about):
    parts = []
    for q in qs:
        keys = list(q['options'])
        part = {'@type': 'Question', 'eduQuestionType': 'Multiple choice', 'position': q['n'], 'text': q['stem'],
                'suggestedAnswer': [{'@type': 'Answer', 'position': i, 'text': q['options'][k]}
                                    for i, k in enumerate(keys) if k != q['answer']]}
        if not q.get('annulled'):
            part['acceptedAnswer'] = {'@type': 'Answer', 'position': keys.index(q['answer']),
                                      'text': q['options'][q['answer']]}
        parts.append(part)
    return {'@type': 'Quiz', 'name': name, 'description': desc, 'url': url_of(slug), 'inLanguage': 'es',
            'educationalLevel': level, 'learningResourceType': 'Examen oficial resuelto',
            'isAccessibleForFree': True, 'about': {'@type': 'Thing', 'name': about},
            'isBasedOn': {'@type': 'CreativeWork', 'name': exam['title'], 'url': exam['source_url']},
            'provider': ORG, 'hasPart': parts}


def faq_html(faqs):
    return '\n'.join(f'<details class="faq"><summary>{esc(q)}</summary><div><p>{a}</p></div></details>'
                     for q, a in faqs)


def when_strip():
    c1, c2 = DATES['C1'], DATES['C2']
    return (f'<p class="when">Fechas previstas · C1 turno libre: <strong>sáb. 17 oct</strong>'
            f'<span class="days" data-days="{c1[0]}" hidden></span> · C2 turno libre: <strong>sáb. 31 oct</strong>'
            f'<span class="days" data-days="{c2[0]}" hidden></span> · '
            f'<a href="../fecha-examen-gobierno-canarias-2026/">ver fechas y horas</a></p>')


TRUST = ('<ul class="trust"><li>Sin registro</li><li>Funciona en el móvil</li>'
         '<li>Tus respuestas no salen de tu navegador</li><li>Herramienta independiente, no oficial</li></ul>')


def hero(eyebrow, h1, lead, ctas, extra=''):
    return f"""<header class="hero">
<p class="eyebrow">{eyebrow}</p>
<h1>{h1}</h1>
<p class="lead">{lead}</p>
<div class="cta-row">{ctas}</div>
{TRUST}
{extra}{when_strip()}
</header>"""


def btn_free(label='Hazlo cronometrado y con corrección automática (gratis)', cls='btn xl'):
    return f'<a class="{cls}" href="{FREE_HREF}">{esc(label)}</a>'


def btn_pass(label=None, cls='btn sun xl'):
    label = label or f'Conseguir el pase · {PRICE}'
    return f'<a class="{cls}" href="{GUMROAD}" target="_blank" rel="noopener">{esc(label)}</a>'


def cta_band(title, text, primary=None, secondary=None):
    primary = primary or btn_free()
    secondary = secondary if secondary is not None else ''
    return f"""<div class="card cta-band">
<p class="cta-title">{title}</p>
<p class="muted">{text}</p>
<div class="cta-row">{primary}{secondary}</div>
<p class="small muted">Sin registro · Corrección con las reglas de 2026 (BOC n.º 57/2026) · Herramienta independiente, no oficial</p>
</div>"""


def pass_card(heading_tag='p', heading='Pase hasta el examen · C1 + C2'):
    return f"""<div class="card pass">
<{heading_tag} class="kicker">{heading}</{heading_tag}>
<p class="price">{PRICE} <small>pago único · IVA incl. · reembolso en 14 días</small></p>
<ul class="check">
<li>{TOTAL_QUESTIONS} preguntas oficiales de 6 exámenes: C2 (test y supuestos) y C1 (tests y supuestos A/B)</li>
<li>Simulacro completo cronometrado: test + 1 de 2 supuestos oficiales (100 min en C1; 80 en C2, cuyos supuestos oficiales tienen 10 preguntas)</li>
<li>Modo «solo parte 2» para quien conserva la nota del primer ejercicio</li>
<li>Tests aleatorios con todo el banco oficial y repaso de falladas</li>
<li>Historial de notas e informe de estrategia de blancos</li>
</ul>
<div class="cta-row">{btn_pass()}</div>
<p class="small muted">Pago seguro con Gumroad (tarjeta, PayPal, Apple Pay o Google Pay). Recibes al momento una clave por email y la pegas en el simulador. Sin suscripción.</p>
</div>"""


def related(current):
    cards = []
    for p in PAGES:
        if p['slug'] == current:
            continue
        cards.append(f'<a class="lcard" href="../{p["slug"]}/"><strong>{esc(p["nav"])}</strong><span>{esc(p["blurb"])}</span></a>')
    cards.append('<a class="lcard" href="../simulador"><strong>Abrir el simulador</strong>'
                 '<span>Exámenes oficiales cronometrados y corregidos con las reglas de 2026.</span></a>')
    return '<div class="links">' + '\n'.join(cards) + '</div>'


def share(slug, text):
    url = url_of(slug)
    wa = 'https://wa.me/?text=' + quote(f'{text} {url}')
    tg = 'https://t.me/share/url?url=' + quote(url, safe='') + '&text=' + quote(text)
    return f"""<div class="share">
<span>¿Te ha servido? Compártelo con tu grupo de estudio:</span>
<a class="btn ghost small" href="{esc(wa)}" target="_blank" rel="noopener">WhatsApp</a>
<a class="btn ghost small" href="{esc(tg)}" target="_blank" rel="noopener">Telegram</a>
<button class="btn ghost small" type="button" data-copy="{esc(url)}" hidden>Copiar enlace</button>
</div>"""


def footer(current):
    items = ['<li><a href="../">Inicio</a></li>', '<li><a href="../simulador">Simulador</a></li>']
    for p in PAGES:
        cur = ' aria-current="page"' if p['slug'] == current else ''
        items.append(f'<li><a href="../{p["slug"]}/"{cur}>{esc(p["nav"])}</a></li>')
    return f"""<footer class="site"><div class="wrap">
<nav aria-label="Guías y exámenes resueltos"><ul class="foot-links">{''.join(items)}</ul></nav>
<p>SimuCanarias es una herramienta independiente, no oficial, sin relación con el Gobierno de Canarias, su Dirección General de la Función Pública ni sus tribunales. Las preguntas proceden de exámenes publicados por la propia Administración y enlazan a su PDF original. · <a href="../aviso-legal">Aviso legal y privacidad</a></p>
</div></footer>"""


def render(slug, title, desc, crumb, body, graph, og_type='article', scripts=''):
    assert len(title) <= 60, f'{slug}: title {len(title)} chars'
    assert len(desc) <= 155, f'{slug}: description {len(desc)} chars'
    canon = url_of(slug)
    graph = [breadcrumb_ld(slug, crumb)] + graph
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
{GH_REDIRECT}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="SimuCanarias">
<meta property="og:locale" content="es_ES">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="icon" href="{FAVICON}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#060a17" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f4f7fd" media="(prefers-color-scheme: light)">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap">
<link rel="stylesheet" href="../assets/app.css">
<link rel="stylesheet" href="../assets/seo.css">
{jsonld(graph)}
</head>
<body>
<canvas id="aurora" aria-hidden="true"></canvas>
<a class="skip" href="#main">Saltar al contenido</a>
<header class="site"><div class="wrap">
<a class="logo" href="../"><span class="logo-mark">S</span>SimuCanarias</a>
<nav class="top" aria-label="Principal"><span class="indep">Herramienta independiente, no oficial</span><a class="btn small" href="{SIM_HREF}">Abrir simulador</a></nav>
</div></header>
<main id="main" class="wrap narrow seo">
<nav class="crumbs" aria-label="Migas de pan"><ol><li><a href="../">Inicio</a></li><li aria-current="page">{esc(crumb)}</li></ol></nav>
{body}
</main>
{footer(slug)}
<script src="../assets/bg.js" defer></script>
{SHARED_JS}
{scripts}</body>
</html>
"""


# ----------------------------------------------------------------------------- question rendering
def q_card(q, anchor=True):
    lis = []
    for k, text in q['options'].items():
        ok = (k == q['answer'] and not q.get('annulled'))
        cls = ' class="ok"' if ok else ''
        sr = '<span class="sr"> (respuesta oficial)</span>' if ok else ''
        lis.append(f'<li{cls}><span class="l">{esc(k)}</span><span class="t-opt">{esc(text)}{sr}</span></li>')
    if q.get('annulled'):
        key = '<p class="qa-key">Pregunta <strong>anulada</strong> por el tribunal.</p>'
    else:
        key = f'<p class="qa-key">Respuesta oficial: <strong>{esc(q["answer"])})</strong> {esc(q["options"][q["answer"]])}</p>'
    if q.get('note'):
        key += f'<p class="qa-key">{esc(q["note"])}</p>'
    ident = f' id="p{q["n"]}"' if anchor else ''
    return (f'<div class="qa"{ident}><p class="qa-stem"><span class="num">{q["n"]}.</span> {esc(q["stem"])}</p>'
            f'<ol class="opts">{"".join(lis)}</ol>{key}</div>')


def q_nav(qs):
    links = ''.join(f'<a href="#p{q["n"]}">{q["n"]}</a>' for q in qs)
    return (f'<details class="navwrap"><summary>Ir a una pregunta ({len(qs)})</summary>'
            f'<div class="navgrid">{links}</div></details>')


HIDE_TOGGLE = ('<label class="toggle" hidden><input type="checkbox" id="hide-ans"> '
               'Ocultar las respuestas para hacer el test por mi cuenta</label>')


# ----------------------------------------------------------------------------- pages
def page_exam_c2(exams):
    slug = 'examen-auxiliar-administrativo-canarias-resuelto'
    ex = exams[FREE_EXAM]
    qs = questions(ex)
    ordinary = [q for q in qs if not q['reserve']]
    reserve = [q for q in qs if q['reserve']]
    assert len(ordinary) == 50 and len(reserve) == 4
    title = 'Examen Auxiliar Administrativo Gobierno de Canarias resuelto'
    desc = ('Examen oficial de Auxiliar Administrativo (C2) del Gobierno de Canarias: 54 preguntas con la '
            'plantilla del tribunal. Hazlo cronometrado gratis.')
    h1 = 'Examen Auxiliar Administrativo del Gobierno de Canarias resuelto'
    src = (f'<p class="srcline">Fuente: <a href="{esc(ex["source_url"])}" target="_blank" rel="noopener">'
           f'relación oficial de preguntas y respuestas (PDF, gobiernodecanarias.org)</a> · publicada el {esc(ex["published"])}</p>')
    first, second = ordinary[:25], ordinary[25:]
    body = hero(
        'Examen oficial · C2 turno libre · Convocatoria 2022',
        esc(h1),
        ('Cuestionario n.º 2 del primer ejercicio de Auxiliar Administrativo (C2, turno libre, convocatoria '
         'BOC n.º 245/2022): las <strong>50 preguntas y las 4 de reserva</strong>, con la respuesta correcta según la '
         f'plantilla oficial del tribunal, publicada el {esc(ex["published"])}.'),
        btn_free() + '<a class="btn ghost xl" href="../calculadora-nota-ejercicio-unico-canarias/">Calcular mi nota</a>',
        src)
    body += f"""
<section class="card sec" aria-labelledby="h-que">
<h2 id="h-que">Qué es este examen y de dónde sale</h2>
<p>Es un examen real. La Dirección General de la Función Pública del Gobierno de Canarias publicó la relación de preguntas y respuestas del cuestionario n.º 2 de Auxiliar Administrativo (turno libre) y aquí lo tienes completo, en texto y legible en el móvil, con la <strong>opción correcta marcada en verde</strong> tal como figura en la plantilla oficial del tribunal.</p>
<div class="kpis"><div class="kpi"><b>50 + 4</b><span>preguntas + reserva</span></div><div class="kpi"><b>4</b><span>opciones por pregunta</span></div><div class="kpi"><b>{esc(ex["published"])}</b><span>plantilla publicada</span></div></div>
<p>La respuesta marcada es la oficial de 2024. Si alguna norma ha cambiado desde entonces, compruébala con el texto legal vigente: para el examen de 2026 cuenta la normativa actual.</p>
<p class="srcline">PDF original: <a href="{esc(ex["source_url"])}" target="_blank" rel="noopener">{esc(ex["source_url"])}</a></p>
</section>

<section class="card sec" aria-labelledby="h-reglas">
<h2 id="h-reglas">Cómo se puntuaría con las reglas de 2026</h2>
<p>En el ejercicio único de 2026 (<a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57/2026</a>), la primera parte es un test de 50 preguntas: <strong>+0,20 por acierto</strong> y <strong>−0,20 por cada grupo completo de 3 fallos</strong>. Las preguntas en blanco no restan. Necesitas al menos un 5, por ejemplo, 25 aciertos sin pasar de 2 fallos.</p>
<p>Calcula tu resultado en la <a href="../calculadora-nota-ejercicio-unico-canarias/">calculadora de nota</a> o mira <a href="../penalizacion-ejercicio-unico-canarias/">cuándo compensa contestar si dudas</a>.</p>
</section>

<section aria-labelledby="h-preg">
<h2 id="h-preg">Preguntas y respuestas oficiales (1 a 50)</h2>
{HIDE_TOGGLE}
{q_nav(qs)}
{''.join(q_card(q) for q in first)}
{cta_band('¿Vas por la mitad? Hazlo de verdad, contra el reloj',
          'El mismo examen en el simulador: cronómetro, corrección automática con las reglas de 2026, nota al instante y revisión pregunta a pregunta. Gratis.')}
{''.join(q_card(q) for q in second)}
</section>

<section aria-labelledby="h-res">
<h2 id="h-res">Preguntas de reserva (51 a 54)</h2>
<p>Solo puntúan si se anula alguna de las 50 ordinarias, por el orden en que se formularon.</p>
{''.join(q_card(q) for q in reserve)}
{src}
</section>

<section aria-labelledby="h-cta">
<h2 id="h-cta">Hazlo cronometrado y con corrección automática</h2>
{cta_band('Ensaya el examen como el día D, gratis',
          'Te ponemos el reloj, te corregimos con las reglas de 2026 y te decimos dónde pierdes nota. Marca las dudosas y al corregir verás si te habría compensado dejarlas en blanco.')}
</section>

<section aria-labelledby="h-mas">
<h2 id="h-mas">¿Quieres más exámenes oficiales?</h2>
<p>Este examen es gratis en el simulador. Con el pase desbloqueas todos los demás: los supuestos prácticos de C2, los tests y supuestos A/B de C1 y los simulacros completos cronometrados (test + supuesto).</p>
{pass_card()}
</section>

<section aria-labelledby="h-sigue">
<h2 id="h-sigue">Sigue preparando el examen</h2>
{related(slug)}
</section>
{share(slug, 'Examen oficial de Auxiliar Administrativo del Gobierno de Canarias resuelto, con la plantilla del tribunal:')}
"""
    graph = [quiz_ld(slug, h1, desc, ex, qs, 'C2 · Auxiliar Administrativo',
                     'Oposiciones Auxiliar Administrativo Gobierno de Canarias')]
    return slug, render(slug, title, desc, 'Examen Auxiliar (C2) resuelto', body, graph)


def page_exam_c1(exams):
    slug = 'examen-administrativo-c1-canarias-resuelto'
    ex = exams['c1-2024-pi-teorico']
    qs = questions(ex)
    ordinary = [q for q in qs if not q['reserve']]
    reserve = [q for q in qs if q['reserve']]
    assert len(ordinary) == 25 and len(reserve) == 4
    title = 'Examen Administrativo C1 Canarias resuelto (con respuestas)'
    desc = ('Examen oficial de Administrativo C1 del Gobierno de Canarias (promoción interna 2024, parte teórica): '
            '29 preguntas con la plantilla del tribunal.')
    h1 = 'Examen Administrativo C1 del Gobierno de Canarias resuelto'
    src = (f'<p class="srcline">Fuente: <a href="{esc(ex["source_url"])}" target="_blank" rel="noopener">'
           f'respuestas oficiales del test teórico (PDF, gobiernodecanarias.org)</a> · publicadas el {esc(ex["published"])}</p>')
    body = hero(
        'Examen oficial · C1 promoción interna · Convocatoria 2024',
        esc(h1),
        ('Parte teórica del ejercicio único de Administrativo (C1), promoción interna, convocatoria BOC n.º 239/2024: '
         '<strong>25 preguntas y 4 de reserva</strong>, con la respuesta correcta según la plantilla oficial publicada '
         f'el {esc(ex["published"])}.'),
        btn_pass(f'Simulacro C1 completo · {PRICE}') +
        btn_free('Probar gratis un examen oficial completo', 'btn ghost xl'),
        src)
    body += f"""
<section class="card sec" aria-labelledby="h-que">
<h2 id="h-que">Qué es este examen</h2>
<p>Es el test teórico oficial del ejercicio único de promoción interna al Cuerpo Administrativo (C1) de la convocatoria de 2024. Cada pregunta tiene <strong>3 opciones</strong>; en el turno libre de 2026 cada pregunta tiene 4 (Base 22.3 del <a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57/2026</a>).</p>
<div class="kpis"><div class="kpi"><b>25 + 4</b><span>preguntas + reserva</span></div><div class="kpi"><b>3</b><span>opciones por pregunta</span></div><div class="kpi"><b>{esc(ex["published"])}</b><span>plantilla publicada</span></div></div>
<p>Sé realista: los exámenes C1 publicados son de promoción interna. Sirven para practicar el formato, la gestión del tiempo y la normativa común, pero no cubren todo el temario del turno libre. Si te presentas por promoción interna, revisa también las bases de tu convocatoria.</p>
</section>

<section aria-labelledby="h-preg">
<h2 id="h-preg">Preguntas y respuestas oficiales (1 a 25)</h2>
{HIDE_TOGGLE}
{q_nav(qs)}
{''.join(q_card(q) for q in ordinary[:13])}
{cta_band('El simulacro C1 completo está en el pase',
          'Este test, más la parte práctica oficial (supuestos A y B, 25 preguntas cada uno) cronometrada y corregida con las reglas de 2026, y el test C1 de promoción interna de 2022.',
          btn_pass(f'Desbloquear el C1 · {PRICE}'), btn_free('O prueba gratis el examen C2', 'btn ghost xl'))}
{''.join(q_card(q) for q in ordinary[13:])}
</section>

<section aria-labelledby="h-res">
<h2 id="h-res">Preguntas de reserva (26 a 29)</h2>
<p>Solo puntúan si se anula alguna de las ordinarias, por el orden en que se formularon.</p>
{''.join(q_card(q) for q in reserve)}
{src}
</section>

<section aria-labelledby="h-pase">
<h2 id="h-pase">Simulacro C1 completo: test + supuestos A/B</h2>
<p>En el simulador, con el pase, haces el ejercicio único C1 como el día del examen: un test de 50 preguntas (las 25 de este examen más 25 del test C1 de 2022) y eliges 1 de los 2 supuestos prácticos oficiales (A o B), con 100 minutos de cronómetro, corrección automática y revisión pregunta a pregunta. Antes de pagar puedes probar gratis el examen oficial completo de C2 para ver cómo funciona.</p>
{pass_card()}
{cta_band('¿Primero quieres probarlo?', 'El examen oficial C2 de 2022 (50 preguntas + reserva) es gratis, sin registro. La parte general comparte gran parte de la normativa con el C1.')}
</section>

<section aria-labelledby="h-sigue">
<h2 id="h-sigue">Sigue preparando el examen</h2>
{related(slug)}
</section>
{share(slug, 'Examen oficial de Administrativo C1 del Gobierno de Canarias resuelto:')}
"""
    graph = [quiz_ld(slug, h1, desc, ex, qs, 'C1 · Administrativo', 'Oposiciones Administrativo C1 Gobierno de Canarias')]
    return slug, render(slug, title, desc, 'Examen Administrativo (C1) resuelto', body, graph)


CALC_FAQS = [
    ('¿Cómo se calcula la nota del test (primera parte)?',
     'Cada acierto suma 0,20 puntos y por cada grupo completo de 3 fallos se restan 0,20 (Base 22.5). '
     'Nota = 0,20 × aciertos − 0,20 × (fallos ÷ 3, sin decimales), entre 0 y 10. '
     'Ejemplo: 35 aciertos y 10 fallos dan 7,00 − 0,60 = 6,40.'),
    ('¿Cómo se calcula la nota del supuesto práctico (segunda parte)?',
     'Cada acierto suma 0,40 puntos y por cada grupo completo de 2 fallos se restan 0,40 (Base 23.6). '
     'Ejemplo: 16 aciertos y 5 fallos dan 6,40 − 0,80 = 5,60.'),
    ('¿Las preguntas en blanco restan?',
     'No. Las preguntas no contestadas no computan a efectos de penalización (Bases 22.6 y 23.7).'),
    ('¿Qué nota necesito para aprobar el ejercicio único?',
     'Al menos un 5 en cada parte (Bases 22.7 y 23.8) y al menos un 5 de media (Base 21.5). La nota del '
     'ejercicio es la media de las dos partes, pero si suspendes una de ellas no eres apto aunque la media llegue a 5.'),
    ('¿Cuántos aciertos necesito como mínimo?',
     'En el test, 25 aciertos si no pasas de 2 fallos (cada 3 fallos más, 1 acierto más). En el supuesto, '
     '13 aciertos si no pasas de 1 fallo (cada 2 fallos más, 1 acierto más).'),
]


def calc_widget():
    def fs(k, title, n, a, f, g, v):
        groups = f // g
        c = max(0, (a - groups) * v)
        free = g - 1 - f % g
        nxt = (f'El próximo fallo te resta {cents(v)}.' if free == 0 else
               f'Te {"queda 1 fallo" if free == 1 else f"quedan {free} fallos"} «gratis»: el siguiente grupo aún no está completo.')
        ok = c >= 500
        return f"""<fieldset>
<legend>{title} ({n} preguntas)</legend>
<div class="fields">
<div><label for="a{k}">Aciertos</label><input id="a{k}" type="number" inputmode="numeric" min="0" max="{n - f}" value="{a}"></div>
<div><label for="f{k}">Fallos</label><input id="f{k}" type="number" inputmode="numeric" min="0" max="{n - a}" value="{f}"></div>
<div><span class="flabel">Blancos</span><output class="box" id="b{k}" for="a{k} f{k}">{n - a - f}</output></div>
</div>
<div class="res" aria-live="polite"><span>Nota de la parte:</span> <span class="mark" id="m{k}">{cents(c)}</span><span class="tag {'ok' if ok else 'bad'}" id="t{k}">{'Parte superada (≥ 5)' if ok else 'Parte no superada (&lt; 5)'}</span></div>
<p class="detail" id="x{k}">{a} × {cents(v)} = {cents(a * v)} · penalización {cents(groups * v)} ({groups} {'grupo' if groups == 1 else 'grupos'} de {g} fallos)</p>
<p class="detail" id="n{k}">{nxt}</p>
</fieldset>"""
    a1, f1, a2, f2 = 35, 10, 16, 5
    c1, c2 = mark1(a1, f1), mark2(a2, f2)
    mean = round((c1 + c2) / 2)
    ok = c1 >= 500 and c2 >= 500 and mean >= 500
    return f"""<form class="card calc" onsubmit="return false" aria-label="Calculadora de nota">
{fs('1', 'Parte 1 · Test', 50, a1, f1, 3, 20)}
{fs('2', 'Parte 2 · Supuesto práctico', 25, a2, f2, 2, 40)}
<div class="res"><span>Nota del ejercicio (media):</span> <span class="mean" id="mm">{cents(mean)}</span></div>
<p class="verdict {'ok' if ok else 'bad'}" id="vv" aria-live="polite">{'APTO: superas las dos partes y la media.' if ok else 'NO APTO'}</p>
<noscript><p class="small muted">Activa JavaScript para recalcular. Sin él, usa la fórmula y las tablas de abajo.</p></noscript>
</form>"""


def page_calc():
    slug = 'calculadora-nota-ejercicio-unico-canarias'
    title = 'Calculadora de nota del ejercicio único Canarias 2026'
    desc = ('Calcula tu nota del ejercicio único del Gobierno de Canarias: test de 50 (−0,20 cada 3 fallos) y '
            'supuesto de 25 (−0,40 cada 2 fallos). Gratis.')
    h1 = 'Calculadora de nota del ejercicio único (Gobierno de Canarias 2026)'
    ex1 = [(25, 0), (25, 2), (25, 3), (28, 9), (30, 10), (35, 10), (40, 8), (45, 5)]
    ex2 = [(13, 0), (13, 1), (13, 2), (15, 6), (16, 5), (18, 4), (20, 5)]

    def rows(exs, fn, n, g, v):
        out = []
        for a, f in exs:
            c = fn(a, f)
            res = 'ok' if c >= 500 else 'bad'
            label = 'apto' if c >= 500 else 'no apto'
            out.append(f'<tr><td class="n">{a}</td><td class="n">{f}</td><td class="n">{n - a - f}</td>'
                       f'<td class="n">−{cents((f // g) * v)}</td><td class="n"><span class="tag {res}">{cents(c)}'
                       f'<span class="sr"> ({label})</span></span></td></tr>')
        return ''.join(out)

    head = ('<thead><tr><th class="n" scope="col">Aciertos</th><th class="n" scope="col">Fallos</th>'
            '<th class="n" scope="col">Blancos</th><th class="n" scope="col">Resta</th><th class="n" scope="col">Nota</th></tr></thead>')
    need1 = ''.join(f'<tr><td>{lo}–{lo + 2} fallos</td><td class="n"><strong>{25 + lo // 3}</strong></td></tr>' for lo in (0, 3, 6, 9, 12))
    need2 = ''.join(f'<tr><td>{lo}–{lo + 1} fallos</td><td class="n"><strong>{13 + lo // 2}</strong></td></tr>' for lo in (0, 2, 4, 6))
    body = hero(
        'Calculadora · Reglas BOC n.º 57/2026',
        esc(h1),
        ('Pon tus aciertos y fallos y verás la nota de cada parte, la media y si eres <strong>APTO</strong>, con la '
         'fórmula exacta de las bases 22 y 23. Los blancos se calculan solos.'),
        '<a class="btn xl" href="#calculadora">Calcular mi nota</a>' + btn_free('Hacer un examen oficial gratis', 'btn ghost xl'))
    body += f"""
<section id="calculadora" aria-labelledby="h-calc">
<h2 id="h-calc">Calcula tu nota</h2>
{calc_widget()}
</section>

<section class="card sec" aria-labelledby="h-formula">
<h2 id="h-formula">La fórmula exacta</h2>
<ul>
<li><strong>Parte 1 · Test (50 preguntas):</strong> nota = máx(0; 0,20 × aciertos − 0,20 × ⌊fallos ÷ 3⌋). Base 22.5.</li>
<li><strong>Parte 2 · Supuesto práctico (25 preguntas):</strong> nota = máx(0; 0,40 × aciertos − 0,40 × ⌊fallos ÷ 2⌋). Base 23.6.</li>
<li><strong>Ejercicio:</strong> media de las dos partes. Para ser apto necesitas al menos un 5 en cada parte y de media (Bases 21.5, 22.7 y 23.8).</li>
</ul>
<p>⌊ ⌋ significa «sin decimales»: solo restan los <strong>grupos completos</strong> de fallos. Con 2 fallos en el test o 1 en el supuesto no pierdes nada. Los blancos nunca restan.</p>
<p class="srcline">Fuente: <a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57, de 24/03/2026</a> (Bases 21 a 23).</p>
</section>

<section class="card sec" aria-labelledby="h-ej">
<h2 id="h-ej">Ejemplos resueltos</h2>
<div class="tw"><table class="t"><caption>Parte 1 · Test (+0,20 · −0,20 cada 3 fallos)</caption>{head}<tbody>{rows(ex1, mark1, 50, 3, 20)}</tbody></table></div>
<div class="tw"><table class="t"><caption>Parte 2 · Supuesto (+0,40 · −0,40 cada 2 fallos)</caption>{head}<tbody>{rows(ex2, mark2, 25, 2, 40)}</tbody></table></div>
<h3>Dos ejercicios completos</h3>
<ul>
<li>Test 6,40 y supuesto 5,60 → media <strong>6,00</strong>: <strong>APTO</strong>.</li>
<li>Test 7,60 y supuesto 4,80 → media 6,20, pero <strong>NO APTO</strong>: el supuesto no llega al 5.</li>
</ul>
</section>

<section class="card sec" aria-labelledby="h-min">
<h2 id="h-min">Cuántos aciertos necesitas para aprobar cada parte</h2>
<div class="links">
<div class="tw"><table class="t"><caption>Test · mínimo para el 5</caption><thead><tr><th scope="col">Si tienes</th><th class="n" scope="col">Aciertos</th></tr></thead><tbody>{need1}</tbody></table></div>
<div class="tw"><table class="t"><caption>Supuesto · mínimo para el 5</caption><thead><tr><th scope="col">Si tienes</th><th class="n" scope="col">Aciertos</th></tr></thead><tbody>{need2}</tbody></table></div>
</div>
<p>Cada grupo completo de fallos te obliga a acertar una pregunta más. Por eso decidir bien qué dejas en blanco importa: lo explicamos en la <a href="../penalizacion-ejercicio-unico-canarias/">guía de penalización</a>.</p>
</section>

<section aria-labelledby="h-prueba">
<h2 id="h-prueba">Comprueba tu nota real con un examen oficial</h2>
{cta_band('Haz el examen oficial C2 completo y la nota se calcula sola',
          '50 preguntas + reserva, cronómetro y corrección con estas mismas reglas. Al terminar ves aciertos, fallos, blancos, penalización y si te habría compensado dejar las dudosas en blanco.')}
{pass_card()}
</section>

<section class="card sec" aria-labelledby="h-faq">
<h2 id="h-faq">Preguntas frecuentes</h2>
{faq_html(CALC_FAQS)}
</section>

<section aria-labelledby="h-sigue">
<h2 id="h-sigue">Sigue preparando el examen</h2>
{related(slug)}
</section>
{share(slug, 'Calculadora de nota del ejercicio único del Gobierno de Canarias (test + supuesto):')}
"""
    graph = [faq_ld(CALC_FAQS)]
    return slug, render(slug, title, desc, 'Calculadora de nota', body, graph, og_type='website', scripts=CALC_JS)


PEN_FAQS = [
    ('¿Cuánto resta cada fallo en el ejercicio único del Gobierno de Canarias?',
     'En el test (parte 1) se restan 0,20 puntos por cada grupo completo de 3 fallos; en el supuesto práctico '
     '(parte 2), 0,40 por cada grupo completo de 2 fallos. Con 1 o 2 fallos en el test, o 1 en el supuesto, no se resta nada.'),
    ('¿Las preguntas en blanco penalizan?',
     'No. Las bases dicen que las preguntas no contestadas no computan a efectos de penalización (Bases 22.6 y 23.7).'),
    ('¿La penalización es proporcional?',
     'No. Las bases excluyen expresamente una penalización proporcional cuando hay menos fallos que los del grupo '
     '(menos de 3 en el test o menos de 2 en el supuesto). Solo restan los grupos completos.'),
    ('¿Compensa contestar cuando dudo?',
     'En el test, si descartas al menos una opción, el valor esperado de contestar es positivo (+0,022 eligiendo entre 3; '
     '+0,067 entre 2); a ciegas entre 4 es neutro. En el supuesto, a ciegas entre 4 pierdes de media (−0,050), entre 3 es '
     'neutro y entre 2 ganas (+0,100).'),
    ('¿Qué pasa si anulan preguntas?',
     'Se sustituyen por las de reserva en el orden en que se formularon. Si se anulan más preguntas que reservas hay, '
     'cada pregunta pasa a valer de forma proporcional al número total que finalmente se valore (Bases 22.2 y 23.2).'),
]


def page_penal():
    slug = 'penalizacion-ejercicio-unico-canarias'
    title = 'Penalización del ejercicio único Canarias: fallos y blancos'
    desc = ('Cuánto restan los fallos en el ejercicio único del Gobierno de Canarias 2026: −0,20 cada 3 fallos en el '
            'test y −0,40 cada 2 en el supuesto. Con ejemplos.')
    h1 = 'Penalización del ejercicio único: cuánto restan los fallos y cuándo compensa arriesgar'
    t1 = ''.join(f'<tr><td class="n">{f}</td><td class="n">{f // 3}</td><td class="n">{"−" + cents((f // 3) * 20) if f >= 3 else "0,00"}</td>'
                 f'<td class="n">{"0,20" if (f + 1) % 3 == 0 else "0,00"}</td></tr>' for f in range(0, 10))
    t2 = ''.join(f'<tr><td class="n">{f}</td><td class="n">{f // 2}</td><td class="n">{"−" + cents((f // 2) * 40) if f >= 2 else "0,00"}</td>'
                 f'<td class="n">{"0,40" if (f + 1) % 2 == 0 else "0,00"}</td></tr>' for f in range(0, 7))
    th = ('<thead><tr><th class="n" scope="col">Fallos</th><th class="n" scope="col">Grupos</th>'
          '<th class="n" scope="col">Resta</th><th class="n" scope="col">Próximo fallo</th></tr></thead>')

    def ev(kind, elim):  # expected value (points of the part) of answering instead of leaving blank
        value, group = (0.20, 3) if kind == 1 else (0.40, 2)
        p = 1 / (4 - elim)
        return p * value - (1 - p) * value / group
    ev_rows, ev_tables = [], []
    for kind, label in ((1, 'Parte 1 · Test'), (2, 'Parte 2 · Supuesto')):
        start = len(ev_rows)
        for elim in (0, 1, 2):
            x = round(ev(kind, elim), 3)
            if abs(x) < 0.0005:
                x = 0.0
            s = f'{x:+.3f}'.replace('.', ',').replace('-', '−') if x else '0,000'
            verdict = ('<span class="tag ok">compensa</span>' if x > 0 else
                       '<span class="tag bad">no compensa</span>' if x < 0 else '<span class="tag warn">neutro</span>')
            ev_rows.append(f'<tr><td>Entre {4 - elim} opciones</td><td class="n"><strong>{s}</strong></td><td>{verdict}</td></tr>')
        ev_tables.append(f'<div class="tw"><table class="t"><caption>{label}</caption><thead><tr><th scope="col">Si dudas</th>'
                         f'<th class="n" scope="col">Valor esperado</th><th scope="col">¿Compensa?</th></tr></thead>'
                         f'<tbody>{"".join(ev_rows[start:])}</tbody></table></div>')
    expected = ['0,000', '+0,022', '+0,067', '−0,050', '0,000', '+0,100']
    got = [re.search(r'<strong>(.*?)</strong>', r).group(1) for r in ev_rows]
    assert got == expected, got
    body = hero(
        'Guía · Bases 22.5 y 23.6 · BOC n.º 57/2026',
        esc(h1),
        ('En el ejercicio único de 2026 los fallos <strong>solo restan por grupos completos</strong>: −0,20 cada 3 en el test '
         'y −0,40 cada 2 en el supuesto. Los blancos no restan nunca. Aquí tienes la regla, ejemplos y cuándo compensa arriesgar.'),
        btn_free('Practicar con un examen oficial (gratis)') +
        '<a class="btn ghost xl" href="../calculadora-nota-ejercicio-unico-canarias/">Calcular mi nota</a>')
    body += f"""
<section class="card sec" aria-labelledby="h-bases">
<h2 id="h-bases">Lo que dicen las bases</h2>
<p>La convocatoria de 2026 (<a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57, de 24/03/2026</a>) fija dos reglas distintas, una para cada parte del ejercicio único:</p>
<blockquote class="base"><p>«Por cada tres preguntas contestadas de forma errónea se descontará de la calificación total 0,20 puntos»</p><footer>Base 22.5 · Parte 1, test de 50 preguntas (+0,20 por acierto)</footer></blockquote>
<blockquote class="base"><p>«Por cada 2 preguntas contestadas de forma errónea se descontará de la calificación total 0,40 puntos»</p><footer>Base 23.6 · Parte 2, supuesto práctico de 25 preguntas (+0,40 por acierto)</footer></blockquote>
<p>Ambas bases añaden que en ningún caso se aplica una penalización proporcional si hay menos errores que los del grupo, y las bases 22.6 y 23.7 aclaran que <strong>las preguntas no contestadas no computan</strong> a efectos de penalización.</p>
</section>

<section class="card sec" aria-labelledby="h-grupos">
<h2 id="h-grupos">Cómo funciona: solo restan los grupos completos</h2>
<p>El número de grupos es el número de fallos dividido entre 3 (test) o entre 2 (supuesto), <strong>sin decimales</strong>. Por eso no todos los fallos cuestan lo mismo: algunos son «gratis» y otros cierran un grupo y restan el valor de un acierto entero.</p>
<div class="tw"><table class="t"><caption>Parte 1 · Test (−0,20 por cada 3 fallos)</caption>{th}<tbody>{t1}</tbody></table></div>
<div class="tw"><table class="t"><caption>Parte 2 · Supuesto (−0,40 por cada 2 fallos)</caption>{th}<tbody>{t2}</tbody></table></div>
</section>

<section class="card sec" aria-labelledby="h-ej">
<h2 id="h-ej">Ejemplos resueltos</h2>
<ul>
<li><strong>Test, 35 aciertos y 10 fallos:</strong> 35 × 0,20 = 7,00; 10 fallos son 3 grupos completos → −0,60. Nota: <strong>6,40</strong>. El décimo fallo no ha restado nada.</li>
<li><strong>Test, 25 aciertos y 2 fallos:</strong> 5,00 y ningún grupo completo → <strong>5,00</strong>, aprobado justo. Con un tercer fallo bajaría a 4,80.</li>
<li><strong>Supuesto, 16 aciertos y 5 fallos:</strong> 16 × 0,40 = 6,40; 5 fallos son 2 grupos → −0,80. Nota: <strong>5,60</strong>.</li>
<li><strong>Supuesto, 13 aciertos y 2 fallos:</strong> 5,20 − 0,40 = <strong>4,80</strong>. No llega al 5: un solo fallo de más cambia el resultado.</li>
</ul>
</section>

<section class="card sec" aria-labelledby="h-ev">
<h2 id="h-ev">¿Compensa contestar si dudo?</h2>
<p>Valor esperado de contestar una pregunta que dejarías en blanco, según entre cuántas opciones dudas (en puntos de la parte). Se calcula como la probabilidad de acertar por el valor del acierto, menos la probabilidad de fallar por el coste medio de un fallo (0,20 ÷ 3 en el test; 0,40 ÷ 2 en el supuesto).</p>
{''.join(ev_tables)}
<ul>
<li><strong>Test:</strong> si descartas al menos una opción, contestar suma de media. A ciegas entre 4 es neutro.</li>
<li><strong>Supuesto:</strong> el fallo sale más caro. A ciegas entre 4 pierdes de media; entre 3 es neutro; solo compensa claramente si dudas entre 2.</li>
</ul>
<p class="small muted">Es un promedio: en un examen concreto la suerte puede ir a favor o en contra. Sirve para decidir con criterio, no garantiza el resultado.</p>
</section>

<section class="card sec" aria-labelledby="h-gratis">
<h2 id="h-gratis">Los «fallos gratis»</h2>
<p>Como solo restan los grupos completos, el 1.º y el 2.º fallo del test no restan nada, y el 1.º del supuesto tampoco. Lo mismo pasa dentro de cada grupo: con 4 fallos en el test, el 5.º es gratis y el 6.º resta 0,20.</p>
<p>Durante el examen no sabes cuáles has fallado, así que la decisión de contestar o no debe apoyarse en la tabla de valor esperado. Donde sí ayuda es al practicar: el simulador te dice en cada intento cuántos de tus fallos no restaron (los del último grupo incompleto) y, si marcas las dudosas, qué nota habrías sacado dejándolas en blanco. Así aprendes si arriesgar te suma o te resta.</p>
</section>

<section aria-labelledby="h-cta">
<h2 id="h-cta">Pruébalo con un examen oficial</h2>
{cta_band('Descubre si arriesgar te suma o te resta',
          'Haz gratis el examen oficial C2 completo, marca las preguntas en las que dudas y al corregir verás tu nota con y sin ellas.')}
{pass_card()}
</section>

<section class="card sec" aria-labelledby="h-faq">
<h2 id="h-faq">Preguntas frecuentes</h2>
{faq_html(PEN_FAQS)}
</section>

<section aria-labelledby="h-sigue">
<h2 id="h-sigue">Sigue preparando el examen</h2>
{related(slug)}
</section>
{share(slug, 'Cómo penalizan los fallos en el ejercicio único del Gobierno de Canarias y cuándo compensa contestar:')}
"""
    graph = [article_ld(slug, h1, desc), faq_ld(PEN_FAQS)]
    return slug, render(slug, title, desc, 'Penalización y blancos', body, graph)


FECHA_FAQS = [
    ('¿Cuándo es el examen de Auxiliar Administrativo (C2) del Gobierno de Canarias 2026?',
     'Según la nota informativa de la Dirección General de la Función Pública de 09/09/2026, el ejercicio único del '
     'Cuerpo Auxiliar (C2) por turno libre está previsto para el sábado 31 de octubre de 2026 a las 10:00.'),
    ('¿Cuándo es el examen de Administrativo (C1) de turno libre?',
     'Está previsto para el sábado 17 de octubre de 2026 a las 10:00, según la misma nota informativa.'),
    ('¿Y el de promoción interna C1 y C2?',
     'Ambos están previstos para el sábado 17 de octubre de 2026 a las 16:00.'),
    ('¿Cuántas plazas se convocan?',
     'Según el Anexo II del BOC n.º 57/2026: 296 plazas de Auxiliar (C2) por turno libre (278 de turno general y 18 de '
     'discapacidad) y 57 de Administrativo (C1) por turno libre (46 y 11). El Anexo II recoge además plazas adicionales.'),
    ('¿Cuánto dura el examen?',
     '100 minutos para las dos partes (test de 50 preguntas y supuesto práctico de 25), repartidos como quieras. '
     'Si conservas la calificación del primer ejercicio, la segunda parte dura como máximo 50 minutos (Base 21.3).'),
    ('¿Son fechas definitivas?',
     'No. La nota informativa tiene carácter orientativo: son oficiales y vinculantes la fecha, la hora y las sedes '
     'que se publiquen en el Boletín Oficial de Canarias.'),
]


def page_fecha():
    slug = 'fecha-examen-gobierno-canarias-2026'
    title = 'Fecha examen Gobierno de Canarias 2026: C1, C2 y hora'
    desc = ('Ejercicio único del Gobierno de Canarias 2026: C1 turno libre el 17/10 a las 10:00, promoción interna el '
            '17/10 a las 16:00 y C2 el 31/10 a las 10:00.')
    h1 = 'Fecha del examen del Gobierno de Canarias 2026 (C1 y C2)'

    def card(key, main=False):
        iso, day, hour, who = DATES[key]
        return (f'<div class="cd-card{" main" if main else ""}"><p class="who">{esc(who)}</p>'
                f'<p class="day">{esc(day.capitalize())}, {hour} h</p>'
                f'<span class="cd" data-cd="{iso}" hidden></span></div>')
    rows = ''.join(
        f'<tr><td>{esc(DATES[k][3])}</td><td>{esc(DATES[k][1].replace(" de 2026", ""))}</td><td class="n">{DATES[k][2]}</td><td class="n">{pl}</td></tr>'
        for k, pl in (('C1', '57'), ('PI', '—'), ('C2', '296')))
    body = hero(
        'Ejercicio único · Convocatoria 2026',
        esc(h1),
        ('Fechas previstas del ejercicio único según la nota informativa de la Dirección General de la Función Pública '
         'de 09/09/2026, con la cuenta atrás, las plazas y cómo es el examen.'),
        btn_free('Hacer un simulacro oficial gratis') +
        '<a class="btn ghost xl" href="../calculadora-nota-ejercicio-unico-canarias/">Calcular mi nota</a>',
        f'<div class="cd-grid">{card("C2", True)}{card("C1")}{card("PI")}</div>\n')
    body += f"""
<section class="card sec" aria-labelledby="h-cal">
<h2 id="h-cal">Calendario del ejercicio único 2026</h2>
<div class="tw"><table class="t"><thead><tr><th scope="col">Proceso</th><th scope="col">Fecha</th><th class="n" scope="col">Hora</th><th class="n" scope="col">Plazas</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Horas de convocatoria, en hora de Canarias. Las fechas son una <strong>previsión</strong>: la propia nota dice que tiene carácter orientativo y que son oficiales la fecha, la hora y las sedes que se publiquen en el Boletín Oficial de Canarias. Como lugares, la nota cita la Universidad de La Laguna y la Universidad de Las Palmas de Gran Canaria.</p>
<p class="srcline">Fuentes: <a href="{NOTA_URL}" target="_blank" rel="noopener">nota informativa DGFP de 09/09/2026 (PDF)</a> · <a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57/2026, Anexo II (plazas)</a></p>
</section>

<section class="card sec" aria-labelledby="h-plazas">
<h2 id="h-plazas">Plazas convocadas por turno libre</h2>
<div class="kpis"><div class="kpi"><b>296</b><span>C2 Auxiliar (278 generales + 18 discapacidad)</span></div><div class="kpi"><b>57</b><span>C1 Administrativo (46 generales + 11 discapacidad)</span></div></div>
<p>Datos del Anexo II del BOC n.º 57/2026. La convocatoria prevé además plazas adicionales (consideración jurídica quinta y Anexo II), para vacantes que surjan en los dos años siguientes.</p>
</section>

<section class="card sec" aria-labelledby="h-como">
<h2 id="h-como">Cómo es el examen</h2>
<ol>
<li><strong>Parte 1 · Test:</strong> 50 preguntas de la parte general del temario (+4 de reserva), 4 opciones. +0,20 por acierto y −0,20 por cada 3 fallos.</li>
<li><strong>Parte 2 · Supuesto práctico:</strong> eliges 1 de 2 supuestos; 25 preguntas tipo test (+3 de reserva). +0,40 por acierto y −0,40 por cada 2 fallos.</li>
<li><strong>Tiempo:</strong> 100 minutos para todo, repartidos como quieras (50 para la segunda parte si conservas la nota del primer ejercicio).</li>
<li><strong>Para aprobar:</strong> al menos un 5 en cada parte y de media. La nota del ejercicio es la media de las dos partes.</li>
</ol>
<p>Más detalle en la <a href="../penalizacion-ejercicio-unico-canarias/">guía de penalización</a> y en la <a href="../calculadora-nota-ejercicio-unico-canarias/">calculadora de nota</a>.</p>
</section>

<section class="card sec" aria-labelledby="h-plan">
<h2 id="h-plan">Qué hacer en los días que quedan</h2>
<ol>
<li><strong>Hoy:</strong> haz un examen oficial completo con cronómetro para saber de dónde partes. El C2 de 2022 es gratis en el simulador.</li>
<li><strong>Mide dónde pierdes nota:</strong> aciertos, fallos y blancos en cada parte. Con la calculadora ves cuántos aciertos te faltan para el 5.</li>
<li><strong>Decide tu estrategia de blancos</strong> antes del examen, no durante: en el test compensa contestar si descartas una opción; en el supuesto, solo si dudas entre 2.</li>
<li><strong>Repite lo que fallas</strong> hasta que salga solo y haz al menos un simulacro completo con cronómetro la semana del examen.</li>
</ol>
</section>

<section aria-labelledby="h-cta">
<h2 id="h-cta">Empieza hoy con un examen oficial</h2>
{cta_band('Haz un examen oficial completo y sabrás tu nota al instante',
          'El cuestionario oficial C2 de 2022 (50 preguntas + reserva), cronometrado y corregido con las reglas de 2026. Gratis y sin registro.')}
{pass_card()}
</section>

<section class="card sec" aria-labelledby="h-faq">
<h2 id="h-faq">Preguntas frecuentes</h2>
{faq_html(FECHA_FAQS)}
</section>

<section aria-labelledby="h-sigue">
<h2 id="h-sigue">Sigue preparando el examen</h2>
{related(slug)}
</section>
{share(slug, 'Fechas previstas del ejercicio único del Gobierno de Canarias 2026 (C1 y C2), con cuenta atrás:')}
"""
    graph = [article_ld(slug, h1, desc), faq_ld(FECHA_FAQS)]
    return slug, render(slug, title, desc, 'Fechas del examen 2026', body, graph, scripts=COUNTDOWN_JS)


SAMPLE_NS = [1, 6, 11, 16, 21, 26, 31, 36, 41, 46]


def page_hub(exams):
    slug = 'test-auxiliar-administrativo-canarias'
    ex = exams[FREE_EXAM]
    byn = {q['n']: q for q in questions(ex)}
    sample = [byn[n] for n in SAMPLE_NS]
    title = 'Test Auxiliar Administrativo Gobierno de Canarias 2026'
    desc = ('Test de Auxiliar Administrativo del Gobierno de Canarias con preguntas oficiales y respuestas: 10 de muestra, '
            'examen completo gratis y simulacros.')
    h1 = 'Test Auxiliar Administrativo Gobierno de Canarias 2026'
    exam_page = '../examen-auxiliar-administrativo-canarias-resuelto/'
    cards = []
    for i, q in enumerate(sample, 1):
        lis = ''.join(f'<li><span class="l">{esc(k)}</span><span class="t-opt">{esc(t)}</span></li>' for k, t in q['options'].items())
        cards.append(
            f'<div class="qa" id="m{i}"><p class="qa-stem"><span class="num">{i}.</span> {esc(q["stem"])}</p>'
            f'<ol class="opts">{lis}</ol>'
            f'<details class="reveal"><summary>Ver respuesta</summary>'
            f'<p>Respuesta oficial: <strong>{esc(q["answer"])})</strong> {esc(q["options"][q["answer"]])}</p>'
            f'<p class="srcline">Pregunta {q["n"]} del cuestionario n.º 2 de Auxiliar (C2) turno libre, convocatoria 2022 · '
            f'<a href="{exam_page}#p{q["n"]}">verla en el examen completo</a></p></details></div>')
    body = hero(
        'Preguntas oficiales de 2022 · C2 Auxiliar · Para el ejercicio único 2026',
        esc(h1),
        ('Preguntas oficiales de exámenes del Gobierno de Canarias, con la respuesta del tribunal y corregidas con las reglas '
         'del ejercicio único de 2026. Empieza por las 10 de muestra o ve directo al examen completo.'),
        btn_free('Hacer el test oficial completo (gratis)') +
        '<a class="btn ghost xl" href="#muestra">Ver 10 preguntas de muestra</a>')
    body += f"""
<section class="card sec" aria-labelledby="h-que">
<h2 id="h-que">Qué puedes hacer gratis y qué incluye el pase</h2>
<div class="links">
<div>
<h3>Gratis, sin registro</h3>
<ul class="check">
<li>Examen oficial completo C2 turno libre 2022 (cuestionario n.º 2: 50 preguntas + 4 de reserva), cronometrado</li>
<li>Corrección con las reglas de 2026 y revisión pregunta a pregunta</li>
<li><a href="../calculadora-nota-ejercicio-unico-canarias/">Calculadora de nota</a> y <a href="../penalizacion-ejercicio-unico-canarias/">guía de penalización</a></li>
<li>Exámenes resueltos para leer: <a href="{exam_page}">C2 2022</a> y <a href="../examen-administrativo-c1-canarias-resuelto/">C1 2024</a></li>
</ul>
</div>
<div>
<h3>Pase hasta el examen · {PRICE}</h3>
<ul class="check lock">
<li>{TOTAL_QUESTIONS} preguntas oficiales de 6 exámenes (C1 y C2)</li>
<li>Simulacro completo cronometrado: test + 1 de 2 supuestos oficiales</li>
<li>Tests aleatorios con todo el banco oficial</li>
<li>Repaso de falladas e historial de notas</li>
</ul>
</div>
</div>
</section>

<section id="muestra" aria-labelledby="h-muestra">
<h2 id="h-muestra">10 preguntas oficiales de muestra (con respuesta)</h2>
<p>Elige tu respuesta antes de desplegar. Todas salen del examen oficial de Auxiliar Administrativo (C2) de turno libre de la convocatoria 2022, con la respuesta de la plantilla del tribunal.</p>
{''.join(cards)}
{cta_band('¿Cuántas has acertado? Ahora las 50, contra el reloj',
          'El examen oficial completo en el simulador, con cronómetro y nota al instante según las reglas de 2026. Gratis y sin registro.')}
</section>

<section class="card sec" aria-labelledby="h-formato">
<h2 id="h-formato">Cómo es el test del ejercicio único 2026</h2>
<p>La primera parte del ejercicio único es un test de <strong>50 preguntas</strong> (+4 de reserva) con 4 opciones. Cada acierto vale 0,20 y cada grupo completo de 3 fallos resta 0,20; los blancos no restan. La segunda parte es un supuesto práctico de 25 preguntas. Tienes 100 minutos para las dos y necesitas al menos un 5 en cada una.</p>
<p>El C2 Auxiliar de turno libre está previsto para el <strong>sábado 31 de octubre de 2026 a las 10:00</strong> (<a href="../fecha-examen-gobierno-canarias-2026/">ver todas las fechas</a>), con 296 plazas convocadas.</p>
<p class="srcline">Fuentes: <a href="{BOC_URL}" target="_blank" rel="noopener">BOC n.º 57/2026</a> · <a href="{NOTA_URL}" target="_blank" rel="noopener">nota informativa DGFP 09/09/2026</a></p>
</section>

<section aria-labelledby="h-rec">
<h2 id="h-rec">Exámenes resueltos y guías</h2>
{related(slug)}
</section>

<section aria-labelledby="h-pase">
<h2 id="h-pase">Todo el banco oficial, por {PRICE}</h2>
{pass_card()}
</section>
{share(slug, 'Test de Auxiliar Administrativo del Gobierno de Canarias con preguntas oficiales y examen completo gratis:')}
"""
    graph = [quiz_ld(slug, '10 preguntas oficiales de muestra · Test Auxiliar Administrativo Gobierno de Canarias',
                     desc, ex, sample, 'C2 · Auxiliar Administrativo',
                     'Oposiciones Auxiliar Administrativo Gobierno de Canarias')]
    return slug, render(slug, title, desc, 'Test Auxiliar Administrativo 2026', body, graph, og_type='website')


# ----------------------------------------------------------------------------- sitemap
def sitemap():
    urls = [BASE + '/', BASE + '/simulador'] + [url_of(s) for s in SLUGS]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f'  <url><loc>{u}</loc><lastmod>{LASTMOD}</lastmod></url>' for u in urls]
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = None
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            old = fh.read()
    if old != text:
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        return 'written'
    return 'unchanged'


def build():
    exams = load_exams()
    pages = [page_hub(exams), page_exam_c2(exams), page_exam_c1(exams), page_calc(), page_penal(), page_fecha()]
    assert [s for s, _ in pages] == SLUGS
    print('assets/seo.css', write(os.path.join(SITE, 'assets', 'seo.css'), SEO_CSS))
    for slug, text in pages:
        print(f'{slug}/index.html', write(os.path.join(SITE, slug, 'index.html'), text), f'{len(text.encode()) // 1024} KB')
    print('sitemap.xml', write(os.path.join(SITE, 'sitemap.xml'), sitemap()))
    robots = os.path.join(SITE, 'robots.txt')
    with open(robots, encoding='utf-8') as fh:
        r = fh.read()
    if f'Sitemap: {BASE}/sitemap.xml' not in r:
        write(robots, r.rstrip('\n') + f'\nSitemap: {BASE}/sitemap.xml\n')


# ----------------------------------------------------------------------------- validation
class Scan(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = 0
        self.h2 = 0
        self.ids = set()
        self.refs = []      # (attr, value)
        self.ld = []
        self.styles = []
        self.title = ''
        self.meta = {}
        self.canonical = None
        self.lang = None
        self.stack = []
        self.errors = []
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == 'html':
            self.lang = a.get('lang')
        if tag == 'h1':
            self.h1 += 1
        if tag == 'h2':
            self.h2 += 1
        if 'id' in a:
            if a['id'] in self.ids:
                self.errors.append(f'duplicate id {a["id"]}')
            self.ids.add(a['id'])
        for k in ('href', 'src'):
            if k in a:
                self.refs.append((tag, k, a[k], a.get('rel', '')))
        if 'style' in a:
            self.styles.append(a['style'])
        if tag == 'meta':
            key = a.get('name') or a.get('property')
            if key:
                self.meta.setdefault(key, a.get('content', ''))
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self._in, self._buf = 'ld', []
        elif tag == 'style':
            self._in, self._buf = 'style', []
        elif tag == 'title':
            self._in, self._buf = 'title', []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f'unbalanced </{tag}> (open: {self.stack[-3:]})')
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()
        if self._in and tag in ('script', 'style', 'title'):
            text = ''.join(self._buf)
            if self._in == 'ld':
                self.ld.append(text)
            elif self._in == 'style':
                self.styles.append(text)
            else:
                self.title = text
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def resolve_local(page_url_path, ref):
    """Map a relative href/src (as used under /<slug>/) to a file in SITE, Cloudflare-pretty-URL style."""
    full = urljoin('https://x' + page_url_path, ref)
    parts = urlsplit(full)
    path = parts.path
    rel = path.lstrip('/')
    cands = [os.path.join(SITE, rel, 'index.html')] if path.endswith('/') else [
        os.path.join(SITE, rel), os.path.join(SITE, rel + '.html'), os.path.join(SITE, rel, 'index.html')]
    for c in cands:
        if os.path.isfile(c):
            return c, parts.fragment
    return None, parts.fragment


WIDTH_RE = re.compile(r'(?<![\w-])(min-width|width)\s*:\s*(\d+(?:\.\d+)?)px')


def fixed_widths(css):
    css = re.sub(r'@media[^{]*\{', '', css)  # media query conditions are not widths
    return [(p, float(v)) for p, v in WIDTH_RE.findall(css) if float(v) > 340]


def validate():
    problems = []
    parsed = {}
    for slug in SLUGS:
        path = os.path.join(SITE, slug, 'index.html')
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        s = Scan()
        s.feed(text)
        s.close()
        parsed[slug] = s
        p = lambda m: problems.append(f'{slug}: {m}')
        for e in s.errors:
            p(e)
        if s.stack:
            p(f'unclosed tags {s.stack}')
        if s.lang != 'es':
            p('lang != es')
        if s.h1 != 1:
            p(f'{s.h1} H1')
        if s.h2 < 3:
            p(f'only {s.h2} H2')
        if not (0 < len(s.title) <= 60):
            p(f'title length {len(s.title)}')
        d = s.meta.get('description', '')
        if not (50 <= len(d) <= 155):
            p(f'description length {len(d)}')
        if s.canonical != url_of(slug):
            p(f'canonical {s.canonical}')
        for k in ('og:title', 'og:description', 'og:url', 'og:image', 'twitter:card', 'twitter:image'):
            if not s.meta.get(k):
                p(f'missing {k}')
        if s.meta.get('og:image') != OG_IMAGE:
            p('og:image')
        types = []
        for raw in s.ld:
            try:
                data = json.loads(raw)
            except ValueError as ex:
                p(f'JSON-LD does not parse: {ex}')
                continue
            types += [g.get('@type') for g in data.get('@graph', [data])]
        if 'BreadcrumbList' not in types or len(types) < 2:
            p(f'JSON-LD types {types}')
        for tag, attr, ref, rel in s.refs:
            if re.match(r'^(https?:|mailto:|tel:|data:|#)', ref):
                continue
            if ref.startswith('/'):
                p(f'root-relative link {ref}')
                continue
            f, frag = resolve_local(f'/{slug}/', ref)
            if not f:
                p(f'broken {attr}="{ref}"')
            elif frag and f.endswith('index.html') and os.path.basename(os.path.dirname(f)) in SLUGS:
                target = os.path.basename(os.path.dirname(f))
                ids = parsed[target].ids if target in parsed else None
                if ids is None:
                    t = Scan()
                    with open(f, encoding='utf-8') as fh:
                        t.feed(fh.read())
                    ids = t.ids
                if frag not in ids:
                    p(f'missing anchor #{frag} in {target}')
        for css in s.styles:
            for prop, v in fixed_widths(css):
                p(f'fixed {prop}: {v}px')
    with open(os.path.join(SITE, 'assets', 'seo.css'), encoding='utf-8') as fh:
        for prop, v in fixed_widths(fh.read()):
            problems.append(f'seo.css: fixed {prop}: {v}px')
    with open(os.path.join(SITE, 'sitemap.xml'), encoding='utf-8') as fh:
        sm = fh.read()
    for u in [BASE + '/', BASE + '/simulador'] + [url_of(s) for s in SLUGS]:
        if f'<loc>{u}</loc><lastmod>{LASTMOD}</lastmod>' not in sm:
            problems.append(f'sitemap missing {u}')
    with open(os.path.join(SITE, 'robots.txt'), encoding='utf-8') as fh:
        if f'Sitemap: {BASE}/sitemap.xml' not in fh.read():
            problems.append('robots.txt does not point to sitemap')
    if problems:
        print('VALIDATION FAILED')
        for x in problems:
            print(' -', x)
        return False
    print(f'validation OK: {len(SLUGS)} pages, one H1 each, JSON-LD parses, links/assets resolve, no fixed widths > 340px')
    return True


if __name__ == '__main__':
    if '--check' not in sys.argv:
        build()
    sys.exit(0 if validate() else 1)
