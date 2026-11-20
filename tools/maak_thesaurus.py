"""Maakt config/thesaurus.json.gz: woord -> URI van het concept in de CHT of de ABR.

De OAI levert onderwerpen als tekst ("forten"), zonder URI. Deze lijst zoekt het woord op in de thesauri van de RCE, die als graph in
het CHO-endpoint staan. Er wordt alleen een URI opgenomen als het woord ondubbelzinnig is; bij twijfel (bijvoorbeeld "forten":
verdedigingswerk of stookplaats) staat het woord niet in de lijst. Er wordt dus nooit gegokt.

Volgorde per woord, per thesaurus (eerst de CHT, dan alleen als de CHT niets heeft de ABR):
  1. gelijk aan de voorkeursterm (prefLabel)                  "kastelen (versterkte woning)"
  2. gelijk aan de voorkeursterm zonder de toelichting        "kastelen"  (vindt "kastelen (versterkte woning)")
  3. gelijk aan een alternatieve term (altLabel)              "fort"
Binnen een stap telt een woord als ondubbelzinnig bij precies één concept; zijn er twee of meer, dan stopt het zoeken voor dat woord.
Concepten met status gidsterm, twijfelachtig, vervallen of onbekend worden overgeslagen.

Gebruik:  python tools/maak_thesaurus.py          (vernieuwt config/thesaurus.json.gz; kost enkele minuten)
"""
import collections
import datetime
import gzip
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from transform_service import norm_label  # noqa: E402

ENDPOINT = 'https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/cho/services/cho/sparql'
THESAURI = ['cht', 'abr/2']                      # volgorde = voorrang
# statussen die wel mogen: definitief en kandidaat (en concepten zonder status)
OK_STATUS = {'aad68581-3960-4faf-9758-8ff6d65810d3', 'c58475d5-0795-4623-b4be-ea1524f4b4fb'}
PREFIX = ('PREFIX skos: <http://www.w3.org/2004/02/skos/core#> '
          'PREFIX rnce: <https://data.cultureelerfgoed.nl/id/rnce#>\n')
PAGE = 8000
CONCEPT_URI = re.compile(r'^https://data\.cultureelerfgoed\.nl/term/id/(cht|abr/2)/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
# een concept dat we kennen, om te controleren dat labels bij het goede concept horen
KNOWN = {'cht': ('https://data.cultureelerfgoed.nl/term/id/cht/15423a8e-7588-41ad-a922-8d3c5161a7fa', 'forten (verdedigingswerk)')}


def query(text: str) -> list:
    req = urllib.request.Request(ENDPOINT, data=urllib.parse.urlencode({'query': PREFIX + text}).encode(),
                                 headers={'Accept': 'application/sparql-results+json'})
    return json.load(urllib.request.urlopen(req, timeout=600))['results']['bindings']


def pages(body: str, variables: str):
    """Alle rijen, per pagina op volgorde van ?c (het endpoint staat geen OFFSET boven 10.000 toe)."""
    seen, last = set(), None
    while True:
        flt = f'FILTER(?c >= <{last}>)' if last else ''
        rows = query(f'SELECT {variables} WHERE {{ {body} {flt} }} ORDER BY ?c LIMIT {PAGE}')
        new = 0
        for r in rows:
            key = tuple(sorted((k, v['value']) for k, v in r.items()))
            if key not in seen:
                seen.add(key)
                new += 1
                yield r
        if len(rows) < PAGE or new == 0:
            return
        last = rows[-1]['c']['value']


def load(thesaurus: str) -> dict:
    # Twee eigenaardigheden van het endpoint: een FILTER op de taal samen met ORDER BY en een grote LIMIT geeft bij elk concept
    # hetzelfde label terug, en OPTIONAL met ORDER BY geeft verkeerde labels. Daarom losse, eenvoudige queries en de taal
    # (nl) in Python filteren. Daarna controleert sanity_check() het resultaat.
    graph = f'GRAPH <https://data.cultureelerfgoed.nl/term/id/{thesaurus}/thesaurus>'
    pref = list(pages(f'{graph} {{ ?c a skos:Concept ; skos:prefLabel ?l }}', '?c ?l'))
    alt = list(pages(f'{graph} {{ ?c a skos:Concept ; skos:altLabel ?l }}', '?c ?l'))
    status = list(pages(f'{graph} {{ ?c a skos:Concept ; rnce:hasConceptStatus ?s }}', '?c ?s'))
    dutch = lambda rows: [r for r in rows if r['l'].get('xml:lang') == 'nl' and CONCEPT_URI.match(r['c']['value'])]
    return {'pref': dutch(pref), 'alt': dutch(alt), 'status': status}


def sanity_check(thesaurus: str, data: dict):
    """Stop als de download niet klopt: hetzelfde label bij honderden concepten, of een bekend concept met een ander label."""
    counts = collections.Counter(r['l']['value'] for r in data['pref'])
    label, n = counts.most_common(1)[0]
    if n > 50:
        raise SystemExit(f'{thesaurus}: label "{label}" komt {n} keer voor; de download is niet betrouwbaar.')
    known = KNOWN.get(thesaurus)
    if known:
        got = {r['c']['value']: r['l']['value'] for r in data['pref']}.get(known[0])
        if got != known[1]:
            raise SystemExit(f'{thesaurus}: {known[0]} heeft label {got!r}, verwacht {known[1]!r}.')


def strip_note(label: str) -> str:
    return re.sub(r'\s*\([^)]*\)\s*$', '', label)


def build_index(data: dict) -> dict:
    """{genormeerd woord: URI, of None bij een dubbelzinnig woord}; de drie stappen samengevoegd."""
    blocked = {r['c']['value'] for r in data['status'] if r['s']['value'].rsplit('/', 1)[1] not in OK_STATUS}
    steps = [collections.defaultdict(set) for _ in range(3)]
    for r in data['pref']:
        if r['c']['value'] in blocked:
            continue
        steps[0][norm_label(r['l']['value'])].add(r['c']['value'])
        steps[1][norm_label(strip_note(r['l']['value']))].add(r['c']['value'])
    for r in data['alt']:
        if r['c']['value'] not in blocked:
            steps[2][norm_label(r['l']['value'])].add(r['c']['value'])
    result = {}
    for word in set().union(*steps):
        for step in steps:
            hit = step.get(word)
            if hit:
                result[word] = next(iter(hit)) if len(hit) == 1 else None
                break
    return result


def main():
    labels, ambiguous = {}, set()
    for thesaurus in THESAURI:
        print(f'{thesaurus}: ophalen ...', flush=True)
        data = load(thesaurus)
        sanity_check(thesaurus, data)
        index = build_index(data)
        print(f'{thesaurus}: {sum(1 for v in index.values() if v)} ondubbelzinnig, {sum(1 for v in index.values() if not v)} dubbelzinnig')
        for word, uri in index.items():
            if word in labels or word in ambiguous:
                continue                           # een eerdere thesaurus heeft voorrang
            if uri:
                labels[word] = uri
            else:
                ambiguous.add(word)
    out = {'gemaakt': datetime.date.today().isoformat(), 'bron': ENDPOINT, 'thesauri': THESAURI,
           'labels': dict(sorted(labels.items()))}
    path = ROOT / 'config' / 'thesaurus.json.gz'
    with gzip.open(path, 'wt', encoding='utf-8', compresslevel=9) as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(labels)} woorden naar {path} ({path.stat().st_size // 1024} kB); {len(ambiguous)} dubbelzinnig, niet opgenomen')


if __name__ == '__main__':
    main()
