"""OAI-client: paginering met resumptionToken, completeListSize, fouten en schoonmaken van de XML."""
import xml.etree.ElementTree as ET

import pytest

import oai_client

NS = 'http://www.openarchives.org/OAI/2.0/'


def _page(ids, token='', size=5):
    records = ''.join(f'<record><header><identifier>t:{i}</identifier><datestamp>2026-01-01T00:00:00Z</datestamp>'
                      f'</header><metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
                      f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{i}</dc:title></oai_dc:dc></metadata></record>'
                      for i in ids)
    return ET.fromstring(f'<OAI-PMH xmlns="{NS}"><ListRecords>{records}'
                         f'<resumptionToken completeListSize="{size}">{token}</resumptionToken></ListRecords></OAI-PMH>')


def test_pagineert_met_resumptiontoken_en_onthoudt_completelistsize(monkeypatch):
    pages = [_page([1, 2, 3], 'volgende'), _page([4, 5], '')]
    urls = []

    def fake(url, retries=5, backoff=2.0):
        urls.append(url)
        return pages[len(urls) - 1]
    monkeypatch.setattr(oai_client, 'fetch_and_parse', fake)
    state = {}
    records = list(oai_client.iter_records('http://x/key/abc/', 'tenant:rce:search_s_entity_type:photos', 'oai_dc',
                                           state, sleep_between=0))
    assert [h['identifier'] for h, _ in records] == ['t:1', 't:2', 't:3', 't:4', 't:5']
    assert state == {'seen': 5, 'complete_list_size': 5}
    assert 'set=tenant%3Arce%3Asearch_s_entity_type%3Aphotos' in urls[0]
    # een vervolgverzoek bevat alleen verb en resumptionToken
    assert urls[1].endswith('?verb=ListRecords&resumptionToken=volgende')


def test_max_records_stopt_vroeg(monkeypatch):
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: _page([1, 2, 3], 'volgende'))
    records = list(oai_client.iter_records('http://x/', 's', 'oai_dc', {}, sleep_between=0, max_records=2))
    assert len(records) == 2


def test_noRecordsMatch_is_een_lege_set(monkeypatch):
    root = ET.fromstring(f'<OAI-PMH xmlns="{NS}"><error code="noRecordsMatch"/></OAI-PMH>')
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: root)
    assert list(oai_client.iter_records('http://x/', 's', 'oai_dc', {}, sleep_between=0)) == []


def test_andere_oai_fout_gooit_een_uitzondering(monkeypatch):
    root = ET.fromstring(f'<OAI-PMH xmlns="{NS}"><error code="badArgument">kapot</error></OAI-PMH>')
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: root)
    with pytest.raises(oai_client.OaiError):
        list(oai_client.iter_records('http://x/', 's', 'oai_dc', {}, sleep_between=0))


def test_verwijderd_record_wordt_gemeld(monkeypatch):
    root = ET.fromstring(f'<OAI-PMH xmlns="{NS}"><ListRecords><record><header status="deleted"><identifier>t:1</identifier>'
                         f'<datestamp>2026-01-01T00:00:00Z</datestamp></header></record></ListRecords></OAI-PMH>')
    monkeypatch.setattr(oai_client, 'fetch_and_parse', lambda *a, **k: root)
    (header, element), = oai_client.iter_records('http://x/', 's', 'oai_dc', {}, sleep_between=0)
    assert header['deleted'] and element is None


def test_losse_ampersand_en_stuurtekens_worden_hersteld(monkeypatch):
    xml = ('<?xml version="1.0"?><OAI-PMH xmlns="%s"><ListRecords><record><header><identifier>t:1</identifier></header>'
           '<metadata><d>Adlib priref F&D 1\x0b</d></metadata></record></ListRecords></OAI-PMH>' % NS)
    monkeypatch.setattr(oai_client, '_open', lambda *a, **k: xml.encode('utf-8'))
    root = oai_client.fetch_and_parse('http://x/')
    assert root.find(f'.//{{{NS}}}d').text == 'Adlib priref F&D 1'


def test_redact():
    assert oai_client.redact('https://h/api/oai/rce/key/geheim/?verb=x') == 'https://h/api/oai/rce/key/***/?verb=x'
