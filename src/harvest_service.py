"""Oogst de Beeldbank van de RCE (Memorix OAI-PMH) en schrijf schema.org JSON-LD in chunks.

Gebruik:
    MEMORIX_OAI_KEY=... python src/harvest_service.py --source photos --chunks 7000
    MEMORIX_OAI_KEY=... python src/harvest_service.py --source all --max-records 50      # snelle test

Bronnen (zie config/config.yml): elke bron is een OAI-set van tenant `rce`.

Per bron ontstaan `{CACHE_PATH}{bron}-0000.jsonld`, `-0001.jsonld`, ... en `{CACHE_PATH}manifest-{bron}.json`.
Controles (de run faalt, zodat er niets gepubliceerd wordt):
  - opgehaald == completeListSize van de bron;
  - weggeschreven + fouten + overgeslagen == opgehaald (niets raakt stilzwijgend kwijt);
  - geen record dat twee keer wordt geleverd;
  - het aantal transformatiefouten blijft binnen MAX_RECORD_ERRORS.
"""
import argparse
import datetime
import json
import logging
import os
import sys
import traceback

import yaml
from rdflib import Graph

import oai_client
import transform_service
import uris

logger = logging.getLogger(__name__)


def load_config(path: str = None) -> dict:
    path = path or os.getenv('CONFIG_PATH', 'config/config.yml')
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def source_url(config: dict) -> str:
    """De OAI-basis-URL met de sleutel uit de omgeving."""
    key = os.getenv('MEMORIX_OAI_KEY', '').strip()
    if not key:
        raise SystemExit('MEMORIX_OAI_KEY ontbreekt in de omgeving (GitHub: secret MEMORIX_OAI_KEY).')
    return config['SRC_URI'].format(MEMORIX_OAI_KEY=key)


class ChunkWriter:
    """Verzamelt records in een graph en schrijft elke `chunk_size` records een bestand weg.

    Elke chunk bevat de dataset- en organisatie-node, zodat elk bestand op zichzelf valideerbaar is."""

    def __init__(self, config: dict, cache_path: str, source_name: str, chunk_size: int, state: dict):
        self.config, self.cache_path, self.source_name = config, cache_path, source_name
        self.chunk_size, self.state = chunk_size, state
        self.graph, self.count = uris.get_dataset(config), 0

    def add(self, header: dict, fields: dict, source: dict) -> bool:
        """Transformeer één record in de huidige chunk. Een fout telt, en het record blijft buiten de graph."""
        scratch = Graph()
        try:
            transform_service.transform_record(scratch, self.config, header, fields, source)
        except Exception as e:  # niet stilzwijgend doorgaan: tel de fout, de run beoordeelt het totaal
            self.state['errors'] += 1
            self.state['error_ids'].append(header.get('identifier'))
            logger.warning('Fout bij transformatie van %s: %s', header.get('identifier'),
                           ''.join(traceback.format_exception_only(type(e), e)).strip())
            return False
        self.graph += scratch
        self.count += 1
        if self.count >= self.chunk_size:
            self.flush()
        return True

    def flush(self):
        if self.count == 0:
            return
        path = f"{self.cache_path}{self.source_name}-{self.state['files']:04d}.jsonld"
        self.graph.serialize(format='json-ld', destination=path, encoding='utf-8', auto_compact=True)
        logger.info('Geschreven: %s (%d records, %.0f KB)', path, self.count, os.path.getsize(path) / 1000)
        self.state['files'] += 1
        self.state['written'] += self.count
        self.graph, self.count = uris.get_dataset(self.config), 0


def new_state() -> dict:
    return {'oai_seen': 0, 'oai_expected': None, 'skipped': 0, 'skipped_reasons': {}, 'duplicates': 0,
            'errors': 0, 'error_ids': [], 'skipped_ids': [], 'written': 0, 'files': 0, 'limited': False}


def _skip(state: dict, reason: str):
    state['skipped'] += 1
    state['skipped_reasons'][reason] = state['skipped_reasons'].get(reason, 0) + 1


