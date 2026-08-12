#!/usr/bin/env python3
"""Importatore privacy-first per Open Data ANAC/BDNCP.

Accetta CSV o ZIP contenenti CSV ufficiali. Produce esclusivamente
i campi contrattuali autorizzati nella lista OUTPUT_FIELDS.
"""

import argparse
import csv
import io
import json
import pathlib
import re
import urllib.request
import uuid
import zipfile

from datetime import datetime, timezone


AVIATION = re.compile(
    r"\b(aere[oa]|aeromobil\w*|aeronaut\w*|vol[oi]|"
    r"elicotter\w*|aircraft|flight)\b",
    re.I,
)

MEDICAL = re.compile(
    r"\b(organ\w*|trapiant\w*|espiant\w*|equipe|"
    r"équipe|pazient\w*|cellul\w* staminal\w*)\b",
    re.I,
)

OUTPUT_FIELDS = {
    "id",
    "title",
    "contractingAuthority",
    "region",
    "cig",
    "status",
    "transportTypes",
    "publicationDate",
    "offerDeadline",
    "contractStart",
    "contractEnd",
    "amount",
    "winner",
    "sourceName",
    "sourceURL",
    "isEstimatedEndDate",
    "notes",
}

ALIASES = {
    "cig": [
        "cig",
        "codice_cig",
    ],
    "title": [
        "oggetto",
        "oggetto_gara",
        "descrizione",
        "denominazione_lotto",
    ],
    "authority": [
        "denominazione_amministrazione_appaltante",
        "stazione_appaltante",
        "denominazione_sa",
    ],
    "region": [
        "regione",
        "regione_sa",
        "regione_stazione_appaltante",
    ],
    "publication": [
        "data_pubblicazione",
        "data_perfezionamento_cig",
        "data_creazione",
    ],
    "deadline": [
        "data_scadenza_offerte",
        "data_scadenza",
    ],
    "start": [
        "data_inizio",
        "data_inizio_contratto",
    ],
    "end": [
        "data_ultimazione_prevista",
        "data_fine",
        "data_fine_contratto",
    ],
    "amount": [
        "importo_complessivo_gara",
        "importo_aggiudicazione",
        "importo_lotto",
    ],
    "winner": [
        "denominazione_aggiudicatario",
        "ragione_sociale",
        "aggiudicatario",
    ],
}


def value(row, name):
    normalized = {
        str(key).strip().lower(): current
        for key, current in row.items()
    }

    for key in ALIASES[name]:
        current = normalized.get(key)

        if current not in (None, ""):
            return str(current).strip()

    return ""


def date_value(raw):
    if not raw:
        return None

    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
    )

    for date_format in formats:
        try:
            result = datetime.strptime(
                raw[:10],
                date_format,
            ).replace(tzinfo=timezone.utc)

            return result.isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    return None


def classify(text):
    result = []
    lower_text = text.lower()

    if (
        "organ" in lower_text
        or "trapiant" in lower_text
        or "espiant" in lower_text
    ):
        result.append("Organi")

    if "equipe" in lower_text or "équipe" in lower_text:
        result.append("Équipe chirurgiche")

    if "pazient" in lower_text:
        result.append("Pazienti")

    return result or ["Servizio misto"]


def map_row(row):
    title = value(row, "title")

    if not (
        AVIATION.search(title)
        and MEDICAL.search(title)
    ):
        return None

    cig = value(row, "cig")
    deadline = date_value(value(row, "deadline"))
    contract_end = date_value(value(row, "end"))
    winner = value(row, "winner")

    now = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    if contract_end:
        if contract_end >= now:
            status = "Contratto in corso"
        else:
            status = "Scaduta"
    elif winner:
        status = "Aggiudicata"
    elif deadline:
        if deadline >= now:
            status = "Aperta"
        else:
            status = "Scaduta"
    else:
        status = "Da verificare"

    amount_raw = (
        value(row, "amount")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        amount = float(amount_raw) if amount_raw else None
    except ValueError:
        amount = None

    source_url = (
        "https://pubblicitalegale.anticorruzione.it/"
        "bdncp"
    )

    if cig:
        source_url += "?cig=" + cig

    record = {
        "id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "anac:" + cig + ":" + title,
            )
        ),
        "title": title,
        "contractingAuthority": (
            value(row, "authority")
            or "Ente non indicato"
        ),
        "region": (
            value(row, "region")
            or "Italia — Regione non indicata"
        ),
        "cig": cig or "Non disponibile",
        "status": status,
        "transportTypes": classify(title),
        "publicationDate": (
            date_value(value(row, "publication"))
            or "1970-01-01T00:00:00Z"
        ),
        "offerDeadline": deadline,
        "contractStart": date_value(
            value(row, "start")
        ),
        "contractEnd": contract_end,
        "amount": amount,
        "winner": winner or None,
        "sourceName": "ANAC — BDNCP Open Data",
        "sourceURL": source_url,
        "isEstimatedEndDate": False,
        "notes": (
            "Dati pubblici contrattuali ANAC. "
            "Nessun documento, dato sanitario "
            "o dato personale importato."
        ),
    }

    assert set(record) == OUTPUT_FIELDS
    return record


def open_source(source):
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(
            source,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/127.0 Safari/537.36"
                ),
                "Accept": (
                    "application/zip,"
                    "text/csv,"
                    "application/octet-stream,"
                    "*/*"
                ),
                "Accept-Language": (
                    "it-IT,it;q=0.9,en;q=0.8"
                ),
                "Referer": (
                    "https://dati.anticorruzione.it/"
                    "opendata/"
                ),
            },
        )

        response = urllib.request.urlopen(
            request,
            timeout=180,
        )

        return io.BytesIO(response.read())

    return open(source, "rb")


def csv_stream(binary):
    prefix = binary.read(4)
    binary.seek(0)

    if prefix == b"PK\x03\x04":
        archive = zipfile.ZipFile(binary)

        csv_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".csv")
        ]

        if not csv_names:
            raise ValueError(
                "L'archivio ANAC non contiene file CSV"
            )

        return io.TextIOWrapper(
            archive.open(csv_names[0]),
            encoding="utf-8-sig",
            errors="replace",
        )

    return io.TextIOWrapper(
        binary,
        encoding="utf-8-sig",
        errors="replace",
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "sources",
        nargs="+",
    )

    parser.add_argument(
        "--output",
        default="anac_catalog.json",
    )

    args = parser.parse_args()
    records = {}

    for source in args.sources:
        print(
            "Elaborazione sorgente ANAC:",
            source,
        )

        with open_source(source) as binary:
            stream = csv_stream(binary)

            sample = stream.read(8192)
            stream.seek(0)

            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=";,\t|",
            )

            reader = csv.DictReader(
                stream,
                dialect=dialect,
            )

            for row in reader:
                record = map_row(row)

                if record:
                    records[record["cig"]] = record

    payload = {
        "source": "ANAC — BDNCP Open Data",
        "license": (
            "Licenza indicata dalle risorse "
            "ufficiali ANAC"
        ),
        "updatedAt": (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "tenders": list(records.values()),
    }

    output_path = pathlib.Path(args.output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    print(
        f"Creati {len(records)} record "
        f"privacy-safe in {output_path}"
    )


if __name__ == "__main__":
    main()
