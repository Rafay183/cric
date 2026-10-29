"""Run with:  pytest -q   (or: python tests/test_cleaning.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data_cleaning import clean_data, export_excel, load_raw

RAW = Path(__file__).resolve().parents[1] / "data" / "cricinfo.csv"


def _clean():
    raw = load_raw(RAW)
    clean, log = clean_data(raw)
    return raw, clean, log


def test_shape_and_no_duplicates():
    raw, clean, _ = _clean()
    assert len(clean) == len(raw) == 62
    assert clean.Player.is_unique


def test_markers_removed():
    _, c, _ = _clean()
    for col in ["High_Score", "Balls_Faced", "Strike_Rate", "Ducks"]:
        assert pd.api.types.is_numeric_dtype(c[col]), col
    b = c.set_index("Player")
    assert b.loc["PHKD Mendis", "High_Score"] == 182 and b.loc["PHKD Mendis", "High_Score_Not_Out"]
    assert b.loc["DG Bradman", "Balls_Faced"] == 9800 and b.loc["DG Bradman", "Balls_Faced_Status"] == "Partial"
    assert b.loc["PHKD Mendis", "Ducks"] == 0
    assert np.isnan(b.loc["ED Weekes", "Strike_Rate"])


def test_player_label_split():
    _, c, _ = _clean()
    b = c.set_index("Player")
    assert b.loc["JH Kallis", "Country"] == "South Africa" and b.loc["JH Kallis", "Played_ICC_XI"]
    assert b.loc["SR Tendulkar", "Country"] == "India" and not b.loc["SR Tendulkar", "Played_ICC_XI"]
    assert not c.Player.str.contains(r"\(").any()


def test_span_and_era():
    _, c, _ = _clean()
    b = c.set_index("Player")
    assert (b.loc["DG Bradman", "Debut_Year"], b.loc["DG Bradman", "Last_Year"]) == (1928, 1948)
    assert b.loc["DG Bradman", "Era"] == "Pre-1946"
    assert (c.Last_Year >= c.Debut_Year).all()


def test_derived_metrics_consistent():
    _, c, log = _clean()
    assert ((c.Runs / c.Dismissals).round(2) - c.Average).abs().max() <= 0.02
    assert (c.Boundary_Runs <= c.Runs).all()
    assert (c.Not_Outs <= c.Innings).all()
    assert log[log.Step == "Validation"].Rows_Affected.sum() == 0


def test_excel_export_has_all_sheets():
    import io
    raw, clean, log = _clean()
    xls = pd.ExcelFile(io.BytesIO(export_excel(clean, raw, log)))
    assert xls.sheet_names == ["Cleaned Data", "Raw Data", "Country Summary",
                               "Cleaning Log", "Data Dictionary"]
    assert len(pd.read_excel(xls, "Cleaned Data")) == 62


def test_bad_file_rejected():
    import io
    try:
        load_raw(io.StringIO("a,b\n1,2\n"))
    except ValueError:
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
