"""
Test Batting Legends — Streamlit analytics dashboard
Run with:  streamlit run app.py
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_cleaning import (
    ERA_ORDER, RECENT_YEAR_THRESHOLD,
    clean_data, country_summary, data_dictionary_df, export_excel, load_raw,
)

# --------------------------------------------------------------------------- #
# Page setup
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Test Batting Legends", page_icon="🏏", layout="wide")

DEFAULT_CSV = Path(__file__).parent / "data" / "cricinfo.csv"
TEMPLATE = "plotly_white"

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem;}
      div[data-testid="stMetric"] {
          background: rgba(120,120,120,0.08); border-radius: 10px; padding: 10px 14px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Small helpers (keep Streamlit-version differences in one place)
# --------------------------------------------------------------------------- #
def show(fig: go.Figure) -> None:
    fig.update_layout(template=TEMPLATE, margin=dict(l=10, r=10, t=50, b=10))
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:  # older Streamlit
        st.plotly_chart(fig, use_container_width=True)


def table(df: pd.DataFrame, **kwargs) -> None:
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kwargs)
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True, **kwargs)


def pick_n(label: str, cap: int, default: int, key: str) -> int:
    """Slider that degrades gracefully when only a handful of players are left."""
    if cap <= 3:
        return cap
    return st.slider(label, 3, cap, min(default, cap), key=key)


@st.cache_data(show_spinner="Cleaning data…")
def get_data(file_bytes: bytes | None):
    source = io.BytesIO(file_bytes) if file_bytes else DEFAULT_CSV
    raw = load_raw(source)
    clean, log = clean_data(raw)
    return raw, clean, log


@st.cache_data(show_spinner="Building Excel workbook…")
def build_excel(raw: pd.DataFrame, clean: pd.DataFrame, log: pd.DataFrame) -> bytes:
    return export_excel(clean, raw, log)


# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #
st.sidebar.title("🏏 Filters")
upload = st.sidebar.file_uploader("Use your own CSV (same format)", type="csv")
try:
    raw_df, clean_df, clean_log = get_data(upload.getvalue() if upload else None)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load the data: {exc}")
    st.stop()

countries = sorted(clean_df["Country"].unique())
palette = px.colors.qualitative.Bold + px.colors.qualitative.Safe
COLORS = {c: palette[i % len(palette)] for i, c in enumerate(countries)}
ERA_CAT = {"Era": ERA_ORDER}

# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
sel_countries = st.sidebar.multiselect("Country", countries, default=countries)
sel_eras = st.sidebar.multiselect("Era (by debut year)", ERA_ORDER, default=ERA_ORDER)
m_lo, m_hi = int(clean_df.Matches.min()), int(clean_df.Matches.max())
sel_matches = st.sidebar.slider("Matches played", m_lo, m_hi, (m_lo, m_hi))
a_lo, a_hi = float(clean_df.Average.min()), float(clean_df.Average.max())
sel_avg = st.sidebar.slider("Batting average", float(np.floor(a_lo)), float(np.ceil(a_hi)),
                            (float(np.floor(a_lo)), float(np.ceil(a_hi))), step=0.5)
search = st.sidebar.text_input("Search player")
recent_only = st.sidebar.checkbox(f"Recently active only (last Test ≥ {RECENT_YEAR_THRESHOLD})")
drop_bradman = st.sidebar.checkbox("Exclude Don Bradman (statistical outlier)")
reliable_sr = st.sidebar.checkbox("Strike-rate charts: reliable data only", value=True,
                                  help="Older players have incomplete balls-faced records, "
                                       "which makes their strike rate less trustworthy.")

mask = (
    clean_df.Country.isin(sel_countries)
    & clean_df.Era.isin(sel_eras)
    & clean_df.Matches.between(*sel_matches)
    & clean_df.Average.between(*sel_avg)
)
if search:
    mask &= clean_df.Player.str.contains(search, case=False, regex=False)
if recent_only:
    mask &= clean_df.Recently_Active
if drop_bradman:
    mask &= ~clean_df.Player.str.contains("Bradman")
fdf = clean_df[mask].copy()

st.title("🏏 Test Batting Legends — Analytics Dashboard")
st.caption("Elite Test batsmen (average ≥ 48, ≥ 1,000 runs) · source: ESPNcricinfo export · "
           "all figures update with the sidebar filters")

if fdf.empty:
    st.warning("No players match the current filters. Widen the filters in the sidebar.")
    st.stop()

# --------------------------------------------------------------------------- #
# KPI row
# --------------------------------------------------------------------------- #
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Players", f"{len(fdf)}")
k2.metric("Total runs", f"{fdf.Runs.sum():,}")
k3.metric("Centuries", f"{fdf.Hundreds.sum():,}")
k4.metric("Sixes", f"{fdf.Sixes.sum():,}")
k5.metric("Aggregate average", f"{fdf.Runs.sum() / fdf.Dismissals.sum():.2f}")
k6.metric("Avg career length", f"{fdf.Career_Years.mean():.1f} yrs")

tab_over, tab_ctry, tab_style, tab_cmp, tab_dist, tab_data = st.tabs(
    ["📊 Overview", "🌍 Countries & Eras", "⚡ Style & Strike Rate",
     "🔍 Player Comparison", "📈 Distributions & Correlations", "🗂️ Data & Downloads"]
)

# =========================================================================== #
# TAB 1 — Overview
# =========================================================================== #
with tab_over:
    METRICS = {
        "Runs": "Runs", "Batting average": "Average", "Centuries": "Hundreds",
        "Half-centuries": "Fifties", "Sixes": "Sixes", "Fours": "Fours",
        "Matches": "Matches", "Highest score": "High_Score",
        "Conversion % (50→100)": "Conversion_Pct", "Boundary % of runs": "Boundary_Pct",
    }
    c1, c2 = st.columns([1, 3])
    metric_label = c1.selectbox("Rank players by", list(METRICS), index=0)
    with c1:
        top_n = pick_n("How many players", min(30, len(fdf)), 10, "top_n")
    mcol = METRICS[metric_label]
    top = fdf.nlargest(top_n, mcol).sort_values(mcol)
    fig = px.bar(top, x=mcol, y="Player", color="Country", orientation="h", text=mcol,
                 color_discrete_map=COLORS, title=f"Top {len(top)} by {metric_label.lower()}",
                 hover_data=["Matches", "Runs", "Average", "Hundreds"])
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=max(380, 34 * len(top) + 120), yaxis_title=None,
                      xaxis_title=metric_label)
    with c2:
        show(fig)

    left, right = st.columns(2)
    with left:
        fig = px.scatter(fdf, x="Matches", y="Runs", size="Hundreds", color="Country",
                         hover_name="Player", color_discrete_map=COLORS,
                         hover_data=["Average", "Hundreds", "Debut_Year", "Last_Year"],
                         title="Longevity vs volume (bubble = centuries)")
        show(fig)
    with right:
        fig = px.scatter(fdf, x="Innings", y="Average", size="Runs", color="Era",
                         hover_name="Player", category_orders=ERA_CAT,
                         title="Quality vs longevity (bubble = total runs)")
        fig.add_hline(y=fdf.Average.median(), line_dash="dot", line_color="grey",
                      annotation_text=f"median {fdf.Average.median():.1f}")
        show(fig)

    st.subheader("Quick insights")
    best_avg = fdf.loc[fdf.Average.idxmax()]
    most_runs = fdf.loc[fdf.Runs.idxmax()]
    most_100 = fdf.loc[fdf.Hundreds.idxmax()]
    most_6 = fdf.loc[fdf.Sixes.idxmax()]
    top_hs = fdf.loc[fdf.High_Score.idxmax()]
    conv = fdf[fdf.Fifty_Plus >= 10].nlargest(1, "Conversion_Pct")
    st.markdown(
        f"- **Highest average:** {best_avg.Player} ({best_avg.Country}) — {best_avg.Average:.2f}\n"
        f"- **Most runs:** {most_runs.Player} — {most_runs.Runs:,} in {most_runs.Matches} Tests\n"
        f"- **Most centuries:** {most_100.Player} — {most_100.Hundreds}\n"
        f"- **Most sixes:** {most_6.Player} — {most_6.Sixes}\n"
        f"- **Highest score:** {top_hs.Player} — {top_hs.High_Score}"
        f"{'*' if top_hs.High_Score_Not_Out else ''}\n"
        + (f"- **Best 50→100 conversion (≥10 fifty-plus scores):** {conv.iloc[0].Player} — "
           f"{conv.iloc[0].Conversion_Pct:.0f}%\n" if not conv.empty else "")
    )

# =========================================================================== #
# TAB 2 — Countries & Eras
# =========================================================================== #
with tab_ctry:
    cs = country_summary(fdf)
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(cs.sort_values("Total_Runs"), x="Total_Runs", y="Country", orientation="h",
                     color="Country", color_discrete_map=COLORS, text="Total_Runs",
                     title="Total runs by country (elite batsmen only)")
        fig.update_layout(showlegend=False, yaxis_title=None)
        fig.update_traces(textposition="outside", cliponaxis=False)
        show(fig)
    with c2:
        fig = px.pie(cs, names="Country", values="Players", hole=0.45,
                     color="Country", color_discrete_map=COLORS,
                     title="Share of elite batsmen by country")
        fig.update_traces(textinfo="label+value")
        show(fig)

    c3, c4 = st.columns(2)
    with c3:
        fig = px.box(fdf, x="Country", y="Average", color="Country", points="all",
                     hover_name="Player", color_discrete_map=COLORS,
                     title="Batting-average spread by country")
        fig.update_layout(showlegend=False)
        show(fig)
    with c4:
        era_c = fdf.groupby(["Era", "Country"]).size().reset_index(name="Players")
        fig = px.bar(era_c, x="Era", y="Players", color="Country", color_discrete_map=COLORS,
                     category_orders=ERA_CAT, title="Elite batsmen by debut era and country")
        show(fig)

    c5, c6 = st.columns(2)
    with c5:
        era_s = fdf.groupby("Era").agg(Runs=("Runs", "sum"), Dis=("Dismissals", "sum"),
                                       Players=("Player", "count")).reset_index()
        era_s["Aggregate_Average"] = (era_s.Runs / era_s.Dis).round(2)
        fig = px.bar(era_s, x="Era", y="Aggregate_Average", text="Aggregate_Average",
                     category_orders=ERA_CAT, color="Aggregate_Average",
                     color_continuous_scale="Blues",
                     title="Aggregate batting average by era (runs ÷ dismissals)")
        fig.update_layout(coloraxis_showscale=False)
        show(fig)
    with c6:
        cc = fdf.groupby("Country")[["Hundreds", "Fifties"]].sum().reset_index()
        cc = cc.melt("Country", var_name="Milestone", value_name="Count")
        fig = px.bar(cc, x="Country", y="Count", color="Milestone", barmode="group",
                     title="Centuries vs half-centuries by country")
        show(fig)

    st.subheader("Career timelines")
    n_tl = pick_n("Players shown (by total runs)", min(40, len(fdf)), 25, "n_tl")
    tl = fdf.nlargest(n_tl, "Runs").sort_values("Debut_Year", ascending=False)
    fig = px.bar(tl, base="Debut_Year", x="Career_Years", y="Player", orientation="h",
                 color="Country", color_discrete_map=COLORS,
                 hover_data=["Debut_Year", "Last_Year", "Runs", "Average"],
                 title="Career spans (earliest debut at top)")
    fig.update_yaxes(categoryorder="array", categoryarray=tl["Player"].tolist(), title=None)
    fig.update_xaxes(title="Year", range=[tl.Debut_Year.min() - 2, tl.Last_Year.max() + 2])
    fig.update_layout(height=max(420, 24 * len(tl) + 150))
    show(fig)

# =========================================================================== #
# TAB 3 — Style & Strike rate
# =========================================================================== #
with tab_style:
    sdf = fdf[fdf.SR_Reliable] if reliable_sr else fdf[fdf.Strike_Rate.notna()]
    if reliable_sr:
        st.caption(f"Strike-rate charts use {len(sdf)} of {len(fdf)} players with complete "
                   "balls-faced data. Untick the sidebar option to include partial records.")

    c1, c2 = st.columns(2)
    with c1:
        if sdf.empty:
            st.info("No players with usable strike-rate data under the current filters.")
        else:
            fig = px.scatter(sdf, x="Strike_Rate", y="Average", size="Sixes", color="Country",
                             hover_name="Player", color_discrete_map=COLORS,
                             hover_data=["Runs", "Era"],
                             title="Strike rate vs average (bubble = sixes)")
            show(fig)
    with c2:
        if sdf.empty:
            st.info("No strike-rate data to plot.")
        else:
            fig = px.box(sdf, x="Era", y="Strike_Rate", color="Era", points="all",
                         category_orders=ERA_CAT, hover_name="Player",
                         title="Strike rate by era")
            fig.update_layout(showlegend=False)
            show(fig)

    c3, c4 = st.columns(2)
    with c3:
        n = min(15, len(fdf))
        tb = fdf.nlargest(n, "Runs").sort_values("Runs")
        tb = tb.assign(Non_Boundary_Runs=tb.Runs - tb.Boundary_Runs)
        fig = go.Figure()
        fig.add_bar(y=tb.Player, x=tb.Boundary_Runs, orientation="h", name="Runs from 4s & 6s",
                    marker_color="#E4572E")
        fig.add_bar(y=tb.Player, x=tb.Non_Boundary_Runs, orientation="h",
                    name="Runs run between wickets", marker_color="#76B041")
        fig.update_layout(barmode="stack", title=f"Where the runs come from — top {n} run-scorers",
                          height=max(380, 30 * n + 120), legend=dict(orientation="h", y=-0.1))
        show(fig)
    with c4:
        bp = fdf.nlargest(min(15, len(fdf)), "Boundary_Pct").sort_values("Boundary_Pct")
        fig = px.bar(bp, x="Boundary_Pct", y="Player", orientation="h", color="Country",
                     color_discrete_map=COLORS, text="Boundary_Pct",
                     title="Most boundary-dependent scoring (% of runs from 4s & 6s)")
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(yaxis_title=None, height=max(380, 30 * len(bp) + 120))
        show(fig)

    c5, c6 = st.columns(2)
    with c5:
        fig = px.scatter(fdf, x="Fours", y="Sixes", color="Era", size="Runs",
                         hover_name="Player", category_orders=ERA_CAT,
                         title="Fours vs sixes (bubble = total runs)")
        show(fig)
    with c6:
        fig = px.bar(fdf.nlargest(min(15, len(fdf)), "Sixes_per_Inns").sort_values("Sixes_per_Inns"),
                     x="Sixes_per_Inns", y="Player", orientation="h", color="Country",
                     color_discrete_map=COLORS, title="Six-hitting rate (sixes per innings)")
        fig.update_layout(yaxis_title=None)
        show(fig)

# =========================================================================== #
# TAB 4 — Player comparison
# =========================================================================== #
with tab_cmp:
    RADAR = {
        "Average": "Average", "Runs / innings": "Runs_per_Inns",
        "Hundreds / 100 inns": "Hundred_Rate_Pct", "50→100 conversion %": "Conversion_Pct",
        "Boundary % of runs": "Boundary_Pct", "Duck avoidance": "Duck_Avoidance",
        "Sixes / innings": "Sixes_per_Inns",
    }
    base = clean_df.copy()
    base["Duck_Avoidance"] = 100 - base["Duck_Pct"]
    norm = base.copy()
    for lab, col in RADAR.items():
        lo, hi = base[col].min(), base[col].max()
        norm[col] = (base[col] - lo) / (hi - lo) * 100 if hi > lo else 0.0

    default = fdf.nlargest(3, "Runs")["Player"].tolist()
    picks = st.multiselect("Choose 2–5 players (from the filtered list)",
                           fdf["Player"].tolist(), default=default, max_selections=5)
    if len(picks) < 2:
        st.info("Select at least two players to compare.")
    else:
        theta = list(RADAR.keys())
        fig = go.Figure()
        for p in picks:
            row = norm.loc[norm.Player == p].iloc[0]
            r = [float(row[c]) for c in RADAR.values()]
            fig.add_trace(go.Scatterpolar(r=r + r[:1], theta=theta + theta[:1], name=p,
                                          fill="toself", opacity=0.5))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False)),
                          title="Batting profile (each axis scaled 0–100 vs. all players in the dataset)",
                          height=520)
        c1, c2 = st.columns([3, 2])
        with c1:
            show(fig)
        with c2:
            cols = ["Country", "Debut_Year", "Last_Year", "Matches",
                    "Runs", "Average", "Hundreds", "Fifties", "High_Score", "Sixes",
                    "Boundary_Pct", "Conversion_Pct", "Duck_Pct"]
            cmp_tbl = fdf[fdf.Player.isin(picks)].set_index("Player")[cols].T
            cmp_tbl.index.name = "Metric"
            st.markdown("**Head-to-head**")
            st.dataframe(cmp_tbl.astype(str), height=470)

        metric_cmp = st.selectbox("Bar comparison metric",
                                  ["Runs", "Average", "Hundreds", "Fifties", "Sixes", "Matches",
                                   "Runs_per_Match", "Hundred_Rate_Pct", "Duck_Pct"], index=1)
        sub = fdf[fdf.Player.isin(picks)]
        fig = px.bar(sub, x="Player", y=metric_cmp, color="Player", text=metric_cmp,
                     title=f"{metric_cmp.replace('_', ' ')} — selected players")
        fig.update_layout(showlegend=False)
        show(fig)

# =========================================================================== #
# TAB 5 — Distributions & correlations
# =========================================================================== #
with tab_dist:
    num_cols = ["Matches", "Innings", "Not_Outs", "Runs", "High_Score", "Average",
                "Strike_Rate", "Hundreds", "Fifties", "Ducks", "Fours", "Sixes",
                "Career_Years", "Boundary_Pct", "Conversion_Pct", "Hundred_Rate_Pct",
                "Duck_Pct", "Runs_per_Match"]
    c1, c2 = st.columns(2)
    with c1:
        dcol = st.selectbox("Distribution of", num_cols, index=num_cols.index("Average"))
        fig = px.histogram(fdf, x=dcol, nbins=20, marginal="box", hover_name="Player",
                           color_discrete_sequence=["#1F77B4"],
                           title=f"Distribution of {dcol.replace('_', ' ')}")
        show(fig)
    with c2:
        st.markdown("**Descriptive statistics (filtered players)**")
        desc = fdf[num_cols].describe().T[["count", "mean", "std", "min", "50%", "max"]].round(2)
        desc.index.name = "Metric"
        st.dataframe(desc, height=420)

    if len(fdf) >= 3:
        corr = fdf[num_cols].corr(numeric_only=True)
        fig = px.imshow(corr, text_auto=".2f", aspect="auto", zmin=-1, zmax=1,
                        color_continuous_scale="RdBu_r", title="Correlation matrix")
        fig.update_layout(height=700)
        show(fig)
        st.caption("Strong positive links: Matches ↔ Runs ↔ Hundreds (longevity drives totals). "
                   "Average is nearly independent of career length.")
    else:
        st.info("Select at least 3 players to compute correlations.")

    st.subheader("Build your own scatter")
    e1, e2, e3, e4 = st.columns(4)
    xv = e1.selectbox("X axis", num_cols, index=num_cols.index("Matches"))
    yv = e2.selectbox("Y axis", num_cols, index=num_cols.index("Runs"))
    cv = e3.selectbox("Colour by", ["Country", "Era", "Played_ICC_XI", "Recently_Active"])
    sv = e4.selectbox("Bubble size", ["None"] + num_cols)
    plot_df = fdf.dropna(subset=[xv, yv] + ([sv] if sv != "None" else []))
    fig = px.scatter(plot_df, x=xv, y=yv, color=cv, hover_name="Player",
                     size=None if sv == "None" else sv,
                     color_discrete_map=COLORS if cv == "Country" else None,
                     category_orders=ERA_CAT if cv == "Era" else None,
                     title=f"{yv.replace('_', ' ')} vs {xv.replace('_', ' ')}")
    show(fig)

# =========================================================================== #
# TAB 6 — Data & downloads
# =========================================================================== #
with tab_data:
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇️ Cleaned CSV (filtered)", fdf.to_csv(index=False).encode("utf-8"),
                       "cricinfo_cleaned_filtered.csv", "text/csv")
    d2.download_button("⬇️ Cleaned CSV (all rows)", clean_df.to_csv(index=False).encode("utf-8"),
                       "cricinfo_cleaned.csv", "text/csv")
    d3.download_button(
        "⬇️ Excel workbook (cleaned + raw + summary + log)",
        build_excel(raw_df, clean_df, clean_log), "cricinfo_cleaned.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    t_clean, t_raw, t_log, t_dict, t_ctry = st.tabs(
        ["Cleaned data", "Raw data", "Cleaning log", "Data dictionary", "Country summary"])
    with t_clean:
        st.caption(f"{len(fdf)} rows × {fdf.shape[1]} columns (after filters)")
        table(fdf, column_config={
            "Runs": st.column_config.ProgressColumn(
                "Runs", format="%d", min_value=0, max_value=int(clean_df.Runs.max())),
            "Average": st.column_config.NumberColumn("Average", format="%.2f"),
        })
    with t_raw:
        st.caption("Exactly as exported — note the '*', '+' and '-' markers cleaned above.")
        table(raw_df)
    with t_log:
        st.caption("Every transformation and validation check applied to the raw file.")
        table(clean_log)
        problems = clean_log[(clean_log.Step == "Validation") & (clean_log.Rows_Affected > 0)]
        if problems.empty:
            st.success("All validation checks passed (0 inconsistent rows).")
        else:
            st.warning(f"{len(problems)} validation check(s) flagged rows — see the log.")
    with t_dict:
        table(data_dictionary_df())
    with t_ctry:
        table(country_summary(fdf))

st.sidebar.markdown("---")
st.sidebar.caption("Built with Streamlit + Plotly · data cleaned in `data_cleaning.py`")
