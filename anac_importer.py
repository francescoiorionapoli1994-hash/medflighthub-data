#!/usr/bin/env python3
"""Importatore privacy-first per Open Data ANAC/BDNCP.

Accetta CSV o ZIP di CSV ufficiali. Produce esclusivamente i campi nella
allowlist OUTPUT_FIELDS: ogni altra colonna della sorgente viene ignorata.
"""
import argparse, csv, io, json, pathlib, re, urllib.request, uuid, zipfile
from datetime import datetime, timezone

AVIATION = re.compile(r"\b(aere[oa]|aeromobil\w*|aeronaut\w*|vol[oi]|elicotter\w*|aircraft|flight)\b", re.I)
MEDICAL = re.compile(r"\b(organ\w*|trapiant\w*|espiant\w*|equipe|équipe|pazient\w*|cellul\w* staminal\w*)\b", re.I)
OUTPUT_FIELDS = {
    "id", "title", "contractingAuthority", "region", "cig", "status",
    "transportTypes", "publicationDate", "offerDeadline", "contractStart",
    "contractEnd", "amount", "winner", "sourceName", "sourceURL",
    "isEstimatedEndDate", "notes"
}

ALIASES = {
    "cig": ["cig", "codice_cig"],
    "title": ["oggetto", "oggetto_gara", "descrizione", "denominazione_lotto"],
    "authority": ["denominazione_amministrazione_appaltante", "stazione_appaltante", "denominazione_sa"],
    "region": ["regione", "regione_sa", "regione_stazione_appaltante"],
    "publication": ["data_pubblicazione", "data_perfezionamento_cig", "data_creazione"],
    "deadline": ["data_scadenza_offerte", "data_scadenza"],
    "start": ["data_inizio", "data_inizio_contratto"],
    "end": ["data_ultimazione_prevista", "data_fine", "data_fine_contratto"],
    "amount": ["importo_complessivo_gara", "importo_aggiudicazione", "importo_lotto"],
    "winner": ["denominazione_aggiudicatario", "ragione_sociale", "aggiudicatario"],
}

def value(row, name):
    normalized = {str(k).strip().lower(): v for k, v in row.items()}
    for key in ALIASES[name]:
        current = normalized.get(key)
        if current not in (None, ""):
            return str(current).strip()
    return ""

def date_value(raw):
    if not raw: return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try: return datetime.strptime(raw[:10], fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError: pass
    return None

def classify(text):
    out=[]; low=text.lower()
    if "organ" in low or "trapiant" in low or "espiant" in low: out.append("Organi")
    if "equipe" in low or "équipe" in low: out.append("Équipe chirurgiche")
    if "pazient" in low: out.append("Pazienti")
    return out or ["Servizio misto"]

def map_row(row):
    title=value(row,"title")
    if not (AVIATION.search(title) and MEDICAL.search(title)): return None
    cig=value(row,"cig")
    deadline=date_value(value(row,"deadline")); end=date_value(value(row,"end")); winner=value(row,"winner")
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    if end: status="Contratto in corso" if end >= now else "Scaduta"
    elif winner: status="Aggiudicata"
    elif deadline: status="Aperta" if deadline >= now else "Scaduta"
    else: status="Scaduta"
    amount_raw=value(row,"amount").replace(".","").replace(",",".")
    try: amount=float(amount_raw) if amount_raw else None
    except ValueError: amount=None
    record={
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "anac:"+cig+":"+title)), "title": title,
        "contractingAuthority": value(row,"authority") or "Ente non indicato", "region": value(row,"region") or "Italia — Regione non indicata",
        "cig": cig or "Non disponibile", "status": status, "transportTypes": classify(title),
        "publicationDate": date_value(value(row,"publication")) or "1970-01-01T00:00:00Z",
        "offerDeadline": deadline, "contractStart": date_value(value(row,"start")), "contractEnd": end,
        "amount": amount, "winner": winner or None, "sourceName": "ANAC — BDNCP Open Data",
        "sourceURL": "https://pubblicitalegale.anticorruzione.it/bdncp?cig="+cig if cig else "https://pubblicitalegale.anticorruzione.it/bdncp",
        "isEstimatedEndDate": False, "notes": "Dati pubblici contrattuali ANAC. Nessun documento o dato personale importato."
    }
    assert set(record) == OUTPUT_FIELDS
    return record

def open_source(source):
    if source.startswith(("https://", "http://")):
        request=urllib.request.Request(source, headers={"User-Agent":"MedFlightHub/1.0 open-data importer"})
        return io.BytesIO(urllib.request.urlopen(request, timeout=120).read())
    return open(source,"rb")

def csv_stream(binary):
    prefix=binary.read(4); binary.seek(0)
    if prefix == b"PK\x03\x04":
        archive=zipfile.ZipFile(binary)
        name=next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        return io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", errors="replace")
    return io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+")
    parser.add_argument("--output", default="backend/data/anac_catalog.json")
    args=parser.parse_args(); records={}
    for source in args.sources:
        with open_source(source) as binary:
            stream=csv_stream(binary); sample=stream.read(8192); stream.seek(0)
            dialect=csv.Sniffer().sniff(sample, delimiters=";,\t|")
            for row in csv.DictReader(stream, dialect=dialect):
                record=map_row(row)
                if record: records[record["cig"]]=record
    payload={"source":"ANAC — BDNCP Open Data","license":"Verificare la licenza indicata dalla singola risorsa ANAC","updatedAt":datetime.now(timezone.utc).isoformat(),"tenders":list(records.values())}
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"Creati {len(records)} record privacy-safe in {out}")
if __name__ == "__main__": main()
