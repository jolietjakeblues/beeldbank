"""Maakt de testfixtures: de eerste records van elke OAI-set, als echte OAI-pagina.

Gebruik (de sleutel komt uit de omgeving, nooit uit een bestand):
    MEMORIX_OAI_KEY=... python tools/maak_fixtures.py
"""
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

import yaml  # noqa: E402

import oai_client  # noqa: E402

AANTAL = {'photos': 14}          # standaard 6 records per set
OAI = 'http://www.openarchives.org/OAI/2.0/'


def main() -> int:
    key = os.environ.get('MEMORIX_OAI_KEY')
    if not key:
        print('Zet MEMORIX_OAI_KEY in de omgeving.')
        return 2
    config = yaml.safe_load((ROOT / 'config' / 'config.yml').read_text(encoding='utf-8'))
    base = config['SRC_URI'].format(MEMORIX_OAI_KEY=key)
    ET.register_namespace('', OAI)
    for name, source in config['SOURCES'].items():
        url = oai_client.build_url(base, {'verb': 'ListRecords', 'metadataPrefix': config['SRC_PREFIX'], 'set': source['set']})
        root = oai_client.fetch_and_parse(url)
        container = root.find(f'{{{OAI}}}ListRecords')
        for record in container.findall(f'{{{OAI}}}record')[AANTAL.get(name, 6):]:
            container.remove(record)
        for token in container.findall(f'{{{OAI}}}resumptionToken'):
            container.remove(token)
        for request in root.findall(f'{{{OAI}}}request'):
            request.text = 'https://example.org/oai'                 # de sleutel hoort niet in een fixture
            request.attrib.clear()
        path = ROOT / 'tests' / 'fixtures' / f'{name}.xml'
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        print(f'{path.name}: {len(container.findall(f"{{{OAI}}}record"))} records')
    return 0


if __name__ == '__main__':
    sys.exit(main())
