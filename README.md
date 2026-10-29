# 🏏 Test Batting Legends — Streamlit Dashboard

Interactive analytics dashboard for the ESPNcricinfo Test-batting export
(62 elite batsmen: average ≥ 48, ≥ 1,000 runs).

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Project layout
| File | Purpose |
|---|---|
| `app.py` | Streamlit dashboard (6 tabs, ~20 interactive charts, sidebar filters) |
| `data_cleaning.py` | Load → clean → validate → engineer features → export (also runnable as a script) |
| `data/cricinfo.csv` | Raw source file |
| `cricinfo_cleaned.csv` / `.xlsx` | Cleaned output (xlsx has Cleaned, Raw, Country Summary, Cleaning Log, Data Dictionary sheets) |
| `cleaning_log.csv` | Every transformation + validation result |
| `tests/test_cleaning.py` | Unit tests for the cleaning layer (`pytest -q`) |

Regenerate the cleaned files: `python data_cleaning.py`

## What was cleaned
| Raw issue | Fix |
|---|---|
| `Player = "JH Kallis (ICC/SA)"` | Split into `Player`, `Country_Code`, `Country`, `Played_ICC_XI` |
| `Span = "1928-1948"` | `Debut_Year`, `Last_Year`, `Career_Years`, `Era`, `Recently_Active` |
| `HS = "182*"` | Numeric `High_Score` + `High_Score_Not_Out` flag |
| `BF = "9800+"` / `"-"` | Numeric `Balls_Faced`; `+` → status *Partial*, `-` → NaN |
| `SR = "-"` | NaN; `SR_Reliable` flags strike rates built on partial ball data |
| `0 = "-"` (ducks) | 0 |
| Text-typed numbers | Proper int / float dtypes |
| Validation | Average = Runs ÷ (Inns − NO), NO ≤ Inns, Inns ≤ 2×Mat, HS ≤ Runs — all pass |

13 derived metrics are added (boundary %, conversion %, duck %, runs/innings, ranks, …);
see the *Data Dictionary* tab inside the app.

## Dashboard tabs
1. **Overview** – KPIs, rank-by-any-metric bar, longevity vs volume, quality vs longevity, auto-insights
2. **Countries & Eras** – runs & share by country, average spread, era trends, career timelines
3. **Style & Strike Rate** – SR vs average, SR by era, boundary vs running runs, six-hitting rate
4. **Player Comparison** – radar profile + head-to-head table for 2–5 players
5. **Distributions & Correlations** – histogram, stats table, correlation heatmap, custom scatter builder
6. **Data & Downloads** – cleaned/raw tables, cleaning log, data dictionary, CSV + Excel downloads

## Notes & assumptions
* Strike rates for older players rely on incomplete balls-faced records, so strike-rate charts default to
  *reliable data only* (toggle in the sidebar).
* "Recently active" = last Test year ≥ 2024 (change `RECENT_YEAR_THRESHOLD` in `data_cleaning.py`).
* Era buckets use debut year: Pre-1946, 1946–70, 1971–90, 1991–2005, 2006+.
* Don Bradman (avg 99.94) skews many charts; use the sidebar toggle to exclude him.
* You can upload another CSV with the same 15 columns from the sidebar.
"# cric" 
