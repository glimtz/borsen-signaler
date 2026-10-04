"""Makrolager: räntor och inflation i USA, och vilken regim de beskriver.

Hämtar dagliga och månatliga serier från FRED. Ingen API-nyckel behövs för
CSV-uttaget. Modulen kastar aldrig vidare ett fel — misslyckas hämtningen
returneras None och resten av bygget fortsätter utan makroavsnitt.

Den avgörande frågan modulen försöker svara på: när den långa räntan rör sig,
är det REALRÄNTAN eller INFLATIONSFÖRVÄNTNINGEN som rör sig? Finansiell
repression — att inflatera bort en skuld — kräver stigande breakeven och
pressad realränta. Stiger i stället realräntan är marknaden inte med på noten,
och allokeringsslutsatserna blir de omvända.
"""

from __future__ import annotations

import io
import urllib.request
from datetime import date

import pandas as pd

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

SERIER = {
    "nominell10": "DGS10",     # 10-årig nominell statsränta
    "real10": "DFII10",        # 10-årig realränta (TIPS)
    "breakeven10": "T10YIE",   # 10-årig breakeven-inflation
    "forward5y5y": "T5YIFR",   # 5-årig inflationsförväntan om 5 år
    "styrranta": "FEDFUNDS",   # effektiv styrränta, månadsvis
    # Ej säsongsjusterade index — det är dem BLS räknar den publicerade
    # årstakten på. De säsongsjusterade (CPIAUCSL/CPILFESL) ger ett par
    # tiondelar fel mot den siffra som står i tidningen.
    "kpi": "CPIAUCNS",         # KPI, nivåindex, månadsvis
    "karn_kpi": "CPILFENS",    # kärn-KPI, nivåindex, månadsvis
    "kurva10_2": "T10Y2Y",     # lutning 10 år minus 2 år
}

# handelsdagar bakåt för dagliga serier
FONSTER = {"1v": 5, "1m": 21, "3m": 63, "12m": 252}

# Hur de fyra regimerna brukar slå. Dokumenterad tumregel, inte en prognos.
REGIMTEXT = {
    "Realräntetryck": dict(
        beskrivning="Den långa räntan stiger för att realräntan stiger, medan "
                    "inflationsförväntningarna står stilla. Marknaden kräver mer "
                    "betalt i reala termer, inte kompensation för inflation.",
        medvind=["Energi", "Finans", "Kort ränta och kontanter"],
        motvind=["Lång US-statsobligation", "Fastigheter", "Kraft/Utilities",
                 "Guld", "Silver", "Investmentbolag"],
    ),
    "Inflationsdrivet": dict(
        beskrivning="Inflationsförväntningarna stiger medan realräntan står still "
                    "eller faller. Det är signaturen för finansiell repression — "
                    "skulden urholkas av inflation.",
        medvind=["Guld", "Silver", "Olja (WTI)", "Koppar", "Energi", "Material"],
        motvind=["Lång US-statsobligation", "Kort ränta och kontanter", "Dagligvaror"],
    ),
    "Stagflationsrisk": dict(
        beskrivning="Både realränta och inflationsförväntan stiger. Den dyraste "
                    "kombinationen för de flesta tillgångsslag.",
        medvind=["Energi", "Olja (WTI)", "Guld", "Dagligvaror", "Hälsovård"],
        motvind=["Sällanköp", "Fastigheter", "Lång US-statsobligation", "Teknik"],
    ),
    "Lättnad": dict(
        beskrivning="Både realränta och inflationsförväntan faller. Lättare "
                    "finansiella villkor framåt.",
        medvind=["Lång US-statsobligation", "Fastigheter", "Kraft/Utilities",
                 "Teknik", "Sällanköp"],
        motvind=["Energi", "Olja (WTI)"],
    ),
    "Neutralt": dict(
        beskrivning="Varken realränta eller inflationsförväntan har rört sig "
                    "nämnvärt det senaste kvartalet.",
        medvind=[], motvind=[],
    ),
}

# Hur mycket en komponent måste ha rört sig på tre månader för att räknas,
# i procentenheter.
TROSKEL = 0.15


def _hamta(serie_id: str, transformation: str = "") -> pd.Series | None:
    url = FRED.format(serie_id) + (f"&transformation={transformation}" if transformation else "")
    try:
        with urllib.request.urlopen(url, timeout=45) as svar:
            rå = svar.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(rå))
    except Exception:
        return None
    if df.shape[1] < 2:
        return None
    datumkol = df.columns[0]
    df[datumkol] = pd.to_datetime(df[datumkol], errors="coerce")
    s = pd.to_numeric(df[df.columns[1]], errors="coerce")  # "." blir NaN
    s.index = df[datumkol]
    s = s.dropna()
    return s if len(s) > 10 else None


