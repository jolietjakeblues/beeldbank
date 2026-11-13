# Mapping: OAI `oai_dc` naar schema.org

Alleen de foto's worden geoogst. De mapping van de andere sets (tekeningen, prenten, kaarten, tafels) staat er ook in; die is getest maar uitgeschakeld.

De bron levert Dublin Core zonder labels. De betekenis van een veld volgt uit de volgorde en de vorm van de waarde; daarom zijn de
heuristieken (adres, datum, identifiers) aparte functies in `src/transform_service.py` met eigen tests. Lege elementen, waarvan de
bron er veel levert, worden weggelaten.

URI's: `https://linkeddata.cultureelerfgoed.nl/rce/beeldbank/id/{klasse}/{uuid3}`. Het uuid3 volgt uit een vaste sleutel (het uuid
van het record, of de naam), dus een tweede run levert dezelfde adressen op.

## Het werk

| Bron | schema.org | Opmerking |
|---|---|---|
| set `photos` | `schema:Photograph` + `schema:CreativeWork` | |
| set `architectural_drawings`, `old_prints_and_drawings` | `schema:VisualArtwork` + `schema:CreativeWork` | |
| set `minuutplans`, `verzamelplans` | `schema:Map` + `schema:CreativeWork` | |
| set `oat` | `schema:CreativeWork` | een aanwijzende tafel is een tabel, geen kaart |
| header `datestamp` | `schema:sdDatePublished` (`xsd:date`) | wijzigingsdatum in de bron, verplicht in het CN-profiel |
| header `identifier` (deel na `:`) | URI van het werk en `schema:identifier` (`beeldbank-uuid`) | het uuid van het record in de beeldbank |
| `dcterms:title`, anders `dc:title` | `schema:name` (eerste); overige titels `schema:alternateName` | |
| geen titel | `schema:name` = inventarisnummer | kaarten hebben geen titel; zo toont de beeldbank ze ook |
| `dc:description` | `schema:description` | niet als die gelijk is aan de naam |
| `dcterms:created`, anders `dc:date` | `schema:dateCreated` | `1985` → `xsd:gYear`, `1985-04` → `xsd:gYearMonth`, `1985-04-12` → `xsd:date`; vrije tekst blijft tekst en geeft een Warning |
| `dcterms:identifier`, anders `dc:source` | `schema:identifier` → `PropertyValue` `inventarisnummer` | |
| getal van 6+ cijfers in `dcterms:references` | `schema:identifier` → `PropertyValue` `priref` | het Adlib-priref van Foto & Documentatie |
| `dcterms:references` (beeldbank-link) | `schema:url` | `http` wordt `https`; zonder link opgebouwd uit record- en beelduuid |
| `dc:rights` (een URL) | `schema:license` | niet-URL's worden niet gepubliceerd; geen waarde = geen licentie, er wordt niets verzonnen |

## Makers en rechten

| Bron | schema.org |
|---|---|
| `dc:creator` | `schema:creator` → `schema:Person` of `schema:Organization` |
| `dc:contributor` | `schema:contributor` (idem) |
| `dcterms:rightsHolder` | `schema:copyrightHolder` (idem) |

Persoon of organisatie wordt geraden uit de naam ("Achternaam, Initialen (Voornaam)" is een persoon; woorden als "Gemeente" of
"Fotografie" wijzen op een organisatie). Zonder authority-nummer deelt dezelfde naam dezelfde node; een homoniem wordt dus
samengevoegd. De rol van de maker ("Fotograaf") staat alleen in het `ese`-formaat en komt hier niet voor.

## Onderwerp, collectie, monument

| Bron | schema.org |
|---|---|
| `dc:subject` | `schema:about` → `schema:DefinedTerm` met `schema:name`, per term gedeeld. Alleen tekst, geen thesaurus-URI |
| `dcterms:coverage` `Monumentnummer: N` | `schema:about` → `https://linkeddata.cultureelerfgoed.nl/cho-kennis/id/rijksmonument/N`, alleen de IRI |
| `dcterms:isPartOf` | `schema:isPartOf` → `schema:Collection` met naam. Waarden van één teken vallen af: dat is de sectieletter van een kadastrale kaart en staat al in het inventarisnummer |

## Plaats

`dcterms:spatial` is een rij zonder labels. Voor foto's, tekeningen en prenten is dat straat, huisnummer, plaats, postcode, gevolgd door
identifiers en een regel "Adlib priref …". Eerst vallen identifiers (alleen cijfers, vier of meer) en de priref-regel weg, en de postcode
wordt herkend aan zijn vorm. Van de rest is de laatste waarde de plaats, de eerste de straat, en een korte tweede waarde die op een
huisnummer lijkt het huisnummer. Zonder huisnummer hoort alles vóór de plaats bij de straat.

| Resultaat | schema.org |
|---|---|
| plaats | `schema:contentLocation` → `schema:Place` met `schema:name` ("Kerkstraat 16, Varik") |
| straat of postcode aanwezig | `schema:address` → `schema:PostalAddress` met `streetAddress`, `addressLocality`, `postalCode` (`1234 AB`), `addressCountry` `NL` |

Voor kaarten (`minuutplans`, `verzamelplans`) en tafels (`oat`) is de rij: plaats, "Nederland", kadastrale gemeentecode, provincie.
Het werk krijgt `schema:contentLocation` → `Place` (de plaats) met `schema:containedInPlace` → `AdministrativeArea` (de provincie).
De gemeentecode wordt niet gepubliceerd.

## Beeld

Het uuid van het beeld staat in de beeldbank-link (`…/media/{uuid}`) en in `dcterms:relation`.

| schema.org | Waarde |
|---|---|
| `schema:image` → `schema:ImageObject` | |
| `schema:contentUrl` | `https://images.memorix.nl/rce/thumb/fullsize/{uuid}.jpg` |
| `schema:thumbnailUrl` | `https://images.memorix.nl/rce/thumb/350x350/{uuid}.jpg` |
| `schema:encodingFormat` | `image/jpeg` |
| `schema:license` | die van het werk |

Beide URL-patronen zijn op 13 november 2026 voor één record gecontroleerd (HTTP 200, `image/jpeg`). Het patroon staat in
`config/config.yml`, zodat het zonder codewijziging aan te passen is.

## Wat niet wordt gepubliceerd

- `dc:identifier` en `dcterms:relation` voor zover het interne nummers zijn (systeemkaartnummers, "Adlib priref …"-regels);
- `dcterms:coverage` dat geen monumentnummer is (een enkel record heeft "Monumentnummer: Gereformeerde Kerk");
- de gemeentecode van kaarten;
- records zonder enige inhoud (zie README).

## Opmerkingen over de bron

- De sectieletter en andere velden die al in het inventarisnummer zitten, worden niet apart gepubliceerd.
- De zes sets melden samen 36.826 records minder dan `tenant:rce` als geheel; zie [besluiten.md](besluiten.md), punt 2.
