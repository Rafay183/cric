"""
data_cleaning.py
================
Loading, cleaning, validating and exporting the ESPNcricinfo Test-batting dataset.

The raw file mixes numbers with Cricinfo display conventions, e.g.

    HS  "182*"   -> highest score, "*" = not out
    BF  "9800+"  -> balls faced, "+" = ball data missing for some matches
    BF  "-"      -> not available
    0   "-"      -> zero ducks
    Player "H Sutcliffe (ENG)" / "JH Kallis (ICC/SA)" -> name + team (+ ICC XI)

`clean_data()` converts all of that into analysis-ready numeric columns,
adds derived metrics and returns a human-readable cleaning log.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import IO, Union

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
RAW_COLUMNS = ["Player", "Span", "Mat", "Inns", "NO", "Runs", "HS", "Ave",
               "BF", "SR", "100", "50", "0", "4s", "6s"]

RENAME_MAP = {
    "Mat": "Matches", "Inns": "Innings", "NO": "Not_Outs", "HS": "High_Score",
    "Ave": "Average", "BF": "Balls_Faced", "SR": "Strike_Rate",
    "100": "Hundreds", "50": "Fifties", "0": "Ducks", "4s": "Fours", "6s": "Sixes",
}

COUNTRY_NAMES = {
    "AUS": "Australia", "ENG": "England", "WI": "West Indies", "SA": "South Africa",
    "SL": "Sri Lanka", "NZ": "New Zealand", "IND": "India", "PAK": "Pakistan",
    "ZIM": "Zimbabwe", "BAN": "Bangladesh", "AFG": "Afghanistan", "IRE": "Ireland",
    "ICC": "ICC World XI",
}

ERA_BINS = [0, 1945, 1970, 1990, 2005, 3000]
ERA_ORDER = ["Pre-1946", "1946–1970", "1971–1990", "1991–2005", "2006 onwards"]

# A player counts as "recently active" if their last Test year is this recent
RECENT_YEAR_THRESHOLD = 2024

DATA_DICTIONARY = [
    ("Player", "text", "Player name (country removed)"),
    ("Country_Code", "text", "Team code parsed from the player label, e.g. AUS"),
    ("Country", "text", "Full country name"),
    ("Played_ICC_XI", "bool", "True if the label contained 'ICC/' (also played for an ICC World XI)"),
    ("Debut_Year", "int", "First year of the career span"),
    ("Last_Year", "int", "Last year of the career span"),
    ("Career_Years", "int", "Last_Year - Debut_Year"),
    ("Era", "category", "Era bucket based on Debut_Year"),
    ("Recently_Active", "bool", f"Last_Year >= {RECENT_YEAR_THRESHOLD}"),
    ("Matches", "int", "Test matches played"),
    ("Innings", "int", "Innings batted"),
    ("Not_Outs", "int", "Number of not-out innings"),
    ("Dismissals", "int", "Innings - Not_Outs"),
    ("Runs", "int", "Total Test runs"),
    ("High_Score", "int", "Highest individual score (asterisk removed)"),
    ("High_Score_Not_Out", "bool", "True if highest score was not out ('*')"),
    ("Average", "float", "Batting average as published"),
    ("Balls_Faced", "float", "Balls faced (numeric; '+' and '-' removed). NaN if unavailable"),
    ("Balls_Faced_Status", "category", "Complete / Partial ('+' = records missing) / Not available ('-')"),
    ("Strike_Rate", "float", "Runs per 100 balls as published. NaN if unavailable"),
    ("SR_Reliable", "bool", "True when ball-by-ball data is complete -> strike rate is trustworthy"),
    ("Hundreds", "int", "Centuries"),
    ("Fifties", "int", "Half-centuries (50-99)"),
    ("Ducks", "int", "Dismissals for 0 ('-' in source = 0)"),
    ("Fours", "int", "Fours hit"),
    ("Sixes", "int", "Sixes hit"),
    ("Fifty_Plus", "int", "Hundreds + Fifties"),
    ("Runs_per_Match", "float", "Runs / Matches"),
    ("Runs_per_Inns", "float", "Runs / Innings"),
    ("Hundred_Rate_Pct", "float", "Hundreds per 100 innings"),
    ("Conversion_Pct", "float", "Hundreds / (Hundreds + Fifties) * 100"),
    ("Duck_Pct", "float", "Ducks / Innings * 100"),
    ("Not_Out_Pct", "float", "Not_Outs / Innings * 100"),
    ("Boundary_Runs", "int", "4 * Fours + 6 * Sixes"),
    ("Boundary_Pct", "float", "Boundary_Runs / Runs * 100"),
    ("Sixes_per_Inns", "float", "Sixes / Innings"),
    ("Rank_Average", "int", "Rank by batting average (1 = best)"),
    ("Rank_Runs", "int", "Rank by total runs (1 = most)"),
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_raw(source: Union[str, Path, IO]) -> pd.DataFrame:
    """Read the raw CSV exactly as published (everything stays as-is)."""
    df = pd.read_csv(source)
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "The file does not look like a Cricinfo batting table. "
            f"Missing columns: {', '.join(missing)}"
        )
    return df[RAW_COLUMNS].copy()


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
def _split_team(label: str) -> tuple[str, bool]:
    """'ICC/SA' -> ('SA', True) ; 'AUS' -> ('AUS', False)."""
    parts = [p.strip() for p in str(label).split("/") if p.strip()]
    icc = "ICC" in parts
    others = [p for p in parts if p != "ICC"]
    return (others[0] if others else "ICC"), icc


def clean_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Clean the raw table.

    Returns
    -------
    clean : analysis-ready DataFrame
    log   : DataFrame(Step, Column, Rows_Affected, Action) documenting every change
    """
    df = raw.copy()
    log: list[dict] = []

    def note(step, column, rows, action):
        log.append({"Step": step, "Column": column,
                    "Rows_Affected": int(rows), "Action": action})

    # 0. Whitespace / duplicates ------------------------------------------------
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype(str).str.strip()
    n_dup = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)
    note("Duplicates", "all", n_dup, "Removed exact duplicate rows")
    note("Missing values", "all", int(df.isna().sum().sum()),
         "Checked for true NaN values in the raw file")

    # 1. Player label -> name / team --------------------------------------------
    parsed = df["Player"].str.extract(r"^(?P<name>.+?)\s*\((?P<team>[^)]+)\)\s*$")
    no_team = parsed["team"].isna()
    parsed.loc[no_team, "name"] = df.loc[no_team, "Player"]
    parsed.loc[no_team, "team"] = "UNK"
    team = [_split_team(t) for t in parsed["team"]]
    df["Country_Code"] = [t[0] for t in team]
    df["Played_ICC_XI"] = [t[1] for t in team]
    df["Country"] = df["Country_Code"].map(COUNTRY_NAMES).fillna(df["Country_Code"])
    df["Player"] = parsed["name"].str.strip()
    note("Player label", "Player", len(df) - no_team.sum(),
         "Split 'Name (TEAM)' into Player + Country_Code + Country")
    note("Player label", "Played_ICC_XI", df["Played_ICC_XI"].sum(),
         "'ICC/XX' labels -> country XX and Played_ICC_XI = True")

    # 2. Span -> years -----------------------------------------------------------
    years = df["Span"].str.extract(r"(?P<a>\d{4})\s*-\s*(?P<b>\d{4})").astype(float)
    bad_span = years.isna().any(axis=1)
    df["Debut_Year"] = years["a"].astype("Int64")
    df["Last_Year"] = years["b"].astype("Int64")
    df["Career_Years"] = (df["Last_Year"] - df["Debut_Year"]).astype("Int64")
    df["Era"] = pd.cut(df["Debut_Year"].astype(float), bins=ERA_BINS,
                       labels=ERA_ORDER, right=True).astype(str)
    df["Recently_Active"] = df["Last_Year"] >= RECENT_YEAR_THRESHOLD
    note("Span", "Span", len(df) - bad_span.sum(),
         "Split '1928-1948' into Debut_Year, Last_Year, Career_Years; added Era and Recently_Active")

    # 3. High score --------------------------------------------------------------
    hs = df["HS"].astype(str).str.strip()
    df["High_Score_Not_Out"] = hs.str.endswith("*")
    df["High_Score"] = pd.to_numeric(hs.str.rstrip("*"), errors="coerce")
    note("High score", "HS", df["High_Score_Not_Out"].sum(),
         "Removed '*' -> numeric High_Score + High_Score_Not_Out flag")

    # 4. Balls faced -------------------------------------------------------------
    bf = df["BF"].astype(str).str.strip()
    partial = bf.str.endswith("+")
    missing = bf.isin(["-", "", "nan"])
    df["Balls_Faced"] = pd.to_numeric(bf.str.rstrip("+").where(~missing), errors="coerce")
    df["Balls_Faced_Status"] = np.select(
        [missing, partial], ["Not available", "Partial"], default="Complete")
    note("Balls faced", "BF", partial.sum(),
         "'+' removed (ball data incomplete for older matches) -> flagged as Partial")
    note("Balls faced", "BF", missing.sum(), "'-' converted to NaN (Not available)")

    # 5. Strike rate -------------------------------------------------------------
    sr_raw = df["SR"].astype(str).str.strip()
    sr_missing = sr_raw.isin(["-", "", "nan"])
    df["Strike_Rate"] = pd.to_numeric(sr_raw.where(~sr_missing), errors="coerce")
    df["SR_Reliable"] = df["Balls_Faced_Status"].eq("Complete") & df["Strike_Rate"].notna()
    note("Strike rate", "SR", sr_missing.sum(), "'-' converted to NaN")
    note("Strike rate", "SR_Reliable", (~df["SR_Reliable"]).sum(),
         "Flagged strike rates based on partial / missing ball data as not reliable")

    # 6. Ducks / numeric columns -------------------------------------------------
    duck_raw = df["0"].astype(str).str.strip()
    df["Ducks"] = pd.to_numeric(duck_raw.replace({"-": "0", "": "0"}), errors="coerce")
    note("Ducks", "0", (duck_raw == "-").sum(), "'-' means no ducks -> 0")

    for src, dst in [("Mat", "Matches"), ("Inns", "Innings"), ("NO", "Not_Outs"),
                     ("Runs", "Runs"), ("Ave", "Average"), ("100", "Hundreds"),
                     ("50", "Fifties"), ("4s", "Fours"), ("6s", "Sixes")]:
        df[dst] = pd.to_numeric(df[src], errors="coerce")
    note("Types", "numeric columns", 9, "Converted counting columns to numeric types")

    # 7. Derived metrics ---------------------------------------------------------
    df["Dismissals"] = df["Innings"] - df["Not_Outs"]
    df["Fifty_Plus"] = df["Hundreds"] + df["Fifties"]
    df["Runs_per_Match"] = (df["Runs"] / df["Matches"]).round(2)
    df["Runs_per_Inns"] = (df["Runs"] / df["Innings"]).round(2)
    df["Hundred_Rate_Pct"] = (df["Hundreds"] / df["Innings"] * 100).round(2)
    df["Conversion_Pct"] = (df["Hundreds"] / df["Fifty_Plus"] * 100).round(2)
    df["Duck_Pct"] = (df["Ducks"] / df["Innings"] * 100).round(2)
    df["Not_Out_Pct"] = (df["Not_Outs"] / df["Innings"] * 100).round(2)
    df["Boundary_Runs"] = df["Fours"] * 4 + df["Sixes"] * 6
    df["Boundary_Pct"] = (df["Boundary_Runs"] / df["Runs"] * 100).round(2)
    df["Sixes_per_Inns"] = (df["Sixes"] / df["Innings"]).round(3)
    df["Rank_Average"] = df["Average"].rank(ascending=False, method="min").astype(int)
    df["Rank_Runs"] = df["Runs"].rank(ascending=False, method="min").astype(int)
    note("Feature engineering", "13 derived columns", len(df),
         "Added Dismissals, Fifty_Plus, per-match/innings rates, conversion %, duck %, "
         "boundary runs & %, sixes per innings, ranks")

    # 8. Validation --------------------------------------------------------------
    recomputed = (df["Runs"] / df["Dismissals"]).round(2)
    mismatch = int(((recomputed - df["Average"]).abs() > 0.02).sum())
    note("Validation", "Average", mismatch,
         "Rows where Runs / (Innings - NO) differs from published Average by > 0.02 (0 = consistent)")
    note("Validation", "Not_Outs", int((df["Not_Outs"] > df["Innings"]).sum()),
         "Rows where Not_Outs > Innings (0 = consistent)")
    note("Validation", "Innings", int((df["Innings"] > 2 * df["Matches"]).sum()),
         "Rows where Innings > 2 x Matches - impossible in Tests (0 = consistent)")
    note("Validation", "High_Score", int((df["High_Score"] > df["Runs"]).sum()),
         "Rows where High_Score > Runs (0 = consistent)")
    note("Validation", "Hundreds/Fifties", int((df["Fifty_Plus"] > df["Innings"]).sum()),
         "Rows where 50+ scores exceed innings (0 = consistent)")

    # 9. Final column order ------------------------------------------------------
    cols = [c for c, _, _ in DATA_DICTIONARY]
    clean = df[cols].copy()
    for c in ["Debut_Year", "Last_Year", "Career_Years"]:
        clean[c] = clean[c].astype(int)
    for c in ["Matches", "Innings", "Not_Outs", "Dismissals", "Runs", "High_Score",
              "Hundreds", "Fifties", "Ducks", "Fours", "Sixes", "Fifty_Plus", "Boundary_Runs"]:
        clean[c] = clean[c].astype(int)
    clean = clean.sort_values("Average", ascending=False).reset_index(drop=True)

    log_df = pd.DataFrame(log)
    return clean, log_df


