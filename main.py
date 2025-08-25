# main.py
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, date
import plotly.express as px
import streamlit as st

import supabase_client as sbc  # cliente centralizado

# =========================
# Config
# =========================
FRONT_COLS = [
    "id", "project_name", "task", "details", "owner",
    "collaborators",  # coma-separado en UI; en DB es text[]
    "start", "end",   # mapean a start_date, end_date
    "progress", "status", "priority",
    "rag", "milestone",
    "baseline_start", "baseline_end",
    "actual_start", "actual_end",
    "phase", "workstream", "tags", "external_link",
]

ENUM_STATUS   = ["No iniciado", "En progreso", "Bloqueado", "Completado"]
ENUM_PRIORITY = ["Baja", "Media", "Alta", "Crítica"]
ENUM_RAG      = ["Verde", "Amarillo", "Rojo"]

# =========================
# Utilidades
# =========================
def _coerce_date(x):
    if x in (None, "", pd.NaT):
        return None
    if isinstance(x, (pd.Timestamp, datetime, date)):
        return pd.to_datetime(x).date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(x), fmt).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def _to_list_from_csv(s):
    if s in (None, "", pd.NA, np.nan):
        return None
    if isinstance(s, list):
        return s
    parts = [p.strip() for p in str(s).split(",") if str(p).strip()]
    return parts if parts else None

def _to_csv_from_list(lst):
    if lst in (None, pd.NA, np.nan):
        return ""
    if isinstance(lst, list):
        return ", ".join([str(x) for x in lst])
    return str(lst)

# =========================
# Transformaciones DF <-> DB
# =========================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in FRONT_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")

    for c in ["project_name","task","details","owner","status","priority","rag",
              "phase","workstream","tags","external_link","collaborators"]:
        df[c] = df[c].astype(str).replace({"<NA>": ""})

    for c in ["start","end","baseline_start","baseline_end","actual_start","actual_end"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int).clip(0,100)
    df["milestone"] = df["milestone"].astype(str).str.lower().isin(["true","1","t","y","yes"])

    df.loc[~df["status"].isin(ENUM_STATUS), "status"] = "No iniciado"
    df.loc[~df["priority"].isin(ENUM_PRIORITY), "priority"] = "Media"
    df.loc[~df["rag"].isin(ENUM_RAG), "rag"] = ""
    return df[FRONT_COLS]

def df_from_supabase(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return ensure_schema(pd.DataFrame(columns=FRONT_COLS))
    df = pd.DataFrame(rows).copy()
    df = df.rename(columns={"start_date": "start", "end_date": "end"})
    if "collaborators" in df.columns:
        df["collaborators"] = df["collaborators"].apply(_to_csv_from_list)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_to_csv_from_list)
    df = ensure_schema(df)
    return df

def payload_for_upsert(df: pd.DataFrame) -> list[dict]:
    df = ensure_schema(df)
    out = []
    for _, r in df.iterrows():
        item = {
            "id": int(r["id"]) if not pd.isna(r["id"]) else None,
            "project_name": (r["project_name"] or "").strip(),
            "task": (r["task"] or "").strip(),
            "details": (r["details"] or None),
            "owner": (r["owner"] or None),
            "collaborators": _to_list_from_csv(r["collaborators"]),
            "start_date": _coerce_date(r["start"]),
            "end_date": _coerce_date(r["end"]),
            "progress": int(r["progress"]) if not pd.isna(r["progress"]) else 0,
            "status": (r["status"] or "No iniciado"),
            "priority": (r["priority"] or "Media"),
            "rag": (r["rag"] if r["rag"] in ENUM_RAG else None),
            "milestone": bool(r["milestone"]),
            "baseline_start": _coerce_date(r["baseline_start"]),
            "baseline_end": _coerce_date(r["baseline_end"]),
            "actual_start": _coerce_date(r["actual_start"]),
            "actual_end": _coerce_date(r["actual_end"]),
            "phase": (r["phase"] or None),
            "workstream": (r["workstream"] or None),
            "tags": _to_list_from_csv(r["tags"]),
            "external_link": (r["external_link"] or None),
        }
        out.append(item)
    return out

# =========================
# CRUD vía supabase_client
# =========================
def fetch_tasks() -> pd.DataFrame:
    rows = sbc.fetch_all()
    return df_from_supabase(rows)

def upsert_tasks(df: pd.DataFrame):
    payload = payload_for_upsert(df)
    if payload:
        sbc.upsert_rows(payload)

def delete_tasks(ids: list[int]):
    if ids:
        sbc.delete_by_ids(ids)

# =========================
# UX: KPIs y Gantt
# =========================
def kpi_counts(df: pd.DataFrame):
    total = len(df)
    in_prog = (df["status"] == "En progreso").sum()
    done = (df["status"] == "Completado").sum()
    today = pd.Timestamp.today().normalize()
    overdue = ((df["end"].notna()) & (df["end"] < today) & (df["progress"] < 100)).sum()
    return total, in_prog, done, overdue

def make_gantt(df: pd.DataFrame, color_by: str = "progress", group_by_project: bool = True):
    if df.empty:
        return px.line()
    df_plot = df.dropna(subset=["start","end"]).copy()
    if df_plot.empty:
        return px.line()
    df_plot["progress_label"] = df_plot["progress"].astype(int).astype(str) + "%"
    df_plot["task_label"] = df_plot["task"].str.slice(0, 40)
    y = "project_name" if group_by_project else "task_label"
    fig = px.timeline(
        df_plot,
        x_start="start", x_end="end", y=y,
        color=color_by,
        hover_data={
            "task": True, "details": True, "owner": True, "collaborators": True,
            "status": True, "priority": True, "rag": True,
            "progress": True, "start": "|%Y-%m-%d", "end": "|%Y-%m-%d",
            "external_link": True,
        },
        text="progress_label",
        title="Cronograma de Proyectos (Gantt)",
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash", opacity=0.6)
    fig.update_layout(bargap=0.25, margin=dict(l=10, r=10, t=60, b=10), legend_title_text=color_by.capitalize())
    return fig

def to_ics(df: pd.DataFrame, cal_name: str = "Proyectos"):
    df = df.dropna(subset=["start","end"]).copy()
    lines = ["BEGIN:VCALENDAR","VERSION:2.0",f"X-WR-CALNAME:{cal_name}","PRODID:-//Streamlit Gantt//ES"]
    now = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for _, row in df.iterrows():
        uid = f"{row.get('id','x')}@streamlit-gantt"
        dtstart = pd.Timestamp(row["start"]).strftime("%Y%m%d")
        dtend = (pd.Timestamp(row["end"]) + pd.Timedelta(days=1)).strftime("%Y%m%d")
        summary = f"{row['project_name']} – {row['task']} ({int(row['progress'])}%)"
        desc = f"Owner: {row.get('owner','')}. Estado: {row.get('status','')}."
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dtstart}", f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}", f"DESCRIPTION:{desc}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\n".join(lines)
