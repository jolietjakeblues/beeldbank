# Besluiten en open punten

Twee lijsten: wat nog besloten of uitgezocht moet worden, en welke keuzes zijn gemaakt en waarom.

## Open besluiten en vragen

| # | Onderwerp | Wat is er aan de hand | Bij wie | Gevolg tot dan |
|---|---|---|---|---|
| 1 | **Dataset in de LDV** | De workflow publiceert naar `rce/beeldbank` (account `rce`, dataset `beeldbank`). Bestaat die dataset al, of moet hij worden aangemaakt? Een eerste run naar een aparte testdataset is veiliger. | beheerder van de LDV | `publish` uit bij de eerste runs ([beheer.md](beheer.md)) |
| 2 | **Verschil tussen tenant en sets** | `tenant:rce` meldt 813.356 records, de zes sets samen 776.530 (verschil 36.826). Elke set meldt wel precies zijn eigen aantal: de volledige oogst van `verzamelplans`, `old_prints_and_drawings` en `minuutplans` kwam uit op het aangekondigde aantal. In een steekproef van 2.800 records uit `tenant:rce` had elk record precies één entity-type-set. De oorzaak is onbekend. Raakt de foto's alleen als het ontbrekende deel foto's zijn. | Memorix (`memorix.contact@vitecsoftware.com`) of de beheerder van de beeldbank | alleen de set `photos` wordt geoogst, met de eigen telling van die set als controle |
| 3 | **Twee OAI-sleutels** | De sleutel voor `ese` geeft 23.533 records, die voor `oai_dc` 813.356. Er is gekozen voor `oai_dc` (de sleutel die de beheerder noemde). De `ese`-sleutel is waarschijnlijk een selectie met beeld, maar dat is niet nagegaan. | beheerder | `ese` wordt niet gebruikt |
| 4 | **Licentie van de metadata** | `LICENSE_URI` is leeg. Het beeld heeft per record een licentie (CC BY-SA 3.0 of 4.0); de metadata als geheel nog niet. | RCE | geen licentie op datasetniveau |
| 5 | **Records zonder licentie** | Bij kaarten (minuutplans, verzamelplans, tafels) en bij ongeveer één op de zes foto's in een steekproef levert de bron geen `dc:rights`. Er wordt niets verzonnen; ze krijgen een Warning. Is hun status bekend (bijvoorbeeld publiek domein)? | RCE, beeldbank | geen `schema:license` bij die records |
| 6 | **Monument-IRI** | `Monumentnummer: N` wordt `…/cho-kennis/id/rijksmonument/N`. Dat patroon komt uit andere RCE-projecten; het is niet gecontroleerd tegen de kennisgraaf. Is `Monumentnummer` altijd een rijksmonumentnummer? | RCE | gepubliceerd als alleen een IRI |
| 7 | **Beeld-URL's** | `fullsize` en `350x350` zijn voor één record gecontroleerd. Dat de beeldserver die patronen voor alle sets en alle records aanbiedt, is niet nagegaan. | beheerder | patronen staan in `config/config.yml` |
| 8 | **Grootte** | Een steekproef geeft ongeveer 4,7 kB JSON-LD per foto: de foto's alleen al zijn dan circa 2,6 GB. De Triply-import ervan (80 bestanden van 7.000 records) is niet getest. | beheerder van de pijplijn | eerste volledige run handmatig, let op de looptijd van `publish` |
| 9 | **NDE Datasetregister** | De dataset moet nog met een beschrijving worden aangemeld, zoals de andere RCE-datasets. Los van deze pijplijn. | RCE | n.v.t. |
| 10 | **Eerste volledige run** | Nog niet gedraaid. Looptijd van de foto's, de Triply-import en het gedrag van `--mode overwrite` bij een tweede run zijn nog niet gezien. | beheerder van de pijplijn | zie [beheer.md](beheer.md) |

## Mogelijke vervolgstappen

