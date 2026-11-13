# Beheer

## Inrichting (eenmalig)

1. Maak een GitHub-repository met deze inhoud.
2. Zet twee secrets (Settings → Secrets and variables → Actions):
   - `MEMORIX_OAI_KEY`: het deel van de OAI-URL na `/key/` (voor `oai_dc`).
   - `LDV_API_TOKEN`: een token met schrijfrechten op de dataset in de LDV.
3. Controleer in de LDV of de dataset `rce/beeldbank` bestaat, of maak hem aan (open besluit 1 in [besluiten.md](besluiten.md)).
   Wilt u eerst naar een testdataset, zet dan `TRIPLY_DATASET` in de workflow tijdelijk op een andere naam.

## Een run starten

Actions → *RCE Beeldbank ETL* → *Run workflow*. De planning draait elke zondag 01:00 UTC en **publiceert direct**.

Aanpak voor de eerste keren:

| Run | `testmode` | `publish` | Doel |
|---|---|---|---|
| 1 | aan | n.v.t. | oogst 100 records, toets met SHACL; niets wordt gepubliceerd |
| 2 | uit | uit | volledige oogst en SHACL, zonder publicatie; kijk naar de looptijd en de manifesten |
| 3 | uit | aan | volledige run met publicatie, bij voorkeur naar een testdataset |

## De uitkomst lezen

Elke job schrijft zijn manifest in de samenvatting (`manifest-{set}.json`), onder meer:

| Veld | Betekenis |
|---|---|
| `oai_seen` / `oai_expected` | opgehaald / aangekondigd (`completeListSize`); moeten gelijk zijn |
| `written`, `errors`, `skipped` | `written + errors + skipped = oai_seen` |
| `skipped_reasons`, `skipped_ids` | waarom en welke records zijn overgeslagen (records zonder inhoud) |
| `duplicates` | records die twee keer zijn geleverd; moet 0 zijn |
| `complete` | `false` betekent: de run is mislukt en er wordt niet gepubliceerd |

## Lokaal draaien

```bash
export MEMORIX_OAI_KEY=<sleutel>
python src/harvest_service.py --source photos --max-records 1000
python src/validate_service.py data/photos-*.jsonld
```

Zonder `--max-records` oogst dit alle 565.178 foto's. Gemeten op 13 november 2026: een OAI-pagina met 200 records duurt ongeveer
een halve seconde; een volledige oogst van de 15.686 minuutplans (een andere set, inmiddels uitgeschakeld) duurde ongeveer 70 seconden
inclusief transformatie. Voor de foto's is dat een schatting van 45 tot 60 minuten; die is nog niet gemeten.

## Foutmeldingen

| Melding | Oorzaak en oplossing |
|---|---|
| `MEMORIX_OAI_KEY ontbreekt` | het secret is niet gezet, of de omgeving mist de variabele |
| `ONVOLLEDIG: bron kondigt N records aan, M opgehaald` | de bron veranderde tijdens de oogst, of een pagina ontbrak. Opnieuw starten; blijft het gebeuren, kijk dan naar de paginering van de bron |
| `N records zijn dubbel geleverd` | de paginering van de bron loopt over; de run publiceert niets |
| `N records konden niet getransformeerd worden` | zie de waarschuwingen `Fout bij transformatie van …` in de log; de identifiers staan ook in het manifest |
| SHACL-Violation | de log noemt de melding en een voorbeeldnode. Pas de transformatie of, bij een bronfout die gepubliceerd moet worden, de shape aan |
| `noRecordsMatch` | de set bestaat niet of is leeg; de oogst levert dan 0 records en de controle faalt |
| HTTP 429/503 | de client wacht en probeert opnieuw (`SRC_RETRIES`, `SRC_BACKOFF`) |

## Terugdraaien

De foto's staan in de graph `…/rce/beeldbank/graphs/photos`. Een volgende run vervangt die graph. Wilt u ze verwijderen,
verwijder dan die graph in de LDV. Een mislukte run publiceert niets, dus de vorige versie blijft staan.
(Tijdens de publicatie zelf, tussen `overwrite` en de laatste `merge` van een set, is die set tijdelijk onvolledig.)

## Testfixtures vernieuwen

```bash
MEMORIX_OAI_KEY=<sleutel> python tools/maak_fixtures.py
python -m pytest
```

De fixtures zijn echte records uit de OAI; de sleutel staat er niet in.
