"""Transformatie van de Beeldbank van de RCE (Memorix, OAI `oai_dc`) naar schema.org (RDF).

Eén OAI-record wordt één werk (schema:Photograph, VisualArtwork, Map of CreativeWork) met zijn eigen nodes
(maker, onderwerpen, plaats, beeld), zodat elk uitvoerbestand op zichzelf valideerbaar is.

Bron: `oai_dc` met `dc:` en `dcterms:`-elementen. De elementen zijn niet gelabeld; de betekenis volgt uit de
volgorde en de vorm van de waarde. Daarom staan de heuristieken (adres, datum, identifiers) in aparte,
geteste functies. De mapping staat in `docs/mapping.md`.
"""
import datetime
import re
from collections import defaultdict
from typing import Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SDO, XSD

import uris

NS_PREFIX = {
    'http://purl.org/dc/elements/1.1/': 'dc',
    'http://purl.org/dc/terms/': 'dcterms',
}

# kind (config) -> (schema.org-typen, klassenaam in de URI)
KINDS = {
    'photo': ([SDO.Photograph, SDO.CreativeWork], 'photograph'),
    'drawing': ([SDO.VisualArtwork, SDO.CreativeWork], 'visualartwork'),
    'print': ([SDO.VisualArtwork, SDO.CreativeWork], 'visualartwork'),
    'map': ([SDO.Map, SDO.CreativeWork], 'map'),
    'table': ([SDO.CreativeWork], 'creativework'),
}

_UUID = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
_MEDIA_IN_URL = re.compile(rf'/media/({_UUID})')
_UUID_ONLY = re.compile(rf'^{_UUID}$')
_BEELDBANK_URL = re.compile(r'^https?://beeldbank\.cultureelerfgoed\.nl/\S+$')
_MONUMENT = re.compile(r'^Monumentnummer:\s*(\d+)\s*$', re.I)
_POSTCODE = re.compile(r'^\d{4}\s?[A-Z]{2}$')
_HOUSE_NUMBER = re.compile(r'^\d+\s*[A-Za-z]?(?:[-/ ]\s*\d+[A-Za-z]?)?(?:\s*(?:bis|hs|rd|sous))?$', re.I)
_ID_ONLY = re.compile(r'^\d{4,}$')
_PRIREF = re.compile(r'^\d{6,}$')
_RIGHTS_URL = re.compile(r'^https?://\S+$')
_DATE = re.compile(r'^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$')

# Organisatie-achtige namen: de bron maakt geen onderscheid tussen persoon en instelling bij makers.
_ORG_WORDS = re.compile(
    r'\b(ministerie|gemeente|provincie|stichting|vereniging|rijksdienst|rijksinstituut|instituut|museum|bureau|'
    r'commissie|werkgroep|raad|dienst|universiteit|hogeschool|genootschap|kring|bond|archief|bibliotheek|'
    r'waterschap|projectgroep|adviesbureau|uitgeverij|maatschappij|vof|b\.?v\.?|n\.?v\.?|gmbh|ltd|inc|'
    r'department|ministry|institute|society|council|association|foundation|werkgemeenschap|federatie|'
    r'kamer|college|inspectie|staatsbosbeheer|monumentenzorg|projecten|historische|heemkundige|fotografie|'
    r'fotostudio|studio|atelier)\b', re.I)
_ORG_SUFFIX = re.compile(r'(museum|instituut|universiteit|archief|bibliotheek|vereniging|uitgeverij|genootschap|'
                         r'hogeschool|stichting|fotografie|fotostudio)\b', re.I)
# 'Achternaam, Initialen (Voornaam)': een persoon, ook als de achternaam een organisatiewoord is
_PERSON_NAME = re.compile(r"^[^,]{1,40}, [A-ZÀ-Ý][\w.\-' ()]{0,40}$")
_ORG_START = re.compile(r'^(ministerie|gemeente|provincie|stichting|vereniging|rijksdienst|rijksinstituut|instituut|'
                        r'museum|commissie|werkgroep|universiteit|hogeschool|genootschap|waterschap)\b', re.I)