- **Het verschil uit punt 2 uitzoeken** met `ListIdentifiers` op `tenant:rce` en de zes sets, en de identifiers vergelijken.
- **Makers en onderwerpen als authority-URI's.** De OAI levert alleen tekst. De REST-API van de mediabank (`webservices.memorix.nl`) heeft rijkere
  velden (objectnaam, techniek, afbeeldingsmaten, geodata, `iprestricted`), maar die toont in een steekproef vooral andere tenants (Westfries
  Museum) en het koppelen aan de OAI-records (record-uuid) is niet getest.
- **Trefwoorden koppelen aan de CHT** via het Termennetwerk, zodat `schema:about` naar een thesaurus-URI verwijst.
- **Adressen koppelen aan de BAG** op postcode en huisnummer.
- **Andere sets aanzetten** (zie `config/config.yml`): de code, de shapes en de tests ondersteunen ze al.
- **Foto's opsplitsen** over meerdere jobs als de looptijd tegenvalt (OAI-selectie met `from`/`until`).

## Genomen besluiten

| Besluit | Waarom |
|---|---|
| **Alleen de foto's (set `photos`)** | opdracht van de beheerder: dit is de enige oogst die nodig is. De andere sets staan uitgeschakeld in de config; code, shapes en tests ondersteunen ze nog. |
| **Alleen OAI `oai_dc`, geen REST-API** | de OAI is het kanaal dat de beheerder noemde, geeft alle zes sets met `completeListSize` voor de volledigheidscontrole, en heeft per record een stabiele identifier. |
| **Alleen `tenant:rce`** | de sets van `gla` en `wfm` leveren geen records. |
| **Elke run oogst alles** | de OAI meldt geen verwijderde records (`deletedRecord = no`): een deltaoogst zou verwijderingen missen. |
| **Een graph per set** | zo kan een set later worden toegevoegd of opnieuw worden gepubliceerd zonder de andere aan te raken. |
| **Code onder GPL-3.0** | dezelfde licentie als de bibliotheek- en kunst-ETL. Geldt voor de code, niet voor de data. |
| **Kaarten zonder titel krijgen het inventarisnummer als naam** | zo toont de beeldbank ze ook; `schema:name` is verplicht. Er wordt geen titel samengesteld. |
| **Geen licentie als de bron er geen geeft** | niets verzinnen; een Warning maakt het zichtbaar. |
| **Records zonder inhoud overslaan** | enkele records hebben alleen een link zonder beeld (5 van 5.234 bij de prenten). Ze worden geteld en met hun identifier in het manifest gezet; de controle faalt er niet op. |
| **`dcterms:isPartOf` met één teken niet publiceren** | dat is de sectieletter van een kadastrale kaart en staat al in het inventarisnummer. |
| **Gemeentecode van kaarten niet publiceren** | de betekenis (kadastraal of historisch) is niet vastgesteld. |
| **Monument alleen als IRI** | de beschrijving staat in de kennisgraaf; zo ontstaan er geen tweede, afwijkende gegevens. |
| **Adres uit `dcterms:spatial` met heuristiek** | de bron heeft geen labels. De ontleder is getest op echte records; wat niet past valt terug op alleen een plaats. |
| **Vrije-tekst-datums blijven tekst, met Warning** | het is bron-informatie ("Reproductie gemaakt in 1989"); weglaten zou die kwijtraken, een Violation zou de run blokkeren. |
| **Persoon of organisatie uit de naam** | de bron maakt geen onderscheid. Een fout daarin is onschuldig; de node is dan wel van het andere type. |
| **Een run faalt liever dan dat hij stilzwijgend onvolledig is** | tellers worden tegen de bron gecontroleerd; een deel publiceren is erger dan niets. |
| **Records die falen laten geen halve triples achter** | een record wordt eerst apart opgebouwd. |
| **Warnings blokkeren niet, Violations wel** | bekende hiaten in de bron mogen publicatie niet tegenhouden. |
| **De API-sleutel alleen uit de omgeving** | hij staat niet in `config.yml`, niet in de log (`oai_client.redact`) en niet in de fixtures. |
