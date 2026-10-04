"""Bygger veckans Branschkompass-underlag.

Hämtar två års dagliga stängningskurser via yfinance, räknar om allt till SEK,
beräknar relativ styrka och trendläge, och skriver data/latest.json plus en
daterad kopia i data/history/.

Körs av .github/workflows/veckokorning.yml. Kan köras lokalt med:
    pip install -r requirements.txt && python build.py
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

from makro import hamta_makro
from universe import (
    BASKETS, BENCHMARK, BENCHMARK_PER_GRUPP, BENCHMARK_PER_VALUTA, CYKLISKA,
    DEFENSIVA, FX_USDSEK, JAMFORELSEINDEX, SINGLES, US_SEKTORER,
)

LOOKBACK = "2y"
SPARK_DAGAR = 126          # ett halvårs dagliga punkter till sparklinen
MIN_ANDEL = 0.92           # en konstituent behöver nästan hela fönstret...
MIN_DAGAR_GOLV = 200       # ...men aldrig färre dagar än så här
FONSTER = {"r1w": 5, "r1m": 21, "r3m": 63, "r6m": 126, "r12m": 252}
MA_FONSTER = [20, 50, 100, 150, 200]
# Långsiktig profil: tyngdpunkten ligger på halvår och år, inte på senaste månaden.
# Det gör rangordningen trögare och minskar frestelsen att flytta kapital varje vecka.
VIKTER = {"r1m": 0.10, "r3m": 0.25, "r6m": 0.35, "r12m": 0.30}

varningar: list[str] = []


# ---------------------------------------------------------------- hämtning

def hamta(tickers: list[str]) -> pd.DataFrame:
    """Dagliga justerade stängningskurser som DataFrame, en kolumn per ticker."""
    raw = yf.download(
        tickers, period=LOOKBACK, interval="1d",
        auto_adjust=True, progress=False, group_by="column", threads=True,
    )
    if raw is None or raw.empty:
        raise SystemExit("yfinance gav ingen data alls — avbryter utan att skriva något.")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    return close.sort_index()


def alla_tickers() -> list[str]:
    ts = {t for _, _, t, _ in SINGLES.values()}
    for _, _, lista, _ in BASKETS.values():
        ts.update(lista)
    ts.add(FX_USDSEK)
    return sorted(ts)


# ------------------------------------------------------------ serieuppbygg

def korg(df: pd.DataFrame, tickers: list[str], namn: str) -> pd.Series | None:
    """Likaviktat index: varje bolag normaliserat till 100 vid första gemensamma dagen.

    Kravet på datatäckning är en ANDEL av fönstret, inte ett absolut antal
    dagar. En rekonstruktion klipper bort slutet av serien, och med ett fast
    tak föll korgarna då ur listan trots att deras data var lika komplett."""
    krav = max(MIN_DAGAR_GOLV, int(len(df) * MIN_ANDEL))
    finns = [t for t in tickers if t in df.columns and df[t].notna().sum() >= krav]
    saknas = [t for t in tickers if t not in finns]
    if saknas:
        varningar.append(f"{namn}: ingen användbar data för {', '.join(saknas)}")
    if len(finns) < 2:
        varningar.append(f"{namn}: för få bolag med data ({len(finns)}) — korgen utelämnas")
        return None
    bit = df[finns].dropna()
    if bit.empty:
        varningar.append(f"{namn}: inga gemensamma handelsdagar — korgen utelämnas")
        return None
    return (bit / bit.iloc[0] * 100).mean(axis=1)


def bygg_serier(asof: str | None = None) -> dict[str, dict]:
    df = hamta(alla_tickers())
    if asof:                       # bara stängningar FORE den morgonen
        df = df[df.index < pd.Timestamp(asof)]
    if FX_USDSEK in df.columns:
        df[FX_USDSEK] = df[FX_USDSEK].ffill()

    ut: dict[str, dict] = {}
    for nyckel, (namn, grupp, ticker, valuta) in SINGLES.items():
        if ticker not in df.columns or df[ticker].notna().sum() < 200:
            varningar.append(f"{namn} ({ticker}): för lite data — utelämnas")
            continue
        s = df[ticker].dropna()
        ut[nyckel] = {"namn": namn, "grupp": grupp, "serie": s,
                      "innehall": [ticker], "valutakod": valuta}

    for nyckel, (namn, grupp, tickers, valuta) in BASKETS.items():
        s = korg(df, tickers, namn)
        if s is None or len(s) < 200:
            continue
        ut[nyckel] = {"namn": namn, "grupp": grupp, "serie": s, "valutakod": valuta,
                      "innehall": [t for t in tickers if t in df.columns]}
    return ut


# ------------------------------------------------------------- beräkningar

def avkastning(s: pd.Series, n: int) -> float | None:
    if len(s) <= n:
        return None
    return round((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2)


def glidande(s: pd.Series, n: int) -> float | None:
    if len(s) < n:
        return None
    return float(s.iloc[-n:].mean())


def mot(px: float, ma: float | None) -> float | None:
    return None if ma is None else round((px / ma - 1) * 100, 2)


def percentilrang(varden: list[float], v: float) -> float:
    under = sum(1 for x in varden if x < v)
    return under / (len(varden) - 1) * 100 if len(varden) > 1 else 50.0


def berakna(serier: dict[str, dict], kalendrar: dict[str, list[str]]) -> list[dict]:
    rader = []
    for nyckel, post in serier.items():
        s = post["serie"]
        px = float(s.iloc[-1])
        r = {"ticker": nyckel, "namn": post["namn"], "grupp": post["grupp"],
             "innehall": post["innehall"], "valutakod": post["valutakod"],
             "pris": round(px, 2)}
        for fält, n in FONSTER.items():
            r[fält] = avkastning(s, n)
        for n in MA_FONSTER:
            ma = glidande(s, n)
            r[f"ma{n}"] = None if ma is None else round(ma, 2)
            r[f"px_ma{n}"] = mot(px, ma)
        # lutning på MA150 senaste månaden
        if len(s) >= 171:
            ma_nu, ma_da = glidande(s, 150), float(s.iloc[-171:-21].mean())
            r["ma150_lutning"] = round((ma_nu / ma_da - 1) * 100, 2)
        else:
            r["ma150_lutning"] = None
        fonster52 = s.iloc[-252:] if len(s) >= 252 else s
        lo, hi = float(fonster52.min()), float(fonster52.max())
        r["lo52"], r["hi52"] = round(lo, 2), round(hi, 2)
        r["lage52"] = round((px - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0
        fonster = s.iloc[-SPARK_DAGAR:]
        r["serie"] = [round(float(v), 2) for v in fonster]
        # Vilken handelskalender serien följer. Sparas en gång per kalender i
        # utdatan så att dashboarden kan räkna avkastning från ett givet datum
        # utan att gissa vilka dagar som var handelsdagar.
        r["kalender"] = "|".join(d.strftime("%Y%m%d") for d in fonster.index[:1]) + \
                        f"-{len(fonster)}-" + fonster.index[-1].strftime("%Y%m%d")
        kalendrar.setdefault(r["kalender"], [d.strftime("%Y-%m-%d") for d in fonster.index])
        rader.append(r)

    index = {r["ticker"]: r for r in rader}
    if BENCHMARK not in index:
        raise SystemExit(f"Jämförelseindex {BENCHMARK} saknas — avbryter utan att skriva något.")
    for r in rader:
        # jämför mot ett index i samma valuta, så relativ styrka blir valutafri
        bnyckel = (BENCHMARK_PER_GRUPP.get(r["grupp"])
                   or BENCHMARK_PER_VALUTA.get(r.get("valutakod"), BENCHMARK))
        bench = index.get(bnyckel) or index[BENCHMARK]
        r["jamfors_mot"] = bench["namn"]
        for horisont in ("r1m", "r3m", "r6m"):
            a, b = r.get(horisont), bench.get(horisont)
            r["rs" + horisont[1:]] = None if a is None or b is None else round(a - b, 2)

    # Trend: MA50 mot MA150 är primärfiltret (MA150 ≈ Weinsteins 30-veckorssnitt)
    for r in rader:
        over50, over150 = (r["px_ma50"] or 0) > 0, (r["px_ma150"] or 0) > 0
        lutning = r["ma150_lutning"]
        stigande = lutning is not None and lutning > 0
        if over50 and over150 and stigande:
            r["trend"], r["trendscore"] = "Stark upptrend", 2
        elif over150:
            r["trend"], r["trendscore"] = "Upptrend", 1
        elif over50:
            r["trend"], r["trendscore"] = "Vänder upp", 0
        elif not over50 and not over150 and not stigande:
            r["trend"], r["trendscore"] = "Stark nedtrend", -2
        else:
            r["trend"], r["trendscore"] = "Nedtrend", -1

    # Valutaraden är kontext, inte ett innehav: den rankas inte och påverkar
    # inte heller de andras percentiler.
    kontext = [r for r in rader if r["grupp"] == "Valuta"]
    rader = [r for r in rader if r["grupp"] != "Valuta"]

    # Styrka: percentilrang över hela listan, tyngdpunkt på 3 och 6 månader
    for fält, vikt in VIKTER.items():
        varden = [r[fält] for r in rader if r.get(fält) is not None]
        for r in rader:
            r.setdefault("_poang", 0.0)
            r["_poang"] += percentilrang(varden, r[fält]) * vikt if r.get(fält) is not None else 50.0 * vikt
    for r in rader:
        r["styrka"] = round(r.pop("_poang"), 1)

    rader.sort(key=lambda r: -r["styrka"])
    n = len(rader)
    for i, r in enumerate(rader):
        r["rank"] = i + 1
        topp, botten = r["rank"] <= n / 3, r["rank"] > 2 * n / 3
        ts = r["trendscore"]
        if topp and ts >= 1:
            r["signal"], r["signalkod"] = "ÖVERVIKT", 2
        elif botten and ts <= -1:
            r["signal"], r["signalkod"] = "UNDERVIKT", -2
        elif topp and ts <= -1:
            r["signal"], r["signalkod"] = "BEVAKA – styrka men bruten trend", 0
        elif botten and ts >= 1:
            r["signal"], r["signalkod"] = "BEVAKA – svag men vänder", 0
        elif ts >= 1:
            r["signal"], r["signalkod"] = "BEHÅLL", 1
        elif ts <= -1:
            r["signal"], r["signalkod"] = "MINSKA", -1
        else:
            r["signal"], r["signalkod"] = "NEUTRAL", 0

        x, y = r.get("rs3m"), r.get("rs1m")
        if r["ticker"] in JAMFORELSEINDEX:
            r["kvadrant"] = "Jämförelseindex"
        elif x is None or y is None:
            r["kvadrant"] = "Okänd"
        elif x >= 0 and y >= 0:
            r["kvadrant"] = "Ledande"
        elif x >= 0:
            r["kvadrant"] = "Försvagas"
        elif y < 0:
            r["kvadrant"] = "Eftersläpande"
        else:
            r["kvadrant"] = "Förbättras"

    for r in kontext:
        r["rank"] = None
        r["styrka"] = None
        r["signal"], r["signalkod"] = "KONTEXT", 0
        r["kvadrant"] = "Kontext"
    return rader + kontext


# ------------------------------------------------------------------ utdata

def main(asof: str | None = None) -> None:
    varningar.clear()
    serier = bygg_serier(asof)
    kalendrar: dict[str, list[str]] = {}
    rader = berakna(serier, kalendrar)
    # Färskheten styrs av jämförelseindexet, inte av den serie som råkar sträcka sig längst
    sista = serier[BENCHMARK]["serie"].index[-1]
    efterslapande = sorted(
        nyckel for nyckel, post in serier.items() if post["serie"].index[-1] < sista
    )
    if efterslapande:
        varningar.append("Senare kursdag saknas för: " + ", ".join(efterslapande))
    sektorer = [r for r in rader if r["ticker"] in US_SEKTORER]

    ut = {
        "asof": pd.Timestamp(sista).strftime("%Y-%m-%d"),
        "uppdaterad": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "valuta": "lokal",
        "fonster_dagar": int(max(len(p["serie"]) for p in serier.values())),
        "bredd": {
            "sektorer_over_ma50": sum(1 for r in sektorer if (r["px_ma50"] or 0) > 0),
            "sektorer_over_ma150": sum(1 for r in sektorer if (r["px_ma150"] or 0) > 0),
            "antal_sektorer": len(sektorer),
            "cykliska_i_trend": sum(1 for r in rader if r["ticker"] in CYKLISKA and (r["px_ma150"] or 0) > 0),
            "defensiva_i_trend": sum(1 for r in rader if r["ticker"] in DEFENSIVA and (r["px_ma150"] or 0) > 0),
        },
        "varningar": varningar,
        "kalendrar": kalendrar,
        "rader": rader,
    }

    try:
        makro = hamta_makro(asof)
    except Exception as fel:                     # makro får aldrig fälla bygget
        makro, _ = None, varningar.append(f"Makrohämtningen fallerade: {fel}")
    if makro:
        ut["makro"] = makro
    else:
        varningar.append("Makrodata från FRED kunde inte hämtas — regimen utelämnas.")

    if asof:
        ut["uppdaterad"] = asof
        ut["rekonstruerad"] = True

    os.makedirs("data/history", exist_ok=True)
    if not asof:                   # en rekonstruktion rör aldrig nuläget
        with open("data/latest.json", "w", encoding="utf-8") as f:
            json.dump(ut, f, ensure_ascii=False, separators=(",", ":"))
    stamp = asof or f"{date.today():%Y-%m-%d}"
    with open(f"data/history/{stamp}.json", "w", encoding="utf-8") as f:
        json.dump(ut, f, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(rader)} instrument, kursdata till {ut['asof']}, "
          f"{ut['bredd']['sektorer_over_ma150']}/{ut['bredd']['antal_sektorer']} sektorer över MA150")
    if ut.get("makro"):
        m = ut["makro"]
        print(f"Regim: {m['regim']} | 10y {m.get('nominell10',{}).get('niva')} % "
              f"| realränta {m.get('real10',{}).get('niva')} % "
              f"| breakeven {m.get('breakeven10',{}).get('niva')} %")
    for v in varningar:
        print("VARNING:", v)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Bygg Branschkompassens underlag.")
    ap.add_argument("--asof", default="",
                    help="Ett eller flera datum (YYYY-MM-DD, kommaseparerade). "
                         "Bygger bilden som den sag ut de morgnarna och skriver "
                         "bara till data/history/. Utan flaggan byggs nulaget.")
    datum = [d.strip() for d in ap.parse_args().asof.split(",") if d.strip()]
    if datum:
        for d in datum:
            tvinga = d.startswith("!")       # ! framfor datumet bygger om det
            d = d.lstrip("!")
            if os.path.exists(f"data/history/{d}.json") and not tvinga:
                print(f"--- {d} finns redan, hoppar over (satt ! framfor for omkorning) ---")
                continue
            print(f"--- rekonstruerar {d}{' (tvingad omkorning)' if tvinga else ''} ---")
            main(d)
    else:
        main()
