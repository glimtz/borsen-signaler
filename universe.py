"""Bevakningslistan för Branschkompass.

Varje post är antingen en enskild ticker eller en likaviktad korg.
`valuta` avgör om serien räknas om till SEK innan avkastning beräknas —
allt jämförs i SEK, eftersom det är den avkastning Leif faktiskt får.
"""

# Enskilda instrument: nyckel -> (namn, grupp, yahoo-ticker, valuta)
SINGLES = {
    "XLK":  ("Teknik",                  "US-sektor",    "XLK",  "USD"),
    "XLE":  ("Energi",                  "US-sektor",    "XLE",  "USD"),
    "XLF":  ("Finans",                  "US-sektor",    "XLF",  "USD"),
    "XLV":  ("Hälsovård",               "US-sektor",    "XLV",  "USD"),
    "XLI":  ("Industri",                "US-sektor",    "XLI",  "USD"),
    "XLY":  ("Sällanköp",               "US-sektor",    "XLY",  "USD"),
    "XLP":  ("Dagligvaror",             "US-sektor",    "XLP",  "USD"),
    "XLU":  ("Kraft/Utilities",         "US-sektor",    "XLU",  "USD"),
    "XLB":  ("Material",                "US-sektor",    "XLB",  "USD"),
    "XLRE": ("Fastigheter",             "US-sektor",    "XLRE", "USD"),
    "XLC":  ("Kommunikation",           "US-sektor",    "XLC",  "USD"),

    "SPY":  ("USA (S&P 500)",           "Region",       "SPY",  "USD"),
    "EFA":  ("Utvecklade marknader",    "Region",       "EFA",  "USD"),
    "EEM":  ("Tillväxtmarknader",       "Region",       "EEM",  "USD"),
    "EWJ":  ("Japan",                   "Region",       "EWJ",  "USD"),
    "EWD":  ("Sverige (EWD)",           "Region",       "EWD",  "USD"),
    "OMX":  ("OMXS30",                  "Region",       "^OMX", "SEK"),

    "GLD":  ("Guld",                    "Råvara/Ränta", "GLD",  "USD"),
    "SLV":  ("Silver",                  "Råvara/Ränta", "SLV",  "USD"),
    "USO":  ("Olja (WTI)",              "Råvara/Ränta", "USO",  "USD"),
    "CPER": ("Koppar",                  "Råvara/Ränta", "CPER", "USD"),
    "TLT":  ("Lång US-statsobligation", "Råvara/Ränta", "TLT",  "USD"),
}

# Svenska branschkorgar: nyckel -> (namn, grupp, [tickers], valuta)
# Likaviktade index, varje bolag normaliserat till 100 vid periodens start.
BASKETS = {
    "SE_VERKSTAD": ("Verkstad",         "SE-bransch", ["VOLV-B.ST", "ATCO-A.ST", "SAND.ST", "SKF-B.ST", "ALFA.ST"], "SEK"),
    "SE_BANK":     ("Bank & finans",    "SE-bransch", ["SEB-A.ST", "SWED-A.ST", "SHB-A.ST", "NDA-SE.ST"],          "SEK"),
    "SE_FASTIGH":  ("Fastigheter",      "SE-bransch", ["CAST.ST", "BALD-B.ST", "FABG.ST", "WIHL.ST"],              "SEK"),
    "SE_TELEIT":   ("Telekom & IT",     "SE-bransch", ["ERIC-B.ST", "TELIA.ST", "HEXA-B.ST"],                      "SEK"),
    "SE_HALSA":    ("Hälsovård",        "SE-bransch", ["AZN.ST", "GETI-B.ST", "SOBI.ST"],                          "SEK"),
    "SE_KONSUM":   ("Konsument",        "SE-bransch", ["ESSITY-B.ST", "AXFO.ST", "ELUX-B.ST", "HM-B.ST"],          "SEK"),
    "SE_INVEST":   ("Investmentbolag",  "SE-bransch", ["INVE-B.ST", "LATO-B.ST", "INDU-C.ST", "KINV-B.ST"],        "SEK"),
}

# Jämförelseindex för relativ styrka (i SEK)
BENCHMARK = "SPY"

# Växelkurs USD -> SEK
FX_USDSEK = "SEK=X"

# Grupper som räknas som cykliska respektive defensiva i breddmåttet
CYKLISKA = ["XLK", "XLY", "XLF", "XLI"]
DEFENSIVA = ["XLP", "XLU", "XLV", "TLT"]
US_SEKTORER = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
