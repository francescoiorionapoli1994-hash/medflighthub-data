#!/usr/bin/env python3
"""Individua esclusivamente le risorse CSV ufficiali ANAC più recenti."""

import json
import sys
import urllib.parse
import urllib.request

API = "https://dati.anticorruzione.it/opendata/api/3/action/package_show"

DATASET = (
    "cig-aggiornamenti-delta",
    "aggiudicazioni",
    "avvio-contratto",
    "fine-contratto",
)

USER_AGENT = "MedFlightHub/1.0 open-data updater"


def leggi_dataset(nome):
    indirizzo = API + "?" + urllib.parse.urlencode({"id": nome})
    richiesta = urllib.request.Request(
        indirizzo,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )

    with urllib.request.urlopen(richiesta, timeout=60) as risposta:
        contenuto = json.load(risposta)

    if not contenuto.get("success"):
        return []

    risorse = contenuto.get("result", {}).get("resources", [])
    risultati = []

    for risorsa in risorse:
        formato = str(risorsa.get("format", "")).upper()
        url = str(risorsa.get("url", "")).strip()

        if formato == "CSV" and url.startswith("https://"):
            risultati.append(
                (
                    str(risorsa.get("last_modified") or ""),
                    url,
                )
            )

    risultati.sort(reverse=True)
    return [url for _, url in risultati[:12]]


def main():
    fonti = []

    for dataset in DATASET:
        try:
            fonti.extend(leggi_dataset(dataset))
        except Exception as errore:
            print(
                f"Avviso: impossibile leggere {dataset}: {errore}",
                file=sys.stderr,
            )

    for url in dict.fromkeys(fonti):
        print(url)

    if not fonti:
        raise SystemExit("Nessuna risorsa ufficiale ANAC trovata")


if __name__ == "__main__":
    main()