def clean(value: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def record_uuid(identifier: str) -> str:
    """OAI '837866ec-…:bc8f6780-…' -> 'bc8f6780-…' (het deel na de tenant-prefix is het record in de beeldbank)."""
    return identifier.split(':', 1)[1].strip() if ':' in identifier else identifier.strip()


def collect_fields(element) -> dict:
    """Alle `dc:`- en `dcterms:`-elementen van een record als {'dc:subject': [...], ...}.
    Lege elementen (de bron levert er veel) worden weggelaten; de volgorde blijft zoals in de bron."""
    fields = defaultdict(list)
    for child in element:
        if '}' not in child.tag:
            continue
        namespace, local = child.tag[1:].split('}', 1)
        prefix = NS_PREFIX.get(namespace)
        value = clean(child.text)
        if prefix and value:
            fields[f'{prefix}:{local}'].append(value)
    return dict(fields)


def unique(values) -> list:
    return list(dict.fromkeys(values))


# ---------------------------------------------------------------------------
# kleine, geteste ontleders
# ---------------------------------------------------------------------------

def parse_date(value: str) -> Optional[Literal]:
    """'1985-04-12' -> xsd:date, '1985-04' -> xsd:gYearMonth, '1985' -> xsd:gYear; alles anders: None."""
    m = _DATE.match(value or '')
    if not m:
        return None
    year, month, day = m.groups()
    if month is not None and not 1 <= int(month) <= 12:
        return None
    if day is not None:
        # echte kalendercontrole: '2005-04-31' bestaat niet en zou door Triply als ongeldige xsd:date worden afgekeurd
        try:
            datetime.date(int(year), int(month), int(day))
        except (TypeError, ValueError):
            return None
    if day:
        return Literal(f'{year}-{month}-{day}', datatype=XSD.date)
    if month:
        return Literal(f'{year}-{month}', datatype=XSD.gYearMonth)
    return Literal(year, datatype=XSD.gYear)


def is_organization(name: str) -> bool:
    """Benadering: de bron kent geen onderscheid tussen persoon en instelling."""
    if _ORG_START.match(name):
        return True
    if _PERSON_NAME.match(name):
        return False
    return bool(_ORG_WORDS.search(name) or _ORG_SUFFIX.search(name))


def parse_address(values: list) -> Optional[dict]:
    """`dcterms:spatial` van foto's, tekeningen en prenten: straat, huisnummer, plaats, postcode, gevolgd door
    identifiers en een regel 'Adlib priref …'. Geeft {'street', 'number', 'locality', 'postcode'} of None.

    Identifiers (alleen cijfers, vier of meer) en de priref-regel worden eerst verwijderd. Van wat overblijft is de
    laatste waarde de plaats, de eerste de straat en een korte tweede waarde met een cijfer het huisnummer.
    Een enkele waarde is alleen een plaats."""
    postcode, rest = None, []
    for value in values:
        if 'priref' in value.lower() or 'systeemkaart' in value.lower() or _ID_ONLY.match(value):
            continue
        if _POSTCODE.match(value):
            postcode = value.upper().replace(' ', '')
            postcode = f'{postcode[:4]} {postcode[4:]}'
            continue
        rest.append(value)
    if not rest:
        return None
    address = {'street': None, 'number': None, 'locality': rest[-1], 'postcode': postcode}
    if len(rest) >= 2:
        address['street'] = rest[0]
    if len(rest) >= 3 and _HOUSE_NUMBER.match(rest[1]):
        address['number'] = rest[1]
    elif len(rest) >= 3:
        # geen huisnummer: alles voor de plaats hoort bij de straat
        address['street'] = ', '.join(rest[:-1])
    return address


def parse_map_place(values: list) -> Optional[dict]:
    """`dcterms:spatial` van minuutplans, verzamelplans en aanwijzende tafels: plaats, land, kadastrale
    gemeentecode, provincie. Geeft {'place', 'province'} of None."""
    rest = [v for v in values if not v.isdigit() and v.lower() != 'nederland']
    if not rest:
        return None
    return {'place': rest[0], 'province': rest[1] if len(rest) > 1 else None}


def media_uuids(fields: dict) -> list:
    """Uuid's van de beelden: uit de links naar de beeldbank en uit `dcterms:relation` (alleen waarden die een uuid zijn)."""
    found = []
    for url in fields.get('dcterms:references', []):
        found += _MEDIA_IN_URL.findall(url)
    found += [v for v in fields.get('dcterms:relation', []) if _UUID_ONLY.match(v)]
    return unique(v.lower() for v in found)


def beeldbank_url(fields: dict, config: dict, rid: str, media: list) -> Optional[str]:
    """Link naar het record in de beeldbank: die uit de bron (https), anders opgebouwd uit record- en beelduuid."""
    for url in fields.get('dcterms:references', []):
        if _BEELDBANK_URL.match(url) and uris.is_valid_uri(url):
            return re.sub(r'^http://', 'https://', url)
    if media:
        return config['BEELDBANK_URL'].format(record=rid, media=media[0])
    return None


def is_empty(fields: dict) -> bool:
    """Een record zonder titel, nummer, beschrijving, onderwerp of beeld. De bron bevat enkele records die alleen een
    link naar de beeldbank hebben (…/media/ zonder beeld); daar is niets over te zeggen en ze worden niet gepubliceerd."""
    if any(fields.get(k) for k in ('dcterms:title', 'dc:title', 'dcterms:identifier', 'dc:source', 'dc:description',
                                   'dc:subject', 'dc:creator')):
        return False
    return not media_uuids(fields)


def title_of(fields: dict) -> list:
    """Titels, de eerste is de naam. `dcterms:title` gaat voor `dc:title`."""
    return unique(fields.get('dcterms:title', []) + fields.get('dc:title', []))


# ---------------------------------------------------------------------------
# gedeelde bouwstenen
# ---------------------------------------------------------------------------

def _node(config: dict, key: str, kind: str) -> URIRef:
    return uris.get_object_uri(config['BASE_URI'], config['COLLECTION_ID'], key, kind)


def _identifier(graph: Graph, config: dict, work: URIRef, rid: str, property_id: str, value: str):
    node = _node(config, f'{rid}/{property_id}/{value}', 'propertyvalue')
    graph.add((node, RDF.type, SDO.PropertyValue))
    graph.add((node, SDO.propertyID, Literal(property_id)))
    graph.add((node, SDO.value, Literal(value, datatype=XSD.string)))
    graph.add((work, SDO.identifier, node))


def _agent(graph: Graph, config: dict, name: str) -> URIRef:
    """Gedeelde node per naam (persoon of organisatie). Zonder authority-nummer kan een homoniem erbij zitten."""
    if is_organization(name):
        node = _node(config, f'organization/{name}', 'organization')
        graph.add((node, RDF.type, SDO.Organization))
    else:
        node = _node(config, f'person/{name}', 'person')
        graph.add((node, RDF.type, SDO.Person))
    graph.add((node, SDO.name, Literal(name, lang='nl')))
    return node


def _named(graph: Graph, config: dict, work: URIRef, predicate: URIRef, name: str, kind: str, rdf_type: URIRef) -> URIRef:
    """Gedeelde benoemde node (term, collectie): zelfde naam, zelfde adres."""
    node = _node(config, f'{kind}/{name}', kind)
    graph.add((node, RDF.type, rdf_type))
    graph.add((node, SDO.name, Literal(name, lang='nl')))
    graph.add((work, predicate, node))
    return node


def _add_place(graph: Graph, config: dict, work: URIRef, kind: str, spatial: list):
    """Plaats van het afgebeelde object (schema:contentLocation)."""
    if kind in ('map', 'table'):
        parsed = parse_map_place(spatial)
        if not parsed:
            return
        place = _node(config, f"place/{parsed['place']}", 'place')
        graph.add((place, RDF.type, SDO.Place))
        graph.add((place, SDO.name, Literal(parsed['place'], lang='nl')))
        if parsed['province']:
            province = _node(config, f"place/{parsed['province']}", 'place')
            graph.add((province, RDF.type, SDO.AdministrativeArea))
            graph.add((province, SDO.name, Literal(parsed['province'], lang='nl')))
            graph.add((place, SDO.containedInPlace, province))
        graph.add((work, SDO.contentLocation, place))
        return

    parsed = parse_address(spatial)
    if not parsed:
        return
    street_line = ' '.join(p for p in (parsed['street'], parsed['number']) if p)
    name = ', '.join(p for p in (street_line, parsed['locality']) if p)
    key = '|'.join(str(parsed[k] or '') for k in ('street', 'number', 'locality', 'postcode'))
    place = _node(config, f'place/{key}', 'place')
    graph.add((place, RDF.type, SDO.Place))
    graph.add((place, SDO.name, Literal(name, lang='nl')))
    if parsed['street'] or parsed['postcode']:
        address = _node(config, f'address/{key}', 'postaladdress')
        graph.add((address, RDF.type, SDO.PostalAddress))
        if street_line:
            graph.add((address, SDO.streetAddress, Literal(street_line)))
        graph.add((address, SDO.addressLocality, Literal(parsed['locality'])))
        if parsed['postcode']:
            graph.add((address, SDO.postalCode, Literal(parsed['postcode'])))
        graph.add((address, SDO.addressCountry, Literal('NL')))
        graph.add((place, SDO.address, address))
    graph.add((work, SDO.contentLocation, place))


# ---------------------------------------------------------------------------
# het record
# ---------------------------------------------------------------------------

def transform_record(graph: Graph, config: dict, header: dict, fields: dict, source: dict) -> URIRef:
    """Zet één OAI-record om. Gooit een uitzondering bij een record zonder identifier; de aanroeper telt die fout.

    Mapping (zie docs/mapping.md voor de volledige tabel):
      titel (dcterms:title, dc:title)      schema:name; overige titels schema:alternateName
      dc:description                       schema:description
      dcterms:created / dc:date            schema:dateCreated (gYear, gYearMonth of date; anders tekst)
      dc:creator, dc:contributor           schema:creator / schema:contributor (persoon of organisatie, per naam gedeeld)
      dcterms:rightsHolder                 schema:copyrightHolder
      dc:rights                            schema:license (alleen als het een URL is)
      dc:subject                           schema:about -> schema:DefinedTerm (per term gedeeld)
      dcterms:coverage 'Monumentnummer: N' schema:about -> rijksmonument-IRI
      dcterms:isPartOf                     schema:isPartOf -> schema:Collection (alleen waarden langer dan één teken)
      dcterms:spatial                      schema:contentLocation -> schema:Place (+ PostalAddress)
      dcterms:references / dcterms:relation  schema:url (beeldbank) en schema:image -> schema:ImageObject
      dcterms:identifier / dc:source       schema:identifier (inventarisnummer); een getal van 6+ cijfers in references is het priref
    """
    rid = record_uuid(header['identifier'])
    if not rid:
        raise ValueError('record zonder identifier')
    types, class_name = KINDS[source['kind']]
    work = _node(config, rid, class_name)
    for t in types:
        graph.add((work, RDF.type, t))
    graph.add((work, SDO.isPartOf, URIRef(config['DATASET_URI'])))
    graph.add((work, SDO.sdPublisher, URIRef(config['ORG_URI'])))
    if header.get('datestamp'):
        graph.add((work, SDO.sdDatePublished, Literal(header['datestamp'][:10], datatype=XSD.date)))
    _identifier(graph, config, work, rid, 'beeldbank-uuid', rid)

    # identifiers
    inventory = (fields.get('dcterms:identifier') or fields.get('dc:source') or [None])[0]
    if inventory:
        _identifier(graph, config, work, rid, 'inventarisnummer', inventory)
    for priref in unique(v for v in fields.get('dcterms:references', []) if _PRIREF.match(v)):
        _identifier(graph, config, work, rid, 'priref', priref)

    # naam: de titel; een record zonder titel (kaarten) valt terug op het inventarisnummer, want zo wordt het in de beeldbank getoond
    titles = title_of(fields)
    name = titles[0] if titles else inventory
    if name:
        graph.add((work, SDO.name, Literal(name, lang='nl')))
    for other in titles[1:]:
        graph.add((work, SDO.alternateName, Literal(other, lang='nl')))
    for text in unique(fields.get('dc:description', [])):
        if text != name:
            graph.add((work, SDO.description, Literal(text, lang='nl')))

    # datum
    for value in unique(fields.get('dcterms:created', []) + fields.get('dc:date', []))[:1]:
        graph.add((work, SDO.dateCreated, parse_date(value) or Literal(value, datatype=XSD.string)))

    # makers
    for who in unique(fields.get('dc:creator', [])):
        graph.add((work, SDO.creator, _agent(graph, config, who)))
    for who in unique(fields.get('dc:contributor', [])):
        graph.add((work, SDO.contributor, _agent(graph, config, who)))
    for who in unique(fields.get('dcterms:rightsHolder', [])):
        graph.add((work, SDO.copyrightHolder, _agent(graph, config, who)))

    # rechten: alleen een URL (de bron levert er één per record)
    license_url = next((v for v in fields.get('dc:rights', []) if _RIGHTS_URL.match(v) and uris.is_valid_uri(v)), None)
    if license_url:
        graph.add((work, SDO.license, URIRef(license_url)))

    # onderwerpen en monumenten
    for term in unique(fields.get('dc:subject', [])):
        _named(graph, config, work, SDO.about, term, 'term', SDO.DefinedTerm)
    for value in fields.get('dcterms:coverage', []):
        m = _MONUMENT.match(value)
        if m:
            graph.add((work, SDO.about, URIRef(config['MONUMENT_URI'].format(number=m.group(1)))))

    # collectie
    for name_part in unique(fields.get('dcterms:isPartOf', [])):
        if len(name_part) > 1:      # een enkele letter is de sectie van een kadastrale kaart en staat al in het inventarisnummer
            _named(graph, config, work, SDO.isPartOf, name_part, 'collection', SDO.Collection)

    _add_place(graph, config, work, source['kind'], fields.get('dcterms:spatial', []))

    # beeld en link
    media = media_uuids(fields)
    url = beeldbank_url(fields, config, rid, media)
    if url:
        graph.add((work, SDO.url, URIRef(url)))
    for uuid_ in media:
        image = _node(config, f'{rid}/{uuid_}', 'imageobject')
        graph.add((image, RDF.type, SDO.ImageObject))
        graph.add((image, SDO.contentUrl, URIRef(config['IMAGE_URL'].format(media=uuid_))))
        graph.add((image, SDO.thumbnailUrl, URIRef(config['THUMBNAIL_URL'].format(media=uuid_))))
        graph.add((image, SDO.encodingFormat, Literal('image/jpeg')))
        if license_url:
            graph.add((image, SDO.license, URIRef(license_url)))
        graph.add((work, SDO.image, image))
    return work
