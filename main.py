# main.py
import streamlit as st
import pandas as pd
import supabase_client as sbc
import plotly.express as px
from datetime import datetime, date

# Enums
ENUM_STATUS   = ["No iniciado", "En progreso", "Bloqueado", "Completado"]
ENUM_PRIORITY = ["Baja", "Media", "Alta", "Crítica"]
ENUM_RAG      = ["Verde", "Amarillo", "Rojo"]

# =========================
# Conexión
# =========================
def check_connection():
    try:
        rows = sbc.fetch_all()
        return True, rows
    except Exception as e:
        return False, str(e)

# =========================
# Transformaciones
# =========================
def df_from_supabase(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def payload_for_upsert(df: pd.DataFrame) -> list[dict]:
    return df.to_dict(orient="records")

# =========================
# KPIs
# =========================
def kpi_counts(df: pd.DataFrame):
    total = len(df)
    in_prog = (df["status"] == "En progreso").sum() if "status" in df else 0
    done = (df["status"] == "Completado").sum() if "status" in df else 0
    overdue = 0
    if "end_date" in df.columns and "progress" in df.columns:
        today = pd.Timestamp.today().normalize()
        overdue = ((df["end_date"].notna()) & (df["end_date"] < today) & (df["progress"] < 100)).sum()
    return total, in_prog, done, overdue

# =========================
# Gantt
# =========================
def make_gantt(df: pd.DataFrame):
    if df.empty or not {"start_date","end_date"}.issubset(df.columns):
        return px.line()
    df_plot = df.dropna(subset=["start_date","end_date"]).copy()
    df_plot["progress_label"] = df_plot["progress"].astype(str) + "%"
    fig = px.timeline(
        df_plot,
        x_start="start_date", x_end="end_date",
        y="project_name", color="status",
        text="progress_label",
        hover_data=df_plot.columns
    )
    fig.update_yaxes(autorange="reversed")
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash")
    return fig
