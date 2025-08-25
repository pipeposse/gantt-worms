# main.py
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, date
import streamlit as st
from st_supabase_connection import SupabaseConnection
import plotly.express as px

# ==============================
# Config
# ==============================
TABLE = "tasks"

# Columnas que maneja la UI / editor (puede ser un superconjunto de lo que edites)
FRONT_COLS = [
    "id", "project_id", "project_name",
    "task", "details", "owner",
    "collaborators",              # UI: "Ana, Pedro"  | DB: text[]
    "baseline_start", "baseline_end",
    "start", "end",               # UI: fechas       | DB: start_date, end_date
    "actual_start", "actual_end",
    "progress", "status", "priority", "rag",
    "milestone",
    "effort_estimated", "effort_actual",
    "cost_estimated", "cost_actual",
    "blocked_by", "phase", "workstream",
    "tags",                       # UI: "dash, ventas" | DB: text[]
    "external_link",
    "created_at", "updated_at"
]

ENUM_STATUS   = ["No iniciado","En progreso","Bloqueado","Completado"]
ENUM_PRIORITY = ["Baja","Media","Alta","Crítica"]
ENUM_RAG      = ["Verde","Amarillo","Rojo"]

# ==============================
# Conexión Supabase
# ==============================
def sb_conn():
    """
    Devuelve una conexión de Streamlit al conector oficial de Supabase,
    leyendo credenciales desde .streamlit/secrets.toml
    """
    return st.connection("supabase", type=SupabaseConnection)

# ==============================
# Helpers de conversión
# ==============================
def _coerce_date(x):
    if x in (None, "", pd.NaT):
        return None
    if isinstance(x, (pd.Timestamp, datetime, date)):
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return None
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
    """
    "a, b, c" -> ["a","b","c"]
    """
    if s in (None, "", pd.NA, np.nan):
        return None
    if isinstance(s, list):
        return s if len(s) > 0 else None
    parts = [p.strip() for p in str(s).split(",") if str(p).strip() != ""]
    return parts if parts else None

def _to_csv_from_list(lst):
    """
    ["a","b"] -> "a, b"
    """
    if lst in (None, pd.NA, np.nan):
        return ""
    if isinstance(lst, list):
        return ", ".join([str(x) for x in lst])
    return str(lst)

# ==============================
# Schema & transformaciones
# ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Crear columnas faltantes
    for col in FRONT_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    # Tipos numéricos / ids
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["project_id"] = pd.to_numeric(df["project_id"], errors="coerce").astype("Int64")

    # Strings
    for c in [
        "project_name","task","details","owner","status","priority","rag",
        "blocked_by","phase","workstream","tags","external_link","collaborators"
    ]:
        df[c] = df[c].astype(str).replace({"<NA>": ""})

    # Fechas (UI)
    for c in ["baseline_start","baseline_end","start","end","actual_start","actual_end",
              "created_at","updated_at"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # Progress / booleanos / numéricos
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int).clip(0,100)
    df["milestone"] = df["milestone"].astype(str).str.lower().isin(["true","1","t","y","yes"])

    df["effort_estimated"] = pd.to_numeric(df["effort_estimated"], errors="coerce").astype("Int64")
    df["effort_actual"]    = pd.to_numeric(df["effort_actual"], errors="coerce").astype("Int64")
    df["cost_estimated"]   = pd.to_numeric(df["cost_estimated"], errors="coerce")
    df["cost_actual"]      = pd.to_numeric(df["cost_actual"], errors="coerce")

    # Enums: si vienen fuera de rango, normalizo o dejo NA
    df.loc[~df["status"].isin(ENUM_STATUS), "status"] = "No iniciado"
    df.loc[~df["priority"].isin(ENUM_PRIORITY), "priority"] = "Media"
    df.loc[~df["rag"].isin(ENUM_RAG), "rag"] = pd.NA

    # Orden de columnas
    return df[FRONT_COLS]

def df_from_supabase(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return ensure_schema(pd.DataFrame(columns=FRONT_COLS))

    df = pd.DataFrame(rows)

    # Renombrar start_date/end_date -> start/end para la UI
    df = df.rename(columns={
        "start_date": "start",
        "end_date": "end"
    })

    # Arrays -> cadena
    if "collaborators" in df.columns:
        df["collaborators"] = df["collaborators"].apply(_to_csv_from_list)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_to_csv_from_list)

    df = ensure_schema(df)
    return df

