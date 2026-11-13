"""Volledigheid van de oogst: wat de run laat falen, de laatste chunk, en dat de sleutel nergens lekt."""
import json
import logging
import xml.etree.ElementTree as ET

import pytest

import harvest_service
import oai_client
from conftest import FIXTURES, OAI

PHOTOS = 14             # records in tests/fixtures/photos.xml


def _fixture_stream(announced=PHOTOS, extra=()):
    """Nep van oai_client.iter_records: de echte fixture-records, met een aangekondigd aantal."""
    root = ET.parse(FIXTURES / 'photos.xml').getroot()
    records = root.findall('.//o:record', OAI)

    def fake(base_url, set_spec, prefix, state, **kwargs):
        state['complete_list_size'] = announced
        state.setdefault('seen', 0)
        for rec in list(records) + list(extra):
            header = {'identifier': rec.find('o:header/o:identifier', OAI).text.strip(),
                      'datestamp': rec.find('o:header/o:datestamp', OAI).text.strip(), 'deleted': False}
            state['seen'] += 1
            yield header, rec.find('o:metadata', OAI)[0]
            if kwargs.get('max_records') and state['seen'] >= kwargs['max_records']:
                return
    return fake


def _run(config, tmp_path, monkeypatch, fake, chunk=5, max_records=None):
    monkeypatch.setattr(oai_client, 'iter_records', fake)
    state = harvest_service.harvest_source(config, 'photos', str(tmp_path) + '/', chunk, max_records)
    ok = harvest_service.verify_completeness(state, int(config['MAX_RECORD_ERRORS']))
    return state, ok


def test_complete_oogst_schrijft_alles_ook_de_laatste_chunk(config, tmp_path, monkeypatch):
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(), chunk=5)
    assert ok
    assert state['written'] == PHOTOS and state['files'] == 3          # 5 + 5 + 4
    assert sorted(p.name for p in tmp_path.glob('photos-*.jsonld')) == [
        'photos-0000.jsonld', 'photos-0001.jsonld', 'photos-0002.jsonld']


def test_minder_records_dan_aangekondigd_laat_de_run_falen(config, tmp_path, monkeypatch):
    _, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(announced=PHOTOS + 1))
    assert not ok


def test_zonder_completelistsize_laat_de_run_falen(config, tmp_path, monkeypatch):
    _, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(announced=None))
    assert not ok


def test_dubbel_geleverd_record_laat_de_run_falen(config, tmp_path, monkeypatch):
    root = ET.parse(FIXTURES / 'photos.xml').getroot()
    dubbel = root.findall('.//o:record', OAI)[0]
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(announced=PHOTOS + 1, extra=[dubbel]))
    assert state['duplicates'] == 1 and not ok


def test_transformatiefout_telt_en_laat_de_run_falen(config, tmp_path, monkeypatch):
    import transform_service

    def kapot(graph, config, header, fields, source):
        raise ValueError('kapot')
    monkeypatch.setattr(transform_service, 'transform_record', kapot)
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream())
    assert state['errors'] == PHOTOS and state['written'] == 0 and not ok


def test_toegestane_fouten_laten_de_run_slagen(config, tmp_path, monkeypatch):
    import transform_service
    echte = transform_service.transform_record
    aantal = {'n': 0}

    def een_fout(graph, config, header, fields, source):
        aantal['n'] += 1
        if aantal['n'] == 1:
            raise ValueError('kapot')
        return echte(graph, config, header, fields, source)
    monkeypatch.setattr(transform_service, 'transform_record', een_fout)
    monkeypatch.setattr(oai_client, 'iter_records', _fixture_stream())
    state = harvest_service.harvest_source(config, 'photos', str(tmp_path) + '/', 5)
    assert state['errors'] == 1 and state['written'] == PHOTOS - 1
    assert not harvest_service.verify_completeness(state, 0)
    assert harvest_service.verify_completeness(state, 1)


def test_beperkte_run_slaat_de_volledigheidscontrole_over(config, tmp_path, monkeypatch):
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(announced=999), max_records=3)
    assert ok and state['written'] == 3


def test_manifest(config, tmp_path, monkeypatch):
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream())
    harvest_service.write_manifest(str(tmp_path) + '/', 'photos', state, ok)
    manifest = json.loads((tmp_path / 'manifest-photos.json').read_text(encoding='utf-8'))
    assert manifest['complete'] is True and manifest['written'] == PHOTOS and manifest['oai_expected'] == PHOTOS


def test_main_zonder_sleutel_stopt_met_een_duidelijke_melding(monkeypatch, tmp_path):
    monkeypatch.delenv('MEMORIX_OAI_KEY')
    monkeypatch.setenv('CACHE_PATH', str(tmp_path))
    with pytest.raises(SystemExit) as stop:
        harvest_service.main(['--source', 'photos', '--max-records', '1'])
    assert 'MEMORIX_OAI_KEY' in str(stop.value)


def test_main_met_onbekende_bron(monkeypatch, tmp_path):
    monkeypatch.setenv('CACHE_PATH', str(tmp_path))
    assert harvest_service.main(['--source', 'bestaat-niet']) == 2


def test_de_sleutel_komt_niet_in_de_log(caplog):
    url = 'https://maior.memorix.nl/api/oai/rce/key/geheim-123/?verb=ListRecords'
    assert 'geheim-123' not in oai_client.redact(url)
    assert 'geheim-123' not in oai_client.redact(ValueError(f'<urlopen error voor {url}>'))
    assert logging  # de redactie wordt in oai_client op de waarschuwingen toegepast


def test_leeg_record_wordt_overgeslagen_en_geteld(config, tmp_path, monkeypatch):
    leeg = ET.fromstring(
        '<record xmlns="http://www.openarchives.org/OAI/2.0/"><header><identifier>t:leeg-1</identifier>'
        '<datestamp>2026-01-01T00:00:00Z</datestamp></header><metadata><dc xmlns:dcterms="http://purl.org/dc/terms/">'
        '<dcterms:references>http://beeldbank.cultureelerfgoed.nl/alle-afbeeldingen/detail/leeg-1/media/</dcterms:references>'
        '<dcterms:spatial/></dc></metadata></record>')
    state, ok = _run(config, tmp_path, monkeypatch, _fixture_stream(announced=PHOTOS + 1, extra=[leeg]))
    assert ok and state['written'] == PHOTOS and state['skipped'] == 1
    assert state['skipped_ids'] == ['t:leeg-1']


def test_alleen_de_fotos_staan_aan_in_de_config(config):
    assert list(config['SOURCES']) == ['photos']
    assert config['SOURCES']['photos']['set'] == 'tenant:rce:search_s_entity_type:photos'
