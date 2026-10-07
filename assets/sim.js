(function () {
  'use strict';
  const C = window.SIMU_CONFIG, S = window.Scoring;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const app = $('#app');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const plural = (n, s, p) => `${n} ${n === 1 ? s : (p || s + 's')}`;

  // ---------------- License / Pro ----------------
  let PRO = false;
  const lic = createLicense({
    productId: C.gumroadProductId,
    storageKey: 'simucanarias_lic_v1',
    onChange: (v) => { PRO = v; renderBadge(); },
  });
  function renderBadge() {
    const el = $('#pro-badge');
    if (!el) return;
    el.innerHTML = PRO
      ? '<span class="tag ok">Pase activo ✓</span>'
      : '<button class="btn small sun" data-buy>Desbloquear todo</button>';
  }
  $$('.js-price').forEach(e => e.textContent = C.price);
  $$('.js-buy').forEach(a => a.href = C.gumroadUrl);
  const modal = $('#buy-modal');
  function openBuy() { modal.classList.add('open'); $('#lic-msg').textContent = ''; }
  function closeBuy() { modal.classList.remove('open'); }
  $('#buy-close').onclick = closeBuy;
  modal.addEventListener('click', (e) => { if (e.target === modal) closeBuy(); });
  document.addEventListener('click', (e) => { if (e.target.closest('[data-buy]')) { e.preventDefault(); openBuy(); } });
  $('#lic-go').onclick = async () => {
    const key = $('#lic-input').value.trim();
    const msg = $('#lic-msg');
    if (!key) { msg.textContent = 'Pega tu clave de licencia.'; return; }
    if (!C.gumroadProductId) { msg.textContent = 'La activación aún no está disponible. Escríbenos y te ayudamos.'; return; }
    msg.textContent = 'Comprobando…';
    const r = await lic.activate(key);
    if (r.ok) { msg.innerHTML = '<span style="color:var(--ok)">¡Activado! Ya tienes acceso a todo.</span>'; setTimeout(() => { closeBuy(); route(); }, 900); }
    else if (r.offline) msg.textContent = 'No hay conexión. Inténtalo de nuevo.';
    else msg.innerHTML = '<span style="color:var(--bad)">Esa clave no es válida (o fue reembolsada). Revisa el email de Gumroad.</span>';
  };
  // Allow ?key=XXXX deep links (e.g. from the Gumroad receipt)
  (async () => {
    const k = new URLSearchParams(location.search).get('key');
    if (k && C.gumroadProductId) {
      const r = await lic.activate(k);
      history.replaceState(null, '', location.pathname + location.hash);
      if (!r.ok) await lic.restore();
      renderBadge(); route();
    } else await lic.restore();
    renderBadge();
  })();

  // ---------------- Data ----------------
  let CATALOG = null;
  const EXAMS = {};
  async function getCatalog() {
    if (!CATALOG) CATALOG = await (await fetch('data/catalog.json', { cache: 'no-cache' })).json();
    return CATALOG;
  }
  async function getExam(id) {
    if (!EXAMS[id]) {
      const r = await fetch(`data/exams/${id}.json`, { cache: 'no-cache' });
      if (!r.ok) throw new Error('No se pudo cargar el examen ' + id);
      EXAMS[id] = await r.json();
    }
    return EXAMS[id];
  }
  function blockQs(ex, bi) {
    const b = ex.blocks[bi];
    const ctx = b.kind === 'practico' && b.context ? { title: b.title, context: b.context } : null;
    return b.questions.map(q => ({ ...q, uid: `${ex.id}#${bi}#${q.n}`, src: ex.title, srcUrl: ex.source_url, srcDate: ex.published, ctx }));
  }
  const isFree = (id) => id === C.freeExam;
  const renumber = (qs) => qs.map((q, i) => ({ ...q, dn: i + 1 }));
  const qLabel = (q, qs) => q.reserve ? 'Reserva ' + (qs.filter(x => x.reserve).indexOf(q) + 1) : (q.dn || q.n) + '.';
  const ctxBox = (q, p) => (!p || !p.choices) && q.ctx ? `<details class="context" style="margin:0 0 10px"><summary class="small"><strong>Ver enunciado: ${esc(q.ctx.title)}</strong></summary>\n${esc(q.ctx.context)}</details>` : '';
  const locked = (id) => !PRO && !isFree(id);

  // ---------------- Session ----------------
  const SKEY = 'simu_session_v1';
  let SES = null, TICK = null;
  function newSession(def) {
    SES = { title: def.title, parts: def.parts, minutes: def.minutes, started: null, answers: {}, doubts: {}, chosen: {}, active: 0, done: false, result: null, practice: !!def.practice };
    save();
    history.replaceState(null, '', '#/run');
    run();
  }
  const save = () => LS.set(SKEY, SES);
  // Total scored questions of a part; a supuesto part not chosen yet still counts its expected size.
  const partTotal = (p, i) => scoredSet(p.choices && SES.chosen[i] == null ? p.choices[0].questions : partQs(p, i)).length;
  const pendingSession = () => { const s = LS.get(SKEY, null) || SES; return s && s.started && !s.done ? s : null; };
  async function startGuarded(build) {
    const s = pendingSession();
    if (s && !confirm(`Tienes un examen a medias («${s.title}»). ¿Descartarlo y empezar uno nuevo?`)) {
      SES = s; history.replaceState(null, '', '#/run'); return run();
    }
    newSession(await build());
  }
  function partQs(p, pi) {
    if (p.choices) { const c = SES.chosen[pi]; return c == null ? [] : p.choices[c].questions; }
    return p.questions;
  }

  // Which questions count: ordinary non-annulled + as many reserves as annulled ordinary ones (Bases 22.2 / 23.2)
  function scoredSet(qs) {
    const ord = qs.filter(q => !q.reserve);
    const ann = ord.filter(q => q.annulled).length;
    const res = qs.filter(q => q.reserve && !q.annulled).slice(0, ann);
    return ord.filter(q => !q.annulled).concat(res);
  }

  function gradePart(p, pi) {
    let qs = partQs(p, pi);
    if (p.choices && SES.chosen[pi] == null) {
      // never chose: take the supuesto with more answers (or the first)
      let best = 0, bestN = -1;
      p.choices.forEach((c, i) => { const n = c.questions.filter(q => SES.answers[q.uid]).length; if (n > bestN) { best = i; bestN = n; } });
      SES.chosen[pi] = best; qs = partQs(p, pi);
    }
    const scored = scoredSet(qs);
    let c = 0, w = 0, b = 0, dc = 0, dw = 0;
    const per = {};
    scored.forEach(q => {
      const a = SES.answers[q.uid];
      if (!a) { b++; per[q.uid] = 'blank'; return; }
      const ok = a === q.answer;
      if (ok) { c++; if (SES.doubts[q.uid]) dc++; } else { w++; if (SES.doubts[q.uid]) dw++; }
      per[q.uid] = ok ? 'ok' : 'ko';
    });
    const n = scored.length;
    const r = S.score(p.kind, c, w, n);
    const alt = S.score(p.kind, c - dc, w - dw, n); // if doubtful answers had been left blank
    return { kind: p.kind, title: p.title, n, c, w, b, dc, dw, ...r, altMark: alt.mark, per };
  }

  function submit(auto) {
    if (SES.done) return;
    if (!auto) {
      const total = SES.parts.reduce((s, p, i) => s + partTotal(p, i), 0);
      const answered = SES.parts.reduce((s, p, i) => s + scoredSet(partQs(p, i)).filter(q => SES.answers[q.uid]).length, 0);
      const unstarted = SES.parts.some((p, i) => p.choices && SES.chosen[i] == null);
      if (!confirm(`¿Entregar el examen? Has respondido ${answered} de ${total} preguntas.` + (unstarted ? '\n\nOjo: todavía no has elegido el supuesto de la parte 2, así que esa parte contará como 0.' : ''))) return;
    }
    clearInterval(TICK);
    const parts = SES.parts.map((p, i) => gradePart(p, i));
    const ex = parts.length === 2 ? S.exercise(parts[0].mark, parts[1].mark) : null;
    SES.result = { parts, ex, finished: Date.now(), auto: !!auto };
    SES.done = true;
    // stats for "falladas"
    const st = LS.get('simu_stats_v1', {});
    parts.forEach(pr => Object.entries(pr.per).forEach(([uid, v]) => {
      if (v === 'blank') return;
      const s = st[uid] || { ok: 0, ko: 0 };
      s[v]++; s.last = v; st[uid] = s;
    }));
    LS.set('simu_stats_v1', st);
    const hist = LS.get('simu_history_v1', []);
    hist.unshift({ t: Date.now(), title: SES.title, marks: parts.map(p => p.mark), mean: ex ? ex.mean : null });
    LS.set('simu_history_v1', hist.slice(0, 50));
    save();
    history.replaceState(null, '', '#/result');
    result();
  }

  // ---------------- Builders ----------------
  async function buildExam(id) {
    const ex = await getExam(id);
    if (ex.kind === 'practico') {
      return {
        title: ex.title, minutes: 50,
        parts: [{ kind: 'practico', title: 'Supuesto práctico', choices: ex.blocks.map((b, i) => ({ title: b.title, context: b.context, note: ex.note, questions: blockQs(ex, i) })) }],
      };
    }
    const qs = ex.blocks.flatMap((b, i) => blockQs(ex, i));
    const n = qs.filter(q => !q.reserve).length;
    return { title: ex.title, minutes: Math.max(10, Math.round(n * 1)), parts: [{ kind: 'general', title: 'Test', note: ex.note, questions: qs }] };
  }
  async function supuestoChoices(group) {
    const cat = await getCatalog();
    const out = [];
    for (const e of cat.exams.filter(e => e.group === group && e.kind === 'practico')) {
      const ex = await getExam(e.id);
      ex.blocks.forEach((b, i) => out.push({ title: `${b.title} · ${shortSrc(ex)}`, context: b.context, note: ex.note, questions: blockQs(ex, i) }));
    }
    return out;
  }
  const shortSrc = (ex) => ex.id.replace(/^(c\d)-(\d{4})-(pi|libre)-.*/, (m, g, y, t) => `${g.toUpperCase()} ${t === 'pi' ? 'promoción interna' : 'turno libre'} ${y}`);

  async function buildSimulacro(group, onlyPart2) {
    const choices = await supuestoChoices(group);
    const part2 = { kind: 'practico', title: 'Parte 2 · Supuesto práctico', choices: choices.slice(0, 2), note: 'Elige 1 de los 2 supuestos, como en el examen real.' };
    if (onlyPart2) { const m = Math.max(10, Math.round(50 * scoredSet(part2.choices[0].questions).length / 25)); return { title: `Parte 2 (${group}) · ${m} minutos`, minutes: m, parts: [part2] }; }
    let q1;
    if (group === 'C2') {
      q1 = blockQs(await getExam('c2-2022-libre-test2'), 0);
    } else {
      const a = blockQs(await getExam('c1-2024-pi-teorico'), 0).filter(q => !q.reserve);
      const b = shuffle(blockQs(await getExam('c1-2022-pi-test'), 0).filter(q => !q.reserve && !q.annulled));
      q1 = renumber(a.concat(b.slice(0, Math.max(0, 50 - a.length))));
    }
    const n1 = scoredSet(q1).length, n2 = scoredSet(part2.choices[0].questions).length;
    const minutes = Math.round(100 * (n1 + n2) / 75);
    return {
      title: `Simulacro completo ${group} · ${minutes} minutos`, minutes,
      parts: [{ kind: 'general', title: 'Parte 1 · Test', questions: q1 }, part2],
    };
  }

  async function generalPool(group) {
    const cat = await getCatalog();
    let pool = [];
    for (const e of cat.exams.filter(e => e.kind === 'general' && (group === 'all' || e.group === group))) {
      const ex = await getExam(e.id);
      pool = pool.concat(ex.blocks.flatMap((b, i) => blockQs(ex, i)).filter(q => !q.annulled));
    }
    return pool;
  }
  async function buildRandom(group, count) {
    const pool = renumber(shuffle(await generalPool(group)).slice(0, count).map(q => ({ ...q, reserve: false })));
    return { title: `Test aleatorio · ${group === 'all' ? 'C1 + C2' : group} · ${pool.length} preguntas`, minutes: Math.max(5, pool.length), parts: [{ kind: 'general', title: 'Test aleatorio', questions: pool }] };
  }
  async function falladasQs() {
    const st = LS.get('simu_stats_v1', {});
    const uids = Object.keys(st).filter(u => st[u].last === 'ko');
    const out = [];
    for (const uid of uids) {
      const [id, bi, n] = uid.split('#');
      try {
        const ex = await getExam(id);
        const q = blockQs(ex, +bi).find(x => String(x.n) === n);
        if (q && !q.annulled) out.push({ ...q, reserve: false });
      } catch {}
    }
    return out;
  }

  // ---------------- Views ----------------
  function view(html, keep) { app.innerHTML = html; if (!keep) window.scrollTo(0, 0); }

  async function home() {
    clearInterval(TICK);
    $('#site-header').classList.remove('hide');
    const cat = await getCatalog();
    const fall = Object.values(LS.get('simu_stats_v1', {})).filter(s => s.last === 'ko').length;
    const hist = LS.get('simu_history_v1', []);
    const pending = LS.get(SKEY, null);
    const lockIco = (id) => locked(id) ? '🔒 ' : '';
    const examRow = (e) => `
      <div class="list-item">
        <div><div><strong>${lockIco(e.id)}${esc(e.title)}</strong></div>
        <div class="small muted">${e.blocks.map(b => `${esc(b.title)}: ${plural(b.count, 'pregunta')}${b.reserves ? ` + ${plural(b.reserves, 'reserva')}` : ''}`).join(' · ')} · Publicado ${esc(e.published)}</div></div>
        <a class="btn small ${locked(e.id) ? 'ghost' : ''}" href="#/exam/${e.id}">${isFree(e.id) ? 'Gratis' : locked(e.id) ? 'Ver' : 'Empezar'}</a>
      </div>`;
    const proBtn = (href, label) => PRO ? `<a class="btn small" href="${href}">${label}</a>` : `<button class="btn small ghost" data-buy>🔒 ${label}</button>`;
    view(`
      <div class="wrap" style="padding-top:24px;padding-bottom:40px">
        ${pending && !pending.done ? `<div class="notice" style="margin-bottom:16px">Tienes un examen a medias: <strong>${esc(pending.title)}</strong>. <a href="#/run">Continuar</a> · <a href="#" id="discard">Descartar</a></div>` : ''}
        <h1 style="margin-top:0">Simulador del ejercicio único</h1>
        <p class="muted">Reglas de corrección de 2026 (BOC 57/2026): test −0,20 cada 3 fallos · supuesto −0,40 cada 2 fallos · mínimo 5 en cada parte.</p>
        ${PRO ? '' : `<div class="card" style="border-color:var(--sun);margin:16px 0">
          <strong>Empieza gratis</strong> con el examen oficial C2 de turno libre (50 preguntas + reserva). Cuando quieras ensayar el examen completo, el pase cuesta <strong>${esc(C.price)}</strong> una sola vez.
          <div class="cta-row" style="margin-bottom:0"><a class="btn" href="#/exam/${C.freeExam}">Hacer el examen gratis</a><button class="btn ghost" data-buy>Tengo una clave / Comprar</button></div></div>`}

        <h2 style="margin-top:28px">Simulacros como el día del examen</h2>
        <div class="grid2">
          <div class="card"><h3>C2 Auxiliar · completo</h3><p class="small muted">80 min · Parte 1: test oficial C2 (50 + 4 reservas) · Parte 2: elige 1 de 2 supuestos oficiales C2 de 2022 (10 preguntas cada uno; tiempo y nota proporcionales).</p>${proBtn('#/sim/C2', 'Empezar simulacro C2')}</div>
          <div class="card"><h3>C1 Administrativo · completo</h3><p class="small muted">100 min · Parte 1: 50 preguntas oficiales C1 · Parte 2: elige entre el supuesto A y el B oficiales (25 preguntas + 3 reservas).</p>${proBtn('#/sim/C1', 'Empezar simulacro C1')}</div>
          <div class="card"><h3>Solo parte 2</h3><p class="small muted">Para quien conserva la nota de la primera parte: 50 min en C1 (25 preguntas) y 20 min en C2 (10 preguntas).</p><div class="cta-row" style="margin:6px 0 0">${proBtn('#/p2/C2', 'C2')} ${proBtn('#/p2/C1', 'C1')}</div></div>
          <div class="card"><h3>Test aleatorio</h3><p class="small muted">Preguntas mezcladas de todo el banco oficial (test general).</p>
            <div class="cta-row" style="margin:6px 0 0">${proBtn('#/random/all/25', '25 preguntas')} ${proBtn('#/random/all/50', '50 preguntas')}</div></div>
        </div>

        <h2 style="margin-top:28px">Exámenes oficiales</h2>
        <div class="card">${cat.exams.map(examRow).join('')}</div>

        <h2 style="margin-top:28px">Tu progreso</h2>
        <div class="grid2">
          <div class="card"><h3>Repasar falladas</h3><p class="small muted">${plural(fall, 'pregunta pendiente', 'preguntas pendientes')} de repasar.</p>${fall ? proBtn('#/falladas', 'Repasar ahora') : '<span class="small muted">Haz un examen primero.</span>'}</div>
          <div class="card"><h3>Historial</h3>${hist.length ? `<ul class="small" style="padding-left:18px;margin:0">${hist.slice(0, 6).map(h => `<li>${new Date(h.t).toLocaleDateString('es-ES')} · ${esc(h.title)} · <strong>${h.mean != null ? 'media ' + S.fmt(h.mean) : h.marks.map(m => S.fmt(m)).join(' / ')}</strong></li>`).join('')}</ul>` : '<p class="small muted">Aún no has hecho ningún examen.</p>'}</div>
        </div>
        ${PRO ? '<p class="small muted" style="margin-top:24px"><a href="#" id="lic-off">Quitar el pase de este dispositivo</a> (podrás volver a activarlo con tu clave).</p>' : ''}
        <p class="small muted" style="margin-top:24px">Preguntas y respuestas tomadas de los exámenes oficiales publicados por la DGFP del Gobierno de Canarias. Si la normativa ha cambiado después del examen, la respuesta oficial puede no coincidir con la ley vigente. ¿Ves un error? Si eres cliente, responde al email de compra de Gumroad y lo corregimos.</p>
      </div>`);
    const lo = $('#lic-off');
    if (lo) lo.onclick = (e) => { e.preventDefault(); if (confirm('¿Quitar el pase de este dispositivo?')) { lic.deactivate(); home(); } };
    const d = $('#discard');
    if (d) d.onclick = (e) => { e.preventDefault(); LS.del(SKEY); home(); };
  }

  async function lockedPreview(id) {
    const cat = await getCatalog();
    const e = cat.exams.find(x => x.id === id);
    view(`<div class="wrap narrow" style="padding:32px 16px">
      <a href="#/">← Volver</a>
      <h1>🔒 ${esc(e ? e.title : id)}</h1>
      <p class="muted">${e ? e.blocks.map(b => `${esc(b.title)}: ${b.count} preguntas oficiales${b.reserves ? ` + ${b.reserves} de reserva` : ''}`).join(' · ') : ''}</p>
      <div class="card"><p>Este examen forma parte del <strong>Pase hasta el examen</strong> (${esc(C.price)}, pago único). Incluye todos los exámenes oficiales, los simulacros completos cronometrados, tests aleatorios y repaso de falladas.</p>
      <div class="cta-row"><button class="btn sun" data-buy>Desbloquear por ${esc(C.price)}</button><a class="btn ghost" href="#/exam/${C.freeExam}">Probar antes el examen gratis</a></div></div>
      ${e ? `<p class="small muted">Fuente: <a href="${esc(e.source_url)}" target="_blank" rel="noopener">PDF oficial</a> (publicado ${esc(e.published)}).</p>` : ''}
    </div>`);
  }

  function timeLeft() { return (SES.started || Date.now()) + SES.minutes * 60000 - Date.now(); }

  function intro() {
    const rows = SES.parts.map((p) => {
      const g = S.RULES[p.kind].group;
      if (p.choices) {
        const n = scoredSet(p.choices[0].questions).length;
        return `<li><strong>${esc(p.title)}</strong>: eliges 1 de ${p.choices.length} supuestos (${n} preguntas puntuables cada uno). Acierto +${S.fmt(10 / n)} · cada ${g} fallos −${S.fmt(10 / n)}.</li>`;
      }
      const n = scoredSet(p.questions).length, res = p.questions.filter(q => q.reserve).length;
      return `<li><strong>${esc(p.title)}</strong>: ${n} preguntas${res ? ` + ${res} de reserva (solo cuentan si se anula alguna)` : ''}. Acierto +${S.fmt(10 / n)} · cada ${g} fallos −${S.fmt(10 / n)}.</li>`;
    }).join('');
    const notes = [...new Set(SES.parts.flatMap(p => (p.choices || [p]).map(c => c.note).filter(Boolean)))];
    $('#site-header').classList.remove('hide');
    view(`<div class="wrap narrow" style="padding-top:24px;padding-bottom:40px">
      <a href="#/" id="cancel-intro">← Volver</a>
      <h1 style="margin-top:10px">${esc(SES.title)}</h1>
      <div class="card">
        <div class="kpis" style="margin-top:0"><div class="kpi"><b>${SES.minutes} min</b><span>tiempo</span></div><div class="kpi"><b>${SES.parts.length === 2 ? '2 partes' : '1 parte'}</b><span>${SES.practice ? 'práctica' : 'corrección oficial 2026'}</span></div></div>
        <ul style="padding-left:18px">${rows}</ul>
        <ul class="small muted" style="padding-left:18px">
          <li>Las preguntas en blanco no restan. Pulsa una opción para marcarla y otra vez para desmarcarla.</li>
          <li>Marca con <strong>✋ Dudo</strong> las preguntas en las que arriesgas: al corregir verás si te compensó.</li>
          <li>Tus respuestas se guardan solas: si cierras la página puedes continuar después (el tiempo sigue corriendo).</li>
        </ul>
        ${notes.map(n => `<p class="notice small">${esc(n)}</p>`).join('')}
        <button class="btn" id="start" style="width:100%;margin-top:6px">Empezar · el cronómetro arranca ahora</button>
      </div>
    </div>`);
    $('#start').onclick = () => { SES.started = Date.now(); save(); run(); };
    $('#cancel-intro').onclick = (e) => { e.preventDefault(); LS.del(SKEY); location.hash = '#/'; };
  }
  function fmtTime(ms) {
    ms = Math.max(0, ms);
    const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ':' : '') + String(m).padStart(h ? 2 : 1, '0') + ':' + String(x).padStart(2, '0');
  }

  function run() {
    SES = LS.get(SKEY, null) || SES;
    if (!SES) { location.hash = '#/'; return; }
    if (SES.done) { history.replaceState(null, '', '#/result'); return result(); }
    if (!SES.started) return intro();
    const pi = SES.active;
    const p = SES.parts[pi];
    const qs = partQs(p, pi);
    const allScored = SES.parts.reduce((s, pp, i) => s + partTotal(pp, i), 0);
    const tabs = SES.parts.length > 1 ? `<div class="tabs">${SES.parts.map((pp, i) => `<button class="tab ${i === pi ? 'on' : ''}" data-part="${i}">${esc(pp.title)}</button>`).join('')}</div>` : '';
    let choiceHtml = '';
    if (p.choices) {
      const ch = SES.chosen[pi];
      choiceHtml = `<p class="small muted">${esc(p.note || 'Elige uno de los supuestos y responde sus preguntas.')}</p>
        <div class="grid2" style="margin-bottom:14px">${p.choices.map((c, i) => `
          <div class="card" style="${ch === i ? 'border-color:var(--brand);box-shadow:inset 0 0 0 1px var(--brand)' : ''}">
            <h3>${esc(c.title)} ${ch === i ? '<span class="tag ok">Elegido</span>' : ''}</h3>
            <p class="small muted">${esc(c.context.slice(0, 220))}${c.context.length > 220 ? '…' : ''}</p>
            ${c.note ? `<p class="small notice">${esc(c.note)}</p>` : ''}
            <button class="btn small ${ch === i ? '' : 'ghost'}" data-choose="${i}">${ch === i ? 'Respondiendo este' : 'Elegir este supuesto'}</button>
          </div>`).join('')}</div>`;
      if (ch != null) choiceHtml += `<details open class="context" style="margin-bottom:12px"><summary><strong>Enunciado del supuesto</strong></summary>\n${esc(p.choices[ch].context)}</details>`;
    }
    const nav = qs.length ? `<details class="navwrap" ${innerWidth > 700 ? 'open' : ''}><summary class="small">Ir a una pregunta</summary><div class="navgrid">${qs.map((q, i) => `<a href="#q-${i}" data-jump="${i}" class="${SES.answers[q.uid] ? 'done' : ''} ${SES.doubts[q.uid] ? 'dq' : ''}" title="${q.reserve ? 'Reserva' : ''}">${q.reserve ? 'R' + (qs.filter(x => x.reserve).indexOf(q) + 1) : (q.dn || q.n)}</a>`).join('')}</div></details>` : '';
    const qHtml = qs.map((q, i) => `
      <div class="q" id="q-${i}">
        ${ctxBox(q, p)}<div class="qhead"><p class="stem"><span class="num">${qLabel(q, qs)}</span>${esc(q.stem)}</p>
          <button class="doubt ${SES.doubts[q.uid] ? 'on' : ''}" data-doubt="${esc(q.uid)}" title="Marca si dudas: al corregir verás si te compensó arriesgar">${SES.doubts[q.uid] ? '✋ Dudosa' : '✋ Dudo'}</button></div>
        ${Object.entries(q.options).map(([l, t]) => `<button class="opt ${SES.answers[q.uid] === l ? 'sel' : ''}" data-q="${esc(q.uid)}" data-l="${l}"><span class="l">${l})</span><span>${esc(t)}</span></button>`).join('')}
      </div>`).join('');
    $('#site-header').classList.add('hide');
    view(`
      <div class="bar"><div class="wrap">
        <a href="#/" class="small" id="exit" title="Salir (se guarda tu progreso)">✕</a>
        <strong class="small bar-title">${esc(SES.title)}</strong>
        <span class="small muted" id="progress"></span>
        <span class="timer" id="timer">--:--</span>
        <button class="btn small" id="submit">Entregar</button>
      </div></div>
      <div class="wrap" style="padding-top:14px;padding-bottom:60px">
        ${tabs}
        ${choiceHtml}
        ${nav}
        ${qHtml || (p.choices ? '' : '<p class="muted">No hay preguntas.</p>')}
        ${qs.length ? `<div class="cta-row">${pi < SES.parts.length - 1 ? `<button class="btn ghost" data-part="${pi + 1}">Ir a ${esc(SES.parts[pi + 1].title)} →</button>` : ''}<button class="btn" id="submit2">Entregar examen</button></div>` : ''}
      </div>`);
    function progress() {
      const n = SES.parts.reduce((s, pp, i) => s + scoredSet(partQs(pp, i)).filter(q => SES.answers[q.uid]).length, 0);
      $('#progress').textContent = `${n}/${allScored}`;
    }
    progress();
    const tick = () => {
      const left = timeLeft();
      const t = $('#timer');
      if (!t) return;
      t.textContent = fmtTime(left);
      t.classList.toggle('low', left < 5 * 60000);
      if (left <= 0) { alert('¡Tiempo! El examen se entrega automáticamente.'); submit(true); }
    };
    clearInterval(TICK); tick(); TICK = setInterval(tick, 1000);
    $('#submit').onclick = () => submit(false);
    const s2 = $('#submit2'); if (s2) s2.onclick = () => submit(false);
    $('#exit').onclick = (e) => { e.preventDefault(); clearInterval(TICK); location.hash = '#/'; };
    app.onclick = (e) => {
      const o = e.target.closest('.opt');
      if (o && o.dataset.q) {
        const uid = o.dataset.q, l = o.dataset.l;
        if (SES.answers[uid] === l) delete SES.answers[uid]; else SES.answers[uid] = l;
        save();
        $$(`.opt[data-q="${CSS.escape(uid)}"]`).forEach(b => b.classList.toggle('sel', SES.answers[uid] === b.dataset.l));
        const idx = qs.findIndex(q => q.uid === uid);
        const nv = $(`[data-jump="${idx}"]`); if (nv) nv.classList.toggle('done', !!SES.answers[uid]);
        progress();
        return;
      }
      const d = e.target.closest('[data-doubt]');
      if (d) {
        const uid = d.dataset.doubt;
        if (SES.doubts[uid]) delete SES.doubts[uid]; else SES.doubts[uid] = true;
        save();
        d.classList.toggle('on', !!SES.doubts[uid]); d.textContent = SES.doubts[uid] ? '✋ Dudosa' : '✋ Dudo';
        const idx = qs.findIndex(q => q.uid === uid);
        const nv = $(`[data-jump="${idx}"]`); if (nv) nv.classList.toggle('dq', !!SES.doubts[uid]);
        return;
      }
      const t = e.target.closest('[data-part]');
      if (t) { SES.active = +t.dataset.part; save(); run(); return; }
      const c = e.target.closest('[data-choose]');
      if (c) { SES.chosen[pi] = +c.dataset.choose; save(); run(); return; }
      const j = e.target.closest('[data-jump]');
      if (j) { e.preventDefault(); const el = $('#q-' + j.dataset.jump); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    };
  }

  // Free word-of-mouth: let candidates pass the simulator to their study group.
  function shareBox() {
    const url = C.siteUrl || 'https://simucanarias.pages.dev/';
    const text = 'Estoy practicando el ejercicio único del Gobierno de Canarias con exámenes oficiales y la corrección real de 2026 (calculadora y examen completo gratis):';
    const enc = encodeURIComponent;
    return `<div class="card" style="margin:18px 0"><h3>¿Conoces a alguien que oposite?</h3>
      <p class="small muted">Pásale el simulador a tu grupo de estudio: la parte gratuita funciona sin registro.</p>
      <div class="cta-row" style="margin-bottom:0">
        <a class="btn small" href="https://wa.me/?text=${enc(text + ' ' + url)}" target="_blank" rel="noopener">Compartir por WhatsApp</a>
        <a class="btn small ghost" href="https://t.me/share/url?url=${enc(url)}&text=${enc(text)}" target="_blank" rel="noopener">Telegram</a>
        <button class="btn small ghost" type="button" data-copy="${esc(url)}">Copiar enlace</button>
      </div></div>`;
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    const done = () => { b.textContent = '¡Copiado!'; setTimeout(() => { b.textContent = 'Copiar enlace'; }, 1500); };
    try { navigator.clipboard.writeText(b.dataset.copy).then(done, () => prompt('Copia el enlace:', b.dataset.copy)); } catch { prompt('Copia el enlace:', b.dataset.copy); }
  });

  function result(filter) {
    SES = LS.get(SKEY, null) || SES;
    if (!SES || !SES.done) { location.hash = '#/'; return; }
    clearInterval(TICK);
    $('#site-header').classList.remove('hide');
    const R = SES.result;
    const keep = !!filter;
    filter = filter || 'all';
    const partCard = (r) => {
      const g = S.RULES[r.kind].group;
      const doubtLine = (r.dc + r.dw) ? `<p class="small">Marcaste <strong>${r.dc + r.dw}</strong> como dudosas y respondidas (${r.dc} bien, ${r.dw} mal). Si las hubieras dejado en blanco: <strong>${S.fmt(r.altMark)}</strong> en lugar de ${S.fmt(r.mark)} → ${r.altMark > r.mark ? '<span class="tag warn">te habría compensado dejarlas en blanco</span>' : r.altMark < r.mark ? '<span class="tag ok">arriesgar te compensó</span>' : '<span class="tag">daba igual</span>'}.</p>` : '<p class="small muted">Consejo: marca con ✋ las preguntas en las que dudes y aquí verás si te compensa arriesgar.</p>';
      return `<div class="card">
        <h3>${esc(r.title)}</h3>
        <div class="big">${S.fmt(r.mark)} <span class="tag ${r.pass ? 'ok' : 'bad'}">${r.pass ? 'Superada' : 'No superada'}</span></div>
        <div class="kpis"><div class="kpi"><b>${r.c}</b><span>aciertos</span></div><div class="kpi"><b>${r.w}</b><span>fallos</span></div><div class="kpi"><b>${r.b}</b><span>en blanco</span></div><div class="kpi"><b>−${S.fmt(r.penalty)}</b><span>penalización</span></div></div>
        <p class="small muted">${r.n} preguntas puntuables · ${S.fmt(r.value)} por acierto · −${S.fmt(r.value)} por cada ${g} fallos. ${r.w % g ? `Tu último grupo de fallos quedó incompleto: ${plural(r.w % g, 'fallo')} sin coste.` : ''}</p>
        ${doubtLine}
      </div>`;
    };
    const verdict = R.ex ? `<div class="verdict ${R.ex.pass ? 'ok' : 'bad'}">Nota del ejercicio: ${S.fmt(R.ex.mean)} — ${R.ex.pass ? 'APTO' : 'NO APTO'} (mínimo 5 en cada parte y de media)</div>` : '';
    // Review list
    const items = [];
    SES.parts.forEach((p, pi) => {
      const qs = partQs(p, pi);
      const pr = R.parts[pi];
      if (p.choices && SES.chosen[pi] != null) items.push({ ctx: p.choices[SES.chosen[pi]] });
      qs.forEach(q => items.push({ q, qs, p, st: pr.per[q.uid] || (q.reserve || q.annulled ? 'reserve' : 'blank'), pi }));
    });
    const show = (it) => filter === 'all' || (filter === 'ko' && it.st === 'ko') || (filter === 'blank' && it.st === 'blank') || (filter === 'doubt' && SES.doubts[it.q.uid]);
    const review = items.map(it => {
      if (it.ctx) return filter === 'all' ? `<details class="context" style="margin:12px 0"><summary><strong>Enunciado: ${esc(it.ctx.title)}</strong></summary>\n${esc(it.ctx.context)}</details>` : '';
      if (!show(it)) return '';
      const q = it.q, a = SES.answers[q.uid];
      const badge = it.st === 'ok' ? '<span class="tag ok">Acierto</span>' : it.st === 'ko' ? '<span class="tag bad">Fallo</span>' : it.st === 'reserve' ? `<span class="tag">${q.annulled ? 'Excluida (no puntúa)' : 'Reserva (no puntúa)'}</span>` : '<span class="tag">En blanco</span>';
      return `<div class="q">
        ${ctxBox(q, it.p)}<div class="qhead"><p class="stem"><span class="num">${qLabel(q, it.qs)}</span>${esc(q.stem)}</p><div>${badge} ${SES.doubts[q.uid] ? '<span class="tag warn">Dudosa</span>' : ''}</div></div>
        ${Object.entries(q.options).map(([l, t]) => `<button disabled class="opt ${l === q.answer ? 'right' : ''} ${a === l && l !== q.answer ? 'wrong' : ''}"><span class="l">${l})</span><span>${esc(t)}${l === q.answer ? ' ✓' : ''}${a === l && l !== q.answer ? ' ✗ (tu respuesta)' : ''}</span></button>`).join('')}
        ${q.note ? `<p class="small notice">${esc(q.note)}</p>` : ''}
        <p class="src">Pregunta ${q.reserve ? 'de reserva ' : ''}${q.n} · <a href="${esc(q.srcUrl)}" target="_blank" rel="noopener">${esc(q.src)}</a> · respuesta según la plantilla oficial publicada ${esc(q.srcDate)}</p>
      </div>`;
    }).join('');
    const upsell = PRO ? '' : `<div class="card" style="border-color:var(--sun);margin:18px 0"><h3>¿Te ha servido?</h3><p class="small">Con el <strong>Pase hasta el examen</strong> (${esc(C.price)}, pago único) haces el simulacro completo cronometrado (test + 1 de 2 supuestos oficiales), todos los exámenes oficiales C1 y C2, tests aleatorios y repaso de falladas.</p><button class="btn sun" data-buy>Desbloquear por ${esc(C.price)}</button></div>`;
    view(`<div class="wrap" style="padding-top:24px;padding-bottom:50px">
      <a href="#/">← Volver al simulador</a>
      <h1 style="margin-top:10px">Resultado</h1>
      <p class="muted">${esc(SES.title)}${R.auto ? ' · entregado al acabarse el tiempo' : ''} · ${Math.round((R.finished - SES.started) / 60000)} min</p>
      ${verdict}
      <div class="grid2" style="margin-top:14px">${R.parts.map(partCard).join('')}</div>
      ${upsell}
      ${shareBox()}
      <h2 style="margin-top:28px;scroll-margin-top:12px" id="review">Revisión</h2>
      <div class="tabs">${[['all', 'Todas'], ['ko', 'Falladas'], ['blank', 'En blanco'], ['doubt', 'Dudosas']].map(([k, l]) => `<a class="tab ${filter === k ? 'on' : ''}" href="#/result/${k}" style="text-decoration:none">${l}</a>`).join('')}</div>
      ${review || '<p class="muted" style="margin-top:14px">No hay preguntas en este filtro.</p>'}
      <div class="cta-row"><a class="btn" href="#/">Hacer otro</a></div>
    </div>`, keep);
    if (keep) { const rv = $('#review'); if (rv) rv.scrollIntoView(); }
  }

  // ---------------- Router ----------------
  async function guardPro(fn) { if (!PRO) { await home(); openBuy(); return; } await fn(); }
  async function route() {
    const h = location.hash.replace(/^#\/?/, '');
    const [r, a, b] = h.split('/');
    try {
      if (r === 'run') return run();
      if (r === 'result') return result(a);
      if (r === 'exam' && a) {
        if (locked(a)) return lockedPreview(a);
        return startGuarded(() => buildExam(a));
      }
      if (r === 'sim' && a) return guardPro(() => startGuarded(() => buildSimulacro(a, false)));
      if (r === 'p2' && a) return guardPro(() => startGuarded(() => buildSimulacro(a, true)));
      if (r === 'random') return guardPro(() => startGuarded(() => buildRandom(a || 'all', +(b || 25))));
      if (r === 'falladas') return guardPro(async () => {
        const qs = await falladasQs();
        if (!qs.length) { location.hash = '#/'; return; }
        await startGuarded(async () => ({ title: `Repaso de falladas · ${plural(qs.length, 'pregunta')}`, minutes: Math.max(5, qs.length), practice: true, parts: [{ kind: 'general', title: 'Repaso', questions: renumber(qs) }] }));
      });
      return home();
    } catch (err) {
      view(`<div class="wrap" style="padding:40px 16px"><p>Ha ocurrido un error: ${esc(err.message)}</p><a href="#/">Volver</a></div>`);
    }
  }
  window.addEventListener('hashchange', route);
  route();
})();
