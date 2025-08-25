# main.py
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, date
import streamlit as st
from supabase import create_client, Client
import plotly.express as px

TABLE = "tasks"

ENUM_STATUS = ["No iniciado","En progreso","Bloqueado","Completado"]
ENUM_PRIORITY = ["Baja","Media","Alta","Crítica"]
ENUM_RAG = ["Verde","Amarillo","Rojo"]

FRONT_COLS = [
    "id","project_name","task","details","owner",
    "collaborators","start","end","progress",
    "status","priority","rag","milestone",
    "baseline_start","baseline_end","actual_start","actual_end",
    "phase","workstream","tags","external_link"
]

# ---------- Supabase client ----------
@st.cache_resource
def get_sb() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

# ---------- utils fechas/listas ----------
def _coerce_date(x):
    if x in (None, "", pd.NaT): return None
    if isinstance(x, (pd.Timestamp, datetime, date)): return pd.to_datetime(x).date()
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%m/%d/%Y"):
        try: return datetime.strptime(str(x), fmt).date()
        except: pass
    try: return pd.to_datetime(x).date()
    except: return None

def _to_list_from_csv(s):
    if s in (None,"",pd.NA,np.nan): return None
    if isinstance(s, list): return s
    parts = [p.strip() for p in str(s).split(",") if str(p).strip()!=""]
    return parts if parts else None

def _to_csv_from_list(lst):
    if lst in (None,pd.NA,np.nan): return ""
    if isinstance(lst, list): return ", ".join(str(x) for x in lst)
    return str(lst)

# ---------- schema ----------
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in FRONT_COLS:
        if c not in df.columns: df[c] = pd.NA

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
    df.loc[~df["rag"].isin(ENUM_RAG), "rag"] = pd.NA
    return df[FRONT_COLS]

def df_from_supabase(rows: list[dict]) -> pd.DataFrame:
    if not rows: return ensure_schema(pd.DataFrame(columns=FRONT_COLS))
    df = pd.DataFrame(rows).rename(columns={"start_date":"start","end_date":"end"})
    if "collaborators" in df.columns:
        df["collaborators"] = df["collaborators"].apply(_to_csv_from_list)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_to_csv_from_list) if isinstance(df["tags"], pd.Series) else _to_csv_from_list(df["tags"])
    return ensure_schema(df)

def payload_for_upsert(df: pd.DataFrame) -> list[dict]:
    df = ensure_schema(df)
    out = []
    for _, r in df.iterrows():
        out.append({
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
        })
    return out

# ---------- CRUD ----------
def fetch_tasks() -> pd.DataFrame:
    sb = get_sb()
    res = sb.table(TABLE).select("*").order("project_name").order("start_date").execute()
    return df_from_supabase(res.data or [])

def upsert_tasks(df: pd.DataFrame):
    sb = get_sb()
    payload = payload_for_upsert(df)
    if payload:
        sb.table(TABLE).upsert(payload, on_conflict="id").execute()

def delete_tasks(ids: list[int]):
    if not ids: return
    sb = get_sb()
    sb.table(TABLE).delete().in_("id", ids).execute()

# ---------- Gantt & ICS ----------
def make_gantt(df: pd.DataFrame, color_by: str = "progress", group_by_project: bool = True):
    if df.empty: return px.line()
    df_plot = df.dropna(subset=["start","end"]).copy()
    df_plot["progress_label"] = df_plot["progress"].astype(int).astype(str) + "%"
    df_plot["task_label"] = df_plot["task"].str.slice(0,40)
    y = "project_name" if group_by_project else "task_label"
    fig = px.timeline(
        df_plot, x_start="start", x_end="end", y=y, color=color_by,
        hover_data={"task":True,"details":True,"owner":True,"collaborators":True,
                    "status":True,"priority":True,"rag":True,
                    "progress":True,"start":"|%Y-%m-%d","end":"|%Y-%m-%d"},
        text="progress_label", title="Cronograma de Proyectos (Gantt)"
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash", opacity=0.6)
    fig.update_layout(bargap=0.2, margin=dict(l=10,r=10,t=60,b=10))
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
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
                  f"DTSTART;VALUE=DATE:{dtstart}", f"DTEND;VALUE=DATE:{dtend}",
                  f"SUMMARY:{summary}", f"DESCRIPTION:{desc}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\n".join(lines)