def _forandring(s: pd.Series, n: int) -> float | None:
    if s is None or len(s) <= n:
        return None
    return round(float(s.iloc[-1] - s.iloc[-1 - n]), 2)


def _aratakt(nivaserie: pd.Series | None) -> float | None:
    """Årstakt ur ett månatligt nivåindex, t.ex. KPI."""
    if nivaserie is None or len(nivaserie) < 13:
        return None
    return round(float(nivaserie.iloc[-1] / nivaserie.iloc[-13] - 1) * 100, 2)


def hamta_makro() -> dict | None:
    varningar_makro: list[str] = []
    serier = {namn: _hamta(sid) for namn, sid in SERIER.items()}
    if serier.get("nominell10") is None or serier.get("breakeven10") is None:
        return None

    ut: dict = {"hamtad": date.today().isoformat(), "kallor": {}}
    for namn in ("nominell10", "real10", "breakeven10", "forward5y5y", "kurva10_2"):
        s = serier.get(namn)
        if s is None:
            continue
        ut[namn] = {
            "niva": round(float(s.iloc[-1]), 2),
            "datum": s.index[-1].strftime("%Y-%m-%d"),
            **{f"d{k}": _forandring(s, n) for k, n in FONSTER.items()},
        }
        ut["kallor"][namn] = SERIER[namn]

    # Årstakten hämtas som FREDs egen pc1-transformation, alltså exakt den
    # siffra BLS publicerar. Att räkna den själv ur nivåindexet gav 3,69 % när
    # publicerat värde var 3,4 — indexnivåerna revideras och stämmer inte
    # alltid med den offentliggjorda takten. Räkna bara själv om pc1 fallerar.
    def takt(nyckel: str, serie_id: str):
        s_pc1 = _hamta(serie_id, "pc1")
        if s_pc1 is not None and abs(float(s_pc1.iloc[-1])) < 50:
            return round(float(s_pc1.iloc[-1]), 2), s_pc1.index[-1]
        varningar_makro.append(f"{serie_id}: pc1 gick inte att hämta, årstakten räknad ur nivåindexet")
        return _aratakt(serier.get(nyckel)), (serier[nyckel].index[-1] if serier.get(nyckel) is not None else None)

    kpi_takt, kpi_datum = takt("kpi", SERIER["kpi"])
    karn_takt_v, _ = takt("karn_kpi", SERIER["karn_kpi"])
    ut["inflation"] = {
        "kpi_arstakt": kpi_takt,
        "karn_arstakt": karn_takt_v,
        "datum": kpi_datum.strftime("%Y-%m") if kpi_datum is not None else None,
    }
    if varningar_makro:
        ut["varningar"] = list(varningar_makro)
    styr = serier.get("styrranta")
    if styr is not None:
        ut["styrranta"] = {"niva": round(float(styr.iloc[-1]), 2),
                           "datum": styr.index[-1].strftime("%Y-%m")}
        kt = ut["inflation"]["karn_arstakt"]
        if kt is not None:
            ut["real_styrranta"] = round(float(styr.iloc[-1]) - kt, 2)

    # Vad drev den långa räntan de senaste tre månaderna?
    d_nom = ut.get("nominell10", {}).get("d3m")
    d_real = ut.get("real10", {}).get("d3m")
    d_be = ut.get("breakeven10", {}).get("d3m")
    if d_nom is not None and d_real is not None and d_be is not None:
        ut["uppdelning_3m"] = {
            "nominell": d_nom, "realranta": d_real, "breakeven": d_be,
            "realrantans_andel": (round(abs(d_real) / (abs(d_real) + abs(d_be)) * 100)
                                  if (abs(d_real) + abs(d_be)) > 0 else None),
        }

    if d_real is None or d_be is None:
        regim = "Neutralt"
    elif d_be > TROSKEL and d_real <= 0:
        regim = "Inflationsdrivet"
    elif d_be > TROSKEL and d_real > 0:
        regim = "Stagflationsrisk"
    elif d_real > TROSKEL and d_be <= TROSKEL:
        regim = "Realräntetryck"
    elif d_real < -TROSKEL and d_be < -TROSKEL:
        regim = "Lättnad"
    else:
        regim = "Neutralt"

    ut["regim"] = regim
    ut.update({f"regim_{k}": v for k, v in REGIMTEXT[regim].items()})

    # Vad som skulle byta regim härifrån — tröskeln att bevaka
    be_niva = ut.get("breakeven10", {}).get("niva")
    ut["vandpunkt"] = (
        f"Breakeven över {be_niva + 0.25:.2f} % medan realräntan planar ut eller "
        f"faller betyder att marknaden börjar prissätta inflation i stället för "
        f"realränta — då byter regimen till Inflationsdrivet."
        if be_niva is not None else None
    )
    return ut


if __name__ == "__main__":
    import json
    print(json.dumps(hamta_makro(), ensure_ascii=False, indent=1))
