"""Transformatie: echte records uit de OAI (tests/fixtures) en de ontleders voor datum, adres en identifiers."""
import xml.etree.ElementTree as ET

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import transform_service as T
import uris
from conftest import build_graph, fixture_records

TYPE_PER_BRON = {'photos': SDO.Photograph, 'architectural_drawings': SDO.VisualArtwork,
                 'old_prints_and_drawings': SDO.VisualArtwork, 'minuutplans': SDO.Map,
                 'verzamelplans': SDO.Map, 'oat': SDO.CreativeWork}


# --- ontleders -------------------------------------------------------------

@pytest.mark.parametrize('value,datatype,lexical', [
    ('1985-04-12', XSD.date, '1985-04-12'),
    ('1985-04', XSD.gYearMonth, '1985-04'),
    ('1985', XSD.gYear, '1985'),
])
def test_parse_date(value, datatype, lexical):
    lit = T.parse_date(value)
    assert lit.datatype == datatype and str(lit) == lexical


@pytest.mark.parametrize('value', ['1985-13', '1985-04-32', '9999 - 99 - 9',
                                   'Reproductie gemaakt in 1989 (A. Schollen)', '', 'ca. 1900'])
def test_parse_date_geen_iso(value):
    assert T.parse_date(value) is None


def test_adres_met_straat_nummer_plaats_postcode():
    values = ['Kerkstraat', '16', 'Varik', '4064 EB', '20295511', 'Adlib priref F&D 20295511']
    assert T.parse_address(values) == {'street': 'Kerkstraat', 'number': '16', 'locality': 'Varik',
                                       'postcode': '4064 EB'}


def test_adres_zonder_postcode_met_ids():
    values = ['Laan v. Meerdervoort', '213', "'s-Gravenhage", '8895', '20089146',
              'systeemkaart, Adlib priref F&D 8895, 20089146']
    assert T.parse_address(values) == {'street': 'Laan v. Meerdervoort', 'number': '213',
                                       'locality': "'s-Gravenhage", 'postcode': None}


def test_adres_alleen_plaats():
    assert T.parse_address(['Culemborg']) == {'street': None, 'number': None, 'locality': 'Culemborg',
                                              'postcode': None}


def test_adres_huisnummer_met_letter_en_toevoeging():
    assert T.parse_address(['Binnenhof', '22a', "'s-Gravenhage", '2513 AA'])['number'] == '22a'
    assert T.parse_address(['Hoogstraat', '3-5', 'Delft'])['number'] == '3-5'


def test_adres_zonder_huisnummer_houdt_alles_voor_de_plaats_bij_de_straat():
    parsed = T.parse_address(['Slot Loevestein', 'Poederoijen', 'Zaltbommel'])
    assert parsed['street'] == 'Slot Loevestein, Poederoijen'
    assert parsed['number'] is None and parsed['locality'] == 'Zaltbommel'


def test_adres_postcode_zonder_spatie_wordt_genormaliseerd():
    assert T.parse_address(['Dorpsstraat', '1', 'Ede', '6711AA'])['postcode'] == '6711 AA'


def test_adres_leeg():
    assert T.parse_address([]) is None
    assert T.parse_address(['20295511', 'Adlib priref F&D 20295511']) is None


def test_plaats_van_een_kaart():
    assert T.parse_map_place(['Asten', 'Nederland', '10007', 'Noord-Brabant']) == {
        'place': 'Asten', 'province': 'Noord-Brabant'}
    assert T.parse_map_place(['Asten']) == {'place': 'Asten', 'province': None}
    assert T.parse_map_place([]) is None


def test_organisatie_of_persoon():
    assert not T.is_organization('Galen, P. (Paul) van')
    assert not T.is_organization('Tangel, L.M. (Loek)')
    assert T.is_organization('Rijksdienst voor het Cultureel Erfgoed')
    assert T.is_organization('Gemeente Utrecht')


def test_record_uuid():
    assert T.record_uuid('837866ec-3f22:bc8f6780-2da6') == 'bc8f6780-2da6'
    assert T.record_uuid('bc8f6780') == 'bc8f6780'


def test_collect_fields_laat_lege_elementen_weg():
    el = ET.fromstring('<d xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">'
                       '<dcterms:spatial>Asten</dcterms:spatial><dcterms:spatial/><dcterms:spatial>  </dcterms:spatial>'
                       '<dc:subject> a   b </dc:subject></d>')
    assert T.collect_fields(el) == {'dcterms:spatial': ['Asten'], 'dc:subject': ['a b']}


# --- echte records ---------------------------------------------------------

@pytest.mark.parametrize('source', list(TYPE_PER_BRON))
def test_elk_record_krijgt_type_naam_en_dataset(config, graph_for, source):
    graph = graph_for(source)
    works = list(graph.subjects(RDF.type, SDO.CreativeWork))
    assert len(works) == len(fixture_records(source))
    for work in works:
        assert (work, RDF.type, TYPE_PER_BRON[source]) in graph
        assert (work, SDO.isPartOf, URIRef(config['DATASET_URI'])) in graph
        assert len(list(graph.objects(work, SDO.name))) == 1
        assert list(graph.objects(work, SDO.sdDatePublished))


