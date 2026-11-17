"""
Confronta, sulla stessa risposta di Open-Meteo (ICON-2I), la regola nuova del
nuvoloso (nubi basse e medie >= 90%) con quella vecchia (copertura totale >= 90%,
nubi alte comprese). Uso:  py confronto_nubi.py
"""

import json
import urllib.request
from datetime import datetime, timedelta

LAT, LON, SOGLIA_MM, NUVOLE = 40.86, 14.28, 1, 90
URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT:.2f}&longitude={LON:.2f}"
    "&hourly=precipitation,weather_code,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high"
    "&models=italia_meteo_arpae_icon_2i"
    "&forecast_hours=14&timeformat=unixtime&timezone=GMT"
)


def stato(mm, codice, coperto):
    if codice is not None and codice >= 95:
        return "temporale"
    if mm >= SOGLIA_MM:
        return "pioggia"
    if mm >= 0.1 or (coperto is not None and coperto >= NUVOLE):
        return "nuvoloso"
    return "asciutto"


req = urllib.request.Request(URL, headers={"User-Agent": "Chametiger-test"})
h = json.load(urllib.request.urlopen(req, timeout=20))["hourly"]
print("ora  mm    tot  bas  med  alt  basse+medie  NUOVA      VECCHIA")
for t, mm, c, tot, b, m, a in zip(
    h["time"], h["precipitation"], h["weather_code"], h["cloud_cover"],
    h["cloud_cover_low"], h["cloud_cover_mid"], h["cloud_cover_high"],
):
    if mm is None:
        continue
    ora = (datetime.fromtimestamp(t) - timedelta(hours=1)).strftime("%d %H")
    bm = None if b is None and m is None else 100 - (100 - (b or 0)) * (100 - (m or 0)) / 100
    nuova, vecchia = stato(mm, c, bm), stato(mm, c, tot)
    segno = "  <-- diverse" if nuova != vecchia else ""
    print(f"{ora}  {mm:<4}  {tot!s:>3}  {b!s:>3}  {m!s:>3}  {a!s:>3}  {bm if bm is None else round(bm):>11}  {nuova:<9}  {vecchia}{segno}")
