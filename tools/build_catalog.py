"""Normalise exam JSON files (NFC, LF) and rebuild data/catalog.json."""
import json, glob, os, unicodedata

ROOT = os.path.join(os.path.dirname(__file__), '..', 'data')
ORDER = ['c2-2022-libre-test2', 'c2-2022-libre-supuestos', 'c1-2024-pi-teorico',
         'c1-2024-pi-supuesto-a', 'c1-2024-pi-supuesto-b', 'c1-2022-pi-test']
NOTES = {
    'c2-2022-libre-supuestos': 'Plantilla provisional publicada por el tribunal el 08/07/2024. En la convocatoria de 2022 cada supuesto tenía 10 preguntas: aquí se puntúa de forma proporcional sobre 10.',
    'c1-2024-pi-teorico': 'Examen de promoción interna con 3 opciones por pregunta.',
}

def nfc(x):
    if isinstance(x, str):
        return unicodedata.normalize('NFC', x).replace('\u0301', '')
    if isinstance(x, list):
        return [nfc(i) for i in x]
    if isinstance(x, dict):
        return {k: nfc(v) for k, v in x.items()}
    return x

exams = []
for path in glob.glob(os.path.join(ROOT, 'exams', '*.json')):
    with open(path, encoding='utf-8') as f:
        d = nfc(json.load(f))
    if d['id'] in NOTES:
        d['note'] = NOTES[d['id']]
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    exams.append({
        'id': d['id'], 'title': d['title'], 'group': d['group'], 'kind': d['kind'],
        'source_url': d['source_url'], 'published': d['published'], 'note': d.get('note', ''),
        'blocks': [{'title': b['title'], 'count': sum(not q['reserve'] for q in b['questions']),
                    'reserves': sum(q['reserve'] for q in b['questions'])} for b in d['blocks']],
    })
exams.sort(key=lambda e: ORDER.index(e['id']) if e['id'] in ORDER else 99)
with open(os.path.join(ROOT, 'catalog.json'), 'w', encoding='utf-8', newline='\n') as f:
    json.dump({'exams': exams}, f, ensure_ascii=False, indent=1)
total = sum(b['count'] + b['reserves'] for e in exams for b in e['blocks'])
print(len(exams), 'exams,', total, 'questions')