def test_adressen_zijn_een_place_met_postaladdress(graph_for):
    graph = graph_for('photos')
    addresses = list(graph.subjects(RDF.type, SDO.PostalAddress))
    assert addresses
    for address in addresses:
        assert list(graph.objects(address, SDO.addressLocality))
        for code in graph.objects(address, SDO.postalCode):
            assert len(str(code)) == 7 and str(code)[4] == ' '


def test_foto_heeft_maker_licentie_beeld_en_link(graph_for):
    graph = graph_for('photos')
    work = next(w for w in graph.subjects(RDF.type, SDO.Photograph) if list(graph.objects(w, SDO.creator)))
    assert list(graph.objects(work, SDO.license))[0] == URIRef('http://creativecommons.org/licenses/by-sa/3.0/')
    url = str(list(graph.objects(work, SDO.url))[0])
    assert url.startswith('https://beeldbank.cultureelerfgoed.nl/alle-afbeeldingen/detail/')
    image = list(graph.objects(work, SDO.image))[0]
    content = str(list(graph.objects(image, SDO.contentUrl))[0])
    assert content.startswith('https://images.memorix.nl/rce/thumb/fullsize/')
    assert str(list(graph.objects(image, SDO.thumbnailUrl))[0]).endswith('.jpg')
    assert content.rsplit('/', 1)[1][:-4] in url        # het beeld is dat van de link


def test_monumentnummer_wordt_een_iri(graph_for):
    graph = graph_for('photos')
    prefix = 'https://linkeddata.cultureelerfgoed.nl/cho-kennis/id/rijksmonument/'
    monuments = [o for o in graph.objects(None, SDO.about) if str(o).startswith(prefix)]
    assert monuments
    assert all(str(m)[len(prefix):].isdigit() for m in monuments)
    # het monument zelf wordt niet beschreven: alleen een IRI
    assert all(not list(graph.predicate_objects(m)) for m in monuments)


def test_kaart_zonder_titel_valt_terug_op_het_inventarisnummer(graph_for):
    graph = graph_for('minuutplans')
    for work in graph.subjects(RDF.type, SDO.Map):
        assert str(list(graph.objects(work, SDO.name))[0]).startswith('MIN')
        assert not list(graph.objects(work, SDO.creator))
        assert not list(graph.objects(work, SDO.license))      # de bron levert geen rechtenverklaring: niets verzinnen


def test_kaart_plaats_met_provincie(graph_for):
    graph = graph_for('minuutplans')
    work = next(iter(graph.subjects(RDF.type, SDO.Map)))
    place = next(iter(graph.objects(work, SDO.contentLocation)))
    province = list(graph.objects(place, SDO.containedInPlace))[0]
    assert (province, RDF.type, SDO.AdministrativeArea) in graph


def test_sectieletter_is_geen_collectie(graph_for):
    graph = graph_for('minuutplans')
    names = {str(n) for c in graph.subjects(RDF.type, SDO.Collection) for n in graph.objects(c, SDO.name)}
    assert 'Minuutplans' in names and all(len(n) > 1 for n in names)


def test_makers_worden_per_naam_gedeeld(graph_for):
    graph = graph_for('photos')
    creators = list(graph.objects(None, SDO.creator))
    assert len(set(creators)) < len(creators)       # in de fixture heeft dezelfde fotograaf meerdere foto's


def test_adressen_zijn_stabiel_tussen_runs(config):
    assert set(build_graph(config, 'photos')) == set(build_graph(config, 'photos'))


def test_geen_ongeldige_iris(graph_for):
    for source in TYPE_PER_BRON:
        for _, _, o in graph_for(source):
            if isinstance(o, URIRef):
                assert uris.is_valid_uri(str(o))


def test_vrije_tekst_als_datum_blijft_tekst(config):
    graph = uris.get_dataset(config)
    header = {'identifier': 'tenant:aaaaaaaa-0000-0000-0000-000000000001', 'datestamp': '2026-01-01T00:00:00Z'}
    fields = {'dcterms:title': ['Titel'], 'dcterms:created': ['Reproductie gemaakt in 1989 (A. Schollen)'],
              'dcterms:identifier': ['1.1']}
    work = T.transform_record(graph, config, header, fields, config['SOURCES']['photos'])
    assert (work, SDO.dateCreated, Literal('Reproductie gemaakt in 1989 (A. Schollen)', datatype=XSD.string)) in graph


def test_record_zonder_identifier_geeft_een_fout(config):
    with pytest.raises(ValueError):
        T.transform_record(uris.get_dataset(config), config, {'identifier': ''}, {}, config['SOURCES']['photos'])


def test_beeldbank_url_zonder_link_in_de_bron(config):
    fields = {'dcterms:relation': ['f1a61dc0-e807-5033-b88e-ef82613d0c90']}
    media = T.media_uuids(fields)
    assert T.beeldbank_url(fields, config, 'rid', media) == (
        'https://beeldbank.cultureelerfgoed.nl/alle-afbeeldingen/detail/rid/media/f1a61dc0-e807-5033-b88e-ef82613d0c90')
    assert T.beeldbank_url({}, config, 'rid', []) is None


def test_record_met_alleen_een_lege_link_is_leeg():
    fields = {'dcterms:references': ['http://beeldbank.cultureelerfgoed.nl/alle-afbeeldingen/detail/aaaa/media/']}
    assert T.is_empty(fields)
    assert not T.is_empty({'dcterms:title': ['Titel']})
    assert not T.is_empty({'dcterms:relation': ['f1a61dc0-e807-5033-b88e-ef82613d0c90']})
