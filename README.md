# Branschkompass — dataunderlag

Hämtar kursdata och räknar fram relativ styrka och trendläge för 29 branscher,
regioner och råvaror, plus växelkursen USD/SEK som kontextrad. Resultatet hamnar i `data/latest.json`, som dashboarden
i Claude läser varje vecka.

## Vad som körs

GitHub Actions kör `build.py` varje måndag 05:10 UTC. Du kan också starta den
manuellt under fliken **Actions → Veckokörning → Run workflow**.

Jobbet hämtar två års dagliga kurser via `yfinance`, räknar om allt till SEK,
beräknar måtten nedan och committar `data/latest.json` plus en daterad kopia i
`data/history/`. Ändras ingenting committas ingenting.

## Bevakningslista

| Grupp | Innehåll |
|---|---|
| US-sektor | De elva SPDR-sektorerna (XLK, XLE, XLF, XLV, XLI, XLY, XLP, XLU, XLB, XLRE, XLC) |
| SE-bransch | Sju likaviktade korgar av Stockholmsbolag: verkstad, bank & finans, fastigheter, telekom & IT, hälsovård, konsument, investmentbolag |
| Region | SPY, EFA, EEM, EWJ, EWD, OMXS30 |
| Råvara/Ränta | Guld, silver, olja, koppar, lång US-statsobligation |
| Valuta | USD/SEK — rankas inte och påverkar inte de andras percentiler, den finns som kontext |

Listan ändras i `universe.py`. En korg behöver minst två bolag med data för att
tas med; bolag som saknas hamnar i `varningar` i utdatan i stället för att
stoppa körningen.

## Måtten

Allt mäts i **instrumentets egen valuta** — amerikanska poster i dollar, svenska i
kronor. Det ger rena marknadssignaler utan valutabrus, men avkastningstalen är
därmed inte den avkastning en svensk investerare fått på ett ovalutasäkrat
innehav. Raden USD/SEK visar hur stor den skillnaden är.

- **Avkastning** över 1 vecka, 1, 3, 6 och 12 månader (5/21/63/126/252 handelsdagar).
- **Glidande medelvärden** MA20, MA50, MA100, MA150, MA200, samt lutningen på
  MA150 den senaste månaden.
- **Läge i 52 veckor** — var priset står i det senaste årets intervall.
- **Relativ styrka** över 1, 3 och 6 månader mot ett index i samma valuta:
  svenska branscher mot OMXS30, övriga mot SPY. Den siffran är därmed helt fri
  från växelkursen.
- **Trend** — MA50 mot MA150 är primärfiltret. MA150 motsvarar Weinsteins
  30-veckorssnitt och är anpassat till den takt branscher roterar i.
  *Stark upptrend* kräver pris över båda och stigande MA150.
- **Styrka** — percentilrang över hela listan, viktad 1 mån 20 %, 3 mån 30 %,
  6 mån 30 %, 12 mån 20 %.
- **Signal** — kräver att styrka och trend pekar åt samma håll. Översta
  tredjedelen i upptrend ger ÖVERVIKT, nedersta i nedtrend ger UNDERVIKT, och
  när de spretar blir det BEVAKA.
- **Kvadrant** — relativ styrka över 3 månader mot förändringen senaste månaden:
  Ledande, Försvagas, Eftersläpande, Förbättras.

## Köra lokalt

```bash
pip install -r requirements.txt
python build.py
```

## Om något går fel

Jobbet avbryter utan att skriva något om yfinance inte svarar alls eller om
jämförelseindexet SPY saknas — hellre gammal data i
dashboarden än halv data. Enskilda tickers som fallerar utelämnas och listas i
`varningar`, som visas i dashboarden.
