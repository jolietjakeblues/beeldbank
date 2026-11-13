import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures'
sys.path.insert(0, str(ROOT / 'src'))

import transform_service  # noqa: E402
import uris  # noqa: E402

OAI = {'o': 'http://www.openarchives.org/OAI/2.0/'}

# Alle sets waarvoor een fixture bestaat. In de config staat alleen `photos` aan; de rest wordt wel getest, zodat het
# aanzetten van een set geen onbeproefde code raakt.
ALL_SOURCES = {
    'photos': {'kind': 'photo', 'set': 'tenant:rce:search_s_entity_type:photos'},
    'architectural_drawings': {'kind': 'drawing', 'set': 'tenant:rce:search_s_entity_type:architectural_drawings'},
    'old_prints_and_drawings': {'kind': 'print', 'set': 'tenant:rce:search_s_entity_type:old_prints_and_drawings'},
    'minuutplans': {'kind': 'map', 'set': 'tenant:rce:search_s_entity_type:minuutplans'},
    'verzamelplans': {'kind': 'map', 'set': 'tenant:rce:search_s_entity_type:verzamelplans'},
    'oat': {'kind': 'table', 'set': 'tenant:rce:search_s_entity_type:oat'},
}


@pytest.fixture(scope='session')
def config():
    with open(ROOT / 'config' / 'config.yml', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(autouse=True)
def omgeving(monkeypatch):
    monkeypatch.setenv('CONFIG_PATH', str(ROOT / 'config' / 'config.yml'))
    monkeypatch.setenv('MEMORIX_OAI_KEY', 'testsleutel')


def fixture_records(source: str) -> list:
    """[(header, fields)] uit een fixture met echte OAI-records van die set."""
    root = ET.parse(FIXTURES / f'{source}.xml').getroot()
    records = []
    for rec in root.findall('.//o:record', OAI):
        header = {'identifier': rec.find('o:header/o:identifier', OAI).text.strip(),
                  'datestamp': rec.find('o:header/o:datestamp', OAI).text.strip(), 'deleted': False}
        records.append((header, transform_service.collect_fields(rec.find('o:metadata', OAI)[0])))
    return records


def build_graph(config: dict, source: str):
    graph = uris.get_dataset(config)
    for header, fields in fixture_records(source):
        transform_service.transform_record(graph, config, header, fields, ALL_SOURCES[source])
    return graph


@pytest.fixture
def graph_for(config):
    return lambda source: build_graph(config, source)
