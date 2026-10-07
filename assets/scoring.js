// Scoring rules of the "ejercicio único" (BOC n.º 57, 24/03/2026, Bases 21-23).
// Parte 1 (test general): +0,20 per correct; -0,20 per COMPLETE group of 3 wrong (Base 22.5).
// Parte 2 (supuesto práctico): +0,40 per correct; -0,40 per COMPLETE group of 2 wrong (Base 23.6).
// Blanks never penalise. Each part is 0-10 and needs >= 5; the exercise mark is the mean (Base 21.5).
// With N scored questions other than 50/25, every question is worth 10/N (proportional rule, Bases 22.2 / 23.2).
(function (global) {
  const RULES = {
    general: { group: 3, defaultN: 50, label: 'Parte 1 · Test' },
    practico: { group: 2, defaultN: 25, label: 'Parte 2 · Supuesto práctico' },
  };
  const r3 = (x) => Math.round(x * 1000) / 1000;

  function score(kind, correct, wrong, n) {
    const rule = RULES[kind];
    n = n || rule.defaultN;
    const value = 10 / n;
    const groups = Math.floor(wrong / rule.group);
    const raw = correct * value - groups * value;
    const mark = r3(Math.max(0, Math.min(10, raw)));
    return {
      mark,
      value: r3(value),
      penalty: r3(groups * value),
      groups,
      pass: mark >= 5,
      // How many more wrong answers are "free" before the next penalty kicks in.
      freeWrongsLeft: rule.group - 1 - (wrong % rule.group),
      nextWrongCost: (wrong + 1) % rule.group === 0 ? r3(value) : 0,
    };
  }

  function exercise(mark1, mark2) {
    const mean = r3((mark1 + mark2) / 2);
    return { mean, pass: mark1 >= 5 && mark2 >= 5 && mean >= 5 };
  }

  // Expected value of answering a question you would otherwise leave blank,
  // when you can rule out `eliminated` of the 4 options and guess among the rest.
  function guessEV(kind, eliminated) {
    const rule = RULES[kind];
    const value = 10 / rule.defaultN;
    const p = 1 / (4 - eliminated);
    const avgWrongCost = value / rule.group;
    return r3(p * value - (1 - p) * avgWrongCost);
  }

  const fmt = (x, d = 2) => Number(x).toLocaleString('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d });

  global.Scoring = { RULES, score, exercise, guessEV, fmt };
})(window);
