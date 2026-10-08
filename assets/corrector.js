// Plantilla corrector: reads the candidate's answers, keeps them in this browser and, once the official key is in
// window.PLANTILLAS, scores each part with the exam rules (Scoring.score), replacing annulled questions with reserves.
(function (global) {
  // "1A 2c 3- 4D" or "AC-D" -> ['a', 'c', '-', 'd']. Digits, spaces and punctuation are ignored; '-', 'x' and '_' mean blank.
  const parse = (s) => (s || '').toLowerCase().replace(/[^a-dx_\-]/g, '').replace(/[x_]/g, '-').split('');

  // key covers questions 1..n followed by the reserves; annulled holds 1-based question numbers.
  function part(kind, answers, key, n, annulled) {
    const ann = new Set(annulled || []);
    const main = [], res = [];
    for (let i = 1; i <= key.length; i++) (i <= n ? main : res).push(i);
    const lost = main.filter((i) => ann.has(i)).length;
    const scored = main.filter((i) => !ann.has(i)).concat(res.filter((i) => !ann.has(i)).slice(0, lost));
    let ok = 0, bad = 0, blank = 0;
    const wrong = [];
    for (const i of scored) {
      const u = answers[i - 1];
      if (!u || u === '-') blank++;
      else if (u === key[i - 1]) ok++;
      else { bad++; wrong.push(i); }
    }
    const s = global.Scoring.score(kind, ok, bad, scored.length);
    return { ok, bad, blank, n: scored.length, mark: s.mark, penalty: s.penalty, wrong };
  }

  global.SimuCorrector = { parse, part };
  if (typeof document === 'undefined' || !document.getElementById('cx-conv')) return;

  const $ = (id) => document.getElementById(id);
  const LS = 'simu_plantilla_v1';
  const load = () => { try { return JSON.parse(localStorage.getItem(LS)) || {}; } catch (e) { return {}; } };
  const save = (v) => { try { localStorage.setItem(LS, JSON.stringify(v)); } catch (e) { /* private mode: still works for this visit */ } };
  const fmt = (x) => x.toFixed(2).replace('.', ',');
  const sup = () => (document.querySelector('input[name="cx-sup"]:checked') || {}).value || 'A';

  function restore() {
    const d = load()[$('cx-conv').value] || {};
    $('cx-p1').value = d.p1 || '';
    $('cx-p2').value = d.p2 || '';
    const r = document.querySelector(`input[name="cx-sup"][value="${d.sup || 'A'}"]`);
    if (r) r.checked = true;
  }

  function persist() {
    const all = load();
    all[$('cx-conv').value] = { p1: $('cx-p1').value, p2: $('cx-p2').value, sup: sup() };
    save(all);
  }

  function line(label, r) {
    return `<p class="detail"><strong>${label}: ${fmt(r.mark)}</strong> · ${r.ok} aciertos, ${r.bad} fallos, ${r.blank} en blanco` +
      ` (${r.n} preguntas puntuables) · penalización ${fmt(r.penalty)}` +
      (r.wrong.length ? `<br>Fallos en: ${r.wrong.join(', ')}` : '') + '</p>';
  }

  function render() {
    const a1 = parse($('cx-p1').value), a2 = parse($('cx-p2').value);
    $('cx-c1').textContent = `${a1.length} respuestas leídas`;
    $('cx-c2').textContent = `${a2.length} respuestas leídas`;
    const K = (global.PLANTILLAS || {})[$('cx-conv').value];
    const out = $('cx-out');
    if (!K) {
      out.innerHTML = a1.length || a2.length
        ? '<p class="detail">Guardado en este navegador. La plantilla de esta convocatoria aún no se ha publicado: vuelve cuando salga y verás aquí tu nota, sin escribir nada otra vez.</p>'
        : '';
      return;
    }
    const k2 = K.p2 && K.p2[sup()];
    const r1 = part('general', a1, K.p1.key, K.p1.n, K.p1.annulled);
    const r2 = k2 ? part('practico', a2, k2.key, k2.n, k2.annulled) : null;
    const ex = r2 ? global.Scoring.exercise(r1.mark, r2.mark) : null;
    out.innerHTML = `<p class="small muted">Plantilla ${K.provisional ? 'provisional' : 'definitiva'} publicada el ${K.date}.</p>` +
      line('Parte 1 · test', r1) + (r2 ? line(`Parte 2 · supuesto ${sup()}`, r2) : '<p class="detail">Este supuesto no tiene plantilla.</p>') +
      (ex ? `<p class="verdict ${ex.pass ? 'ok' : 'ko'}">Nota del ejercicio: ${fmt(ex.mean)} · ${ex.pass ? 'APTO' : 'NO APTO'} (hace falta un 5 en cada parte y de media).</p>` : '') +
      '<div class="cta-row"><a class="btn ghost" href="../simulador">Seguir practicando con exámenes oficiales</a></div>';
  }

  $('cx-conv').addEventListener('change', () => { restore(); render(); });
  ['cx-p1', 'cx-p2'].forEach((id) => $(id).addEventListener('input', () => { persist(); render(); }));
  document.querySelectorAll('input[name="cx-sup"]').forEach((r) => r.addEventListener('change', () => { persist(); render(); }));
  $('cx-go').addEventListener('click', () => { persist(); render(); $('cx-out').scrollIntoView({ block: 'nearest' }); });
  restore();
  render();
})(typeof window !== 'undefined' ? window : globalThis);
