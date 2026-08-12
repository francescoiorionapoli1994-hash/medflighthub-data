#!/usr/bin/env python3
"""Trova su dati.gov.it le risorse CSV ufficiali pubblicate da ANAC."""

import json
import sys
import urllib.parse
import urllib.request

API = "https://www.dati.gov.it/opendata/api/3/action/package_search"

RICERCHE = (
    "CIG aggiornamenti delta",
    "aggiudicazioni",
    "avvio-contratto",
    "fine-contratto",
)

USER_AGENT = "MedFlightHub/1.0 open-data updater"


def cerca_dataset(titolo):
    parametri = urllib.parse.urlencode(
        {
            "q": f'"{titolo}"',
            "rows": 20,
        }
    )
    richiesta = urllib.request.Request(
        API + "?" + parametri,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(richiesta, timeout=90) as risposta:
        contenuto = json.load(risposta)

    if not contenuto.get("success"):
        return []

    dataset = contenuto.get("result", {}).get("results", [])
    risorse = []

    for elemento in dataset:
        nome = str(elemento.get("title", "")).casefold()

        if titolo.casefold() not in nome:
            continue

        for risorsa in elemento.get("resources", []):
            formato = str(risorsa.get("format", "")).upper()
            url = str(risorsa.get("url", "")).strip()

            if formato != "CSV" or not url:
                continue

            if url.startswith("http://dati.anticorruzione.it/"):
                url = "https://" + url[len("http://"):]

            if url.startswith("https://"):
                risorse.append(
                    (
                        str(risorsa.get("last_modified") or ""),
                        url,
                    )
                )

    risorse.sort(reverse=True)
    return [url for _, url in risorse[:6]]


def main():
    fonti = []

    for titolo in RICERCHE:
        try:
            trovate = cerca_dataset(titolo)
            fonti.extend(trovate)
            print(
                f"Trovate {len(trovate)} risorse per {titolo}",
                file=sys.stderr,
            )
        except Exception as errore:
            print(
                f"Avviso per {titolo}: {errore}",
                file=sys.stderr,
            )

    fonti = list(dict.fromkeys(fonti))

    if not fonti:
        raise SystemExit(
            "Nessuna risorsa ANAC trovata tramite dati.gov.it"
        )

    for url in fonti:
        print(url)


if __name__ == "__main__":
    main()