def payload_for_upsert(df: pd.DataFrame) -> list[dict]:
    """
    Convierte el DF de la UI al payload esperado por la tabla de Supabase.
    """
    df = ensure_schema(df)
    out = []
    for _, r in df.iterrows():
        item = {
            "id": int(r["id"]) if not pd.isna(r["id"]) else None,
            "project_id": int(r["project_id"]) if not pd.isna(r["project_id"]) else None,
            "project_name": (r["project_name"] or "").strip(),
            "task": (r["task"] or "").strip(),
            "details": (r["details"] or None),
            "owner": (r["owner"] or None),
            "collaborators": _to_list_from_csv(r["collaborators"]),
            "baseline_start": _coerce_date(r["baseline_start"]),
            "baseline_end": _coerce_date(r["baseline_end"]),
            "start_date": _coerce_date(r["start"]),
            "end_date": _coerce_date(r["end"]),
            "actual_start": _coerce_date(r["actual_start"]),
            "actual_end": _coerce_date(r["actual_end"]),
            "progress": int(r["progress"]) if not pd.isna(r["progress"]) else 0,
            "status": (r["status"] or "No iniciado"),
            "priority": (r["priority"] or "Media"),
            "rag": (r["rag"] if r["rag"] in ENUM_RAG else None),
            "milestone": bool(r["milestone"]),
            "effort_estimated": int(r["effort_estimated"]) if not pd.isna(r["effort_estimated"]) else None,
            "effort_actual": int(r["effort_actual"]) if not pd.isna(r["effort_actual"]) else None,
            "cost_estimated": float(r["cost_estimated"]) if not pd.isna(r["cost_estimated"]) else None,
            "cost_actual": float(r["cost_actual"]) if not pd.isna(r["cost_actual"]) else None,
            "blocked_by": (r["blocked_by"] or None),
            "phase": (r["phase"] or None),
            "workstream": (r["workstream"] or None),
            "tags": _to_list_from_csv(r["tags"]),
            "external_link": (r["external_link"] or None),
        }
        out.append(item)
    return out

# ==============================
# CRUD contra Supabase
# ==============================
def fetch_tasks() -> pd.DataFrame:
    sb = sb_conn()
    # Traigo todo; podés limitar columnas si querés
    res = sb.table(TABLE).select("*").order("project_name").order("start_date").execute()
    rows = res.data or []
    return df_from_supabase(rows)

def upsert_tasks(df: pd.DataFrame):
    """
    Upsert de todas las filas actuales del grid.
    - Si 'id' existe: UPDATE
    - Si 'id' es None: INSERT (Postgres asigna id)
    """
    payload = payload_for_upsert(df)
    if not payload:
        return
    sb = sb_conn()
    sb.table(TABLE).upsert(payload, on_conflict="id").execute()

def delete_tasks(ids: list[int]):
    if not ids:
        return
    sb = sb_conn()
    sb.table(TABLE).delete().in_("id", ids).execute()

# ==============================
# Gantt (Plotly) & Export ICS
# ==============================
def make_gantt(df: pd.DataFrame, color_by: str = "progress", group_by_project: bool = True):
    if df.empty:
        return px.line()

    df_plot = df.dropna(subset=["start","end"]).copy()
    if df_plot.empty:
        return px.line()

    # Etiquetas
    df_plot["progress_label"] = df_plot["progress"].astype(int).astype(str) + "%"
    df_plot["task_label"] = df_plot["task"].str.slice(0, 40)

    # Eje Y
    y = "project_name" if group_by_project else "task_label"

    fig = px.timeline(
        df_plot,
        x_start="start", x_end="end", y=y,
        color=color_by,
        hover_data={
            "task": True, "details": True, "owner": True, "collaborators": True,
            "status": True, "priority": True, "rag": True,
            "progress": True, "start": "|%Y-%m-%d", "end": "|%Y-%m-%d",
        },
        text="progress_label",
        title="Cronograma de Proyectos (Gantt)",
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash", opacity=0.6)
    fig.update_layout(bargap=0.2, margin=dict(l=10, r=10, t=60, b=10), legend_title_text=color_by.capitalize())
    return fig

def to_ics(df: pd.DataFrame, cal_name: str = "Proyectos"):
    df = df.dropna(subset=["start","end"]).copy()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"X-WR-CALNAME:{cal_name}",
        "PRODID:-//Streamlit Gantt//ES",
    ]
    now = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for _, row in df.iterrows():
        uid = f"{row.get('id','x')}@streamlit-gantt"
        dtstart = pd.Timestamp(row["start"]).strftime("%Y%m%d")
        # DTEND no inclusivo -> +1 día
        dtend = (pd.Timestamp(row["end"]) + pd.Timedelta(days=1)).strftime("%Y%m%d")
        summary = f"{row['project_name']} – {row['task']} ({int(row['progress'])}%)"
        desc = f"Owner: {row.get('owner','')}. Estado: {row.get('status','')}."
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\n".join(lines)