# --------------------------------------------------------------------------- #
# Summaries & export
# --------------------------------------------------------------------------- #
def country_summary(clean: pd.DataFrame) -> pd.DataFrame:
    g = clean.groupby("Country").agg(
        Players=("Player", "count"),
        Total_Runs=("Runs", "sum"),
        Dismissals=("Dismissals", "sum"),
        Hundreds=("Hundreds", "sum"),
        Fifties=("Fifties", "sum"),
        Sixes=("Sixes", "sum"),
        Best_Average=("Average", "max"),
    ).reset_index()
    g["Aggregate_Average"] = (g["Total_Runs"] / g["Dismissals"]).round(2)
    return g.sort_values("Total_Runs", ascending=False).reset_index(drop=True)


def data_dictionary_df() -> pd.DataFrame:
    return pd.DataFrame(DATA_DICTIONARY, columns=["Column", "Type", "Description"])


def export_excel(clean: pd.DataFrame, raw: pd.DataFrame, log: pd.DataFrame) -> bytes:
    """Build a formatted multi-sheet workbook and return it as bytes."""
    buf = io.BytesIO()
    sheets = {
        "Cleaned Data": clean,
        "Raw Data": raw,
        "Country Summary": country_summary(clean),
        "Cleaning Log": log,
        "Data Dictionary": data_dictionary_df(),
    }
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#1F4E79",
                                "border": 1, "align": "center", "valign": "vcenter"})
        for name, d in sheets.items():
            d.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for i, col in enumerate(d.columns):
                ws.write(0, i, col, header)
                longest = d[col].astype(str).str.len().max() if len(d) else 0
                ws.set_column(i, i, min(max(len(str(col)), int(longest)) + 2, 70))
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(d), len(d.columns) - 1)

        ws = xw.sheets["Cleaned Data"]
        n = len(clean)
        runs_col = list(clean.columns).index("Runs")
        avg_col = list(clean.columns).index("Average")
        ws.conditional_format(1, runs_col, n, runs_col, {"type": "data_bar", "bar_color": "#5B9BD5"})
        ws.conditional_format(1, avg_col, n, avg_col, {"type": "3_color_scale",
                                                       "min_color": "#F8696B", "mid_color": "#FFEB84",
                                                       "max_color": "#63BE7B"})
    return buf.getvalue()


def save_cleaned(src: Union[str, Path], out_dir: Union[str, Path]) -> pd.DataFrame:
    """CLI helper: clean `src` and write CSV + Excel next to the project."""
    out_dir = Path(out_dir)
    raw = load_raw(src)
    clean, log = clean_data(raw)
    clean.to_csv(out_dir / "cricinfo_cleaned.csv", index=False)
    (out_dir / "cricinfo_cleaned.xlsx").write_bytes(export_excel(clean, raw, log))
    log.to_csv(out_dir / "cleaning_log.csv", index=False)
    return clean


if __name__ == "__main__":
    here = Path(__file__).parent
    df = save_cleaned(here / "data" / "cricinfo.csv", here)
    print(f"Cleaned {len(df)} rows x {df.shape[1]} columns -> cricinfo_cleaned.csv / .xlsx")