def harvest_source(config: dict, source_name: str, cache_path: str, chunk_size: int, max_records=None) -> dict:
    """Oogst één bron en geef de state terug (tellers, volledigheid)."""
    source = config['SOURCES'][source_name]
    state = new_state()
    state['limited'] = max_records is not None
    writer = ChunkWriter(config, cache_path, source_name, chunk_size, state)
    oai_state = {}
    seen_ids = set()
    logger.info('Start oogst %s (set %s, %s)', source_name, source['set'], source['kind'])
    for header, element in oai_client.iter_records(
            source_url(config), source['set'], config.get('SRC_PREFIX', 'oai_dc'), oai_state,
            sleep_between=float(config.get('SRC_SLEEP', 0.1)), retries=int(config.get('SRC_RETRIES', 5)),
            backoff=float(config.get('SRC_BACKOFF', 2.0)), max_records=max_records):
        if header['deleted']:
            _skip(state, 'deleted')
        elif element is None:
            _skip(state, 'geen metadata')
        elif not header['identifier']:
            _skip(state, 'geen identifier')
        elif header['identifier'] in seen_ids:
            state['duplicates'] += 1
            _skip(state, 'dubbel geleverd')
        else:
            seen_ids.add(header['identifier'])
            fields = transform_service.collect_fields(element)
            if transform_service.is_empty(fields):
                _skip(state, 'leeg record (alleen een link, geen titel, nummer of beeld)')
                state['skipped_ids'].append(header['identifier'])
            else:
                writer.add(header, fields, source)
        if oai_state['seen'] % 20000 == 0:
            logger.info('%s: %d/%s records verwerkt', source_name, oai_state['seen'], oai_state.get('complete_list_size'))
    state['oai_seen'], state['oai_expected'] = oai_state.get('seen', 0), oai_state.get('complete_list_size')
    writer.flush()                       # ook de LAATSTE (kleinere) chunk moet weggeschreven worden
    return state


def verify_completeness(state: dict, max_record_errors: int) -> bool:
    """Vergelijk wat we gezien en verwerkt hebben met wat de bron aankondigt."""
    if state['limited']:
        logger.info('Beperkte run (--max-records): volledigheidscontrole overgeslagen.')
        return True
    ok = True
    if state['oai_expected'] is None:
        logger.error('De OAI gaf geen completeListSize; volledigheid kan niet worden gecontroleerd.')
        ok = False
    elif state['oai_seen'] != state['oai_expected']:
        logger.error('ONVOLLEDIG: bron kondigt %d records aan, %d opgehaald.', state['oai_expected'], state['oai_seen'])
        ok = False
    if state['written'] + state['errors'] + state['skipped'] != state['oai_seen']:
        logger.error('Rekenfout: weggeschreven (%d) + fouten (%d) + overgeslagen (%d) != opgehaald (%d).',
                     state['written'], state['errors'], state['skipped'], state['oai_seen'])
        ok = False
    if state['duplicates']:
        logger.error('%d records zijn dubbel geleverd; de paginering van de bron klopt niet.', state['duplicates'])
        ok = False
    if state['errors'] > max_record_errors:
        logger.error('%d records konden niet getransformeerd worden (toegestaan: %d): %s', state['errors'],
                     max_record_errors, ', '.join(map(str, state['error_ids'][:20])))
        ok = False
    logger.info('Controle: OAI %s/%s, weggeschreven=%d, fouten=%d, overgeslagen=%d -> %s', state['oai_seen'],
                state['oai_expected'], state['written'], state['errors'], state['skipped'], 'OK' if ok else 'MISLUKT')
    return ok


def write_manifest(cache_path: str, source_name: str, state: dict, complete: bool):
    keys = ('oai_seen', 'oai_expected', 'written', 'files', 'errors', 'skipped', 'skipped_reasons', 'duplicates')
    manifest = {k: state.get(k) for k in keys}
    manifest['source'] = source_name
    manifest['error_ids'] = state.get('error_ids', [])[:200]
    manifest['skipped_ids'] = state.get('skipped_ids', [])[:200]
    manifest['complete'] = complete
    manifest['finished_at'] = datetime.datetime.now().replace(microsecond=0).isoformat()
    with open(f'{cache_path}manifest-{source_name}.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)


def main(argv=None) -> int:
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO,
                        datefmt='%Y-%m-%d %H:%M:%S')
    parser = argparse.ArgumentParser('Beeldbank RCE ETL: oogst en transformeer')
    parser.add_argument('--source', default='all', help="Naam van de bron in config (bijv. photos) of 'all'.")
    parser.add_argument('--chunks', type=int, default=7000, help='Aantal records per JSON-LD-bestand.')
    parser.add_argument('--max-records', type=int, default=None, help='Stop na dit aantal records (test).')
    args = parser.parse_args(argv)

    config = load_config()
    cache_path = os.getenv('CACHE_PATH', 'data/')
    if not cache_path.endswith(('/', os.sep)):
        cache_path += '/'
    os.makedirs(cache_path, exist_ok=True)
    names = list(config['SOURCES']) if args.source == 'all' else [args.source]
    unknown = [n for n in names if n not in config['SOURCES']]
    if unknown:
        logger.error('Onbekende bron: %s (beschikbaar: %s)', ', '.join(unknown), ', '.join(config['SOURCES']))
        return 2

    all_ok = True
    for name in names:
        state = harvest_source(config, name, cache_path, args.chunks, args.max_records)
        complete = verify_completeness(state, int(config.get('MAX_RECORD_ERRORS', 0)))
        write_manifest(cache_path, name, state, complete)
        all_ok = all_ok and complete
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
