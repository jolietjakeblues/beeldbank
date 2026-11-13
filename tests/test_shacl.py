"""SHACL: de echte fixture-records voldoen aan de shapes, en de shapes vangen de bekende fouten af."""
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import transform_service as T
import uris
import validate_service
from conftest import ROOT, build_graph, fixture_records

BRONNEN = ['photos', 'architectural_drawings', 'old_prints_and_drawings', 'minuutplans', 'verzamelplans', 'oat']


@pytest.fixture(scope='module')
def shapes():
    return Graph().parse(ROOT / 'shacl' / 'beeldbank.shacl.ttl', format='turtle')


def _validate(graph, shapes):
    return validate_service.validate_graph(graph, shapes)


@pytest.mark.parametrize('source', BRONNEN)
def test_fixtures_hebben_geen_violations(config, shapes, source):
    result = _validate(build_graph(config, source), shapes)
    assert not result['Violation'], dict(result['Violation'])


def test_kaarten_geven_warnings_voor_wat_de_bron_mist(config, shapes):
    result = _validate(build_graph(config, 'minuutplans'), shapes)
    messages = ' '.join(result['Warning'])
    assert 'schema:license ontbreekt' in messages and 'schema:creator ontbreekt' in messages


def _basis(config):
    graph = uris.get_dataset(config)
    header = {'identifier': 'tenant:aaaaaaaa-0000-0000-0000-000000000001', 'datestamp': '2026-01-01T00:00:00Z'}
    fields = {'dcterms:title': ['Titel'], 'dcterms:identifier': ['1.1'], 'dc:creator': ['Galen, P. (Paul) van'],
              'dcterms:created': ['1985'], 'dc:rights': ['http://creativecommons.org/licenses/by-sa/3.0/'],
              'dcterms:references': ['http://beeldbank.cultureelerfgoed.nl/alle-afbeeldingen/detail/'
                                     'aaaaaaaa-0000-0000-0000-000000000001/media/f1a61dc0-e807-5033-b88e-ef82613d0c90']}
    work = T.transform_record(graph, config, header, fields, config['SOURCES']['photos'])
    return graph, work


def test_basisrecord_is_schoon(config, shapes):
    graph, _ = _basis(config)
    result = _validate(graph, shapes)
    assert not result['Violation'] and not result['Warning']


def test_werk_zonder_naam_is_een_violation(config, shapes):
    graph, work = _basis(config)
    graph.remove((work, SDO.name, None))
    assert any('schema:name ontbreekt' in m for m in _validate(graph, shapes)['Violation'])


def test_url_naar_een_andere_site_is_een_violation(config, shapes):
    graph, work = _basis(config)
    graph.remove((work, SDO.url, None))
    graph.add((work, SDO.url, URIRef('https://example.org/x')))
    assert any('link naar de beeldbank' in m for m in _validate(graph, shapes)['Violation'])


def test_twee_titels_als_naam_is_een_violation(config, shapes):
    graph, work = _basis(config)
    graph.add((work, SDO.name, Literal('Andere titel', lang='nl')))
    assert any('maximaal één waarde' in m for m in _validate(graph, shapes)['Violation'])


def test_vrije_tekst_als_datum_is_een_warning_en_geen_violation(config, shapes):
    graph, work = _basis(config)
    graph.remove((work, SDO.dateCreated, None))
    graph.add((work, SDO.dateCreated, Literal('Reproductie gemaakt in 1989', datatype=XSD.string)))
    result = _validate(graph, shapes)
    assert not result['Violation']
    assert any('vrije tekst' in m for m in result['Warning'])


def test_beeld_buiten_de_beeldserver_is_een_violation(config, shapes):
    graph, work = _basis(config)
    image = next(graph.objects(work, SDO.image))
    graph.remove((image, SDO.contentUrl, None))
    graph.add((image, SDO.contentUrl, URIRef('https://example.org/x.jpg')))
    assert any('beeldserver' in m for m in _validate(graph, shapes)['Violation'])


def test_ongeldige_postcode_is_een_violation(config, shapes):
    graph = build_graph(config, 'photos')
    address = next(graph.subjects(RDF.type, SDO.PostalAddress))
    graph.remove((address, SDO.postalCode, None))
    graph.add((address, SDO.postalCode, Literal('9988RB')))
    assert any('1234 AB' in m for m in _validate(graph, shapes)['Violation'])


def test_alle_fixture_records_worden_gevalideerd(config):
    assert sum(len(fixture_records(s)) for s in BRONNEN) == 14 + 5 * 6
