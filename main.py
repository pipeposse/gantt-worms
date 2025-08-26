# main.py
from __future__ import annotations
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client, Client
import plotly.express as px

# Tu DB tiene collaborators/tags como ARRAY => usamos listas Python
DB_ARRAY_COLS = True
TABLE = "tasks"

ENUM_STATUS = ["No iniciado", "En progreso", "Bloqueado", "Completado"]
ENUM_PRIORITY = ["Baja", "Media", "Alta", "Crítica"]
ENUM_RAG = ["Verde", "Amarillo", "Rojo"]

FRONT_COLS = [
    "id", "project_name", "task", "details", "owner",
    "collaborators", "start", "end", "progress",
    "status", "priority", "rag", "milestone",
    "baseline_start", "baseline_end", "actual_start", "actual_end",
    "phase", "workstream", "tags", "external_link"
]

# ----------------- Supabase -----------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")

@st.cache_resource
def get_sb() -> Optional[Client]:
    try:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return None
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        return None

def supabase_ready() -> bool:
    return get_sb() is not None

# ----------------- Utils -----------------
def _coerce_date(x: Any) -> Optional[date]:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
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

def _date_to_str(d: Any) -> Optional[str]:
    """'YYYY-MM-DD' o None (JSON-safe)."""
    if d is None:
        return None
    try:
        if pd.isna(d):
            return None
    except Exception:
        pass
    if isinstance(d, pd.Timestamp):
        d = d.date()
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.isoformat()
    s = str(d).strip()
    return s if s else None

def _to_list_from_csv(s: Any) -> Optional[List[str]]:
    # None / NA
    if s is None:
        return None
    try:
        if pd.isna(s):
            return None
    except Exception:
        pass
    # Lista ya válida
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip() != ""]
    # Cadena "a, b"
    s_str = str(s).strip()
    if s_str == "" or s_str.lower() in ("nan", "none", "<na>"):
        return None
    return [p.strip() for p in s_str.split(",") if p.strip() != ""]

def _to_csv_from_list(lst: Any) -> str:
    if lst is None:
        return ""
    try:
        if pd.isna(lst):
            return ""
    except Exception:
        pass
    if isinstance(lst, list):
        return ", ".join(str(x).strip() for x in lst if str(x).strip() != "")
    s = str(lst).strip()
    return "" if s.lower() in ("nan", "none", "<na>") else s

def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None or pd.isna(v):
            return None
    except Exception:
        if v is None:
            return None
    if isinstance(v, (np.integer,)):
        return int(v)
    try:
        return int(v)
    except Exception:
        return None

def _to_bool(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return bool(v)

# ----------------- Schema & transforms -----------------
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in FRONT_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")

    text_like = [
        "project_name", "task", "details", "owner",
        "status", "priority", "rag", "phase",
        "workstream", "tags", "external_link", "collaborators"
    ]
    for c in text_like:
        df[c] = df[c].astype("object")
        df[c] = df[c].where(~pd.isna(df[c]), None)

    for c in ["start", "end", "baseline_start", "baseline_end", "actual_start", "actual_end"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int).clip(0, 100)
    df["milestone"] = df["milestone"].apply(lambda v: False if v is None or (isinstance(v, float) and pd.isna(v)) else bool(v))

    mask_status_bad = df["status"].isna() | ~df["status"].isin(ENUM_STATUS)
    df.loc[mask_status_bad, "status"] = "No iniciado"

    mask_prio_bad = df["priority"].isna() | ~df["priority"].isin(ENUM_PRIORITY)
    df.loc[mask_prio_bad, "priority"] = "Media"

    df.loc[~df["rag"].isin(ENUM_RAG) & ~df["rag"].isna(), "rag"] = None

    return df[FRONT_COLS]

def df_from_supabase(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return ensure_schema(pd.DataFrame(columns=FRONT_COLS))
    df = pd.DataFrame(rows).rename(columns={"start_date": "start", "end_date": "end"})
    # Para la UI mostramos CSV; la DB guarda arrays reales
    if "collaborators" in df.columns:
        df["collaborators"] = df["collaborators"].apply(_to_csv_from_list)
    if "tags" in df.columns:
        if isinstance(df["tags"], pd.Series):
            df["tags"] = df["tags"].apply(_to_csv_from_list)
        else:
            df["tags"] = _to_csv_from_list(df["tags"])
    return ensure_schema(df)

def payload_for_upsert(df: pd.DataFrame) -> List[Dict[str, Any]]:
    df = ensure_schema(df)
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        # Armamos SIN 'id'; lo agregamos solo si viene con valor (evita "id": null)
        item: Dict[str, Any] = {
            "project_name": (r["project_name"] or "").strip(),
            "task": (r["task"] or "").strip(),
            "details": (r["details"] or None),
            "owner": (r["owner"] or None),
            "collaborators": _to_list_from_csv(r["collaborators"]) if DB_ARRAY_COLS else _to_csv_from_list(r["collaborators"]),
            "start_date": _date_to_str(_coerce_date(r["start"])),
            "end_date": _date_to_str(_coerce_date(r["end"])),
            "progress": _to_int(r["progress"]) or 0,
            "status": (r["status"] or "No iniciado"),
            "priority": (r["priority"] or "Media"),
            "rag": (r["rag"] if r["rag"] in ENUM_RAG else None),
            "milestone": _to_bool(r["milestone"]),
            "baseline_start": _date_to_str(_coerce_date(r["baseline_start"])),
            "baseline_end": _date_to_str(_coerce_date(r["baseline_end"])),
            "actual_start": _date_to_str(_coerce_date(r["actual_start"])),
            "actual_end": _date_to_str(_coerce_date(r["actual_end"])),
            "phase": (r["phase"] or None),
            "workstream": (r["workstream"] or None),
            "tags": _to_list_from_csv(r["tags"]) if DB_ARRAY_COLS else _to_csv_from_list(r["tags"]),
            "external_link": (r["external_link"] or None),
        }

        # id solo si existe
        id_val = _to_int(r["id"])
        if id_val is not None:
            item["id"] = id_val

        # Forzar listas reales si por UI vino string (defensa extra)
        if DB_ARRAY_COLS:
            for k in ("collaborators", "tags"):
                v = item.get(k)
                if isinstance(v, str):
                    item[k] = _to_list_from_csv(v)

        out.append(item)
    return out

# ----------------- CRUD -----------------
def fetch_tasks() -> pd.DataFrame:
    sb = get_sb()
    if sb is None:
        demo = pd.DataFrame([
            {"id": 1, "project_name": "Demo", "task": "Tarea 1", "status": "No iniciado", "priority": "Media", "progress": 0},
            {"id": 2, "project_name": "Demo", "task": "Tarea 2", "status": "En Progreso", "priority": "Alta", "progress": 50},
        ])
        return ensure_schema(demo)
    res = sb.table(TABLE).select("*").order("project_name").order("start_date").execute()
    return df_from_supabase(res.data or [])

try:
    from postgrest.exceptions import APIError  # type: ignore
except Exception:  # pragma: no cover
    class APIError(Exception):
        pass

def upsert_tasks(df: pd.DataFrame) -> bool:
    sb = get_sb()
    if sb is None:
        st.warning("Sin conexión a Supabase: cambios NO persistidos (demo).")
        return False
    payload = payload_for_upsert(df)
    if not payload:
        return True
    try:
        sb.table(TABLE).upsert(payload, on_conflict="id").execute()
        return True
    except APIError as e:
        st.error("❌ Error de Supabase al guardar")
        st.code({
            "code": getattr(e, "code", None),
            "message": getattr(e, "message", None),
            "details": getattr(e, "details", None),
            "hint": getattr(e, "hint", None),
            "payload_sample": payload[:1],
        })
        return False

def delete_tasks(ids: List[int]) -> bool:
    if not ids:
        return True
    sb = get_sb()
    if sb is None:
        st.warning("Sin conexión a Supabase: borrado NO persistido (demo).")
        return False
    try:
        sb.table(TABLE).delete().in_("id", ids).execute()
        return True
    except APIError as e:
        st.error("❌ Error de Supabase al borrar")
        st.code({
            "code": getattr(e, "code", None),
            "message": getattr(e, "message", None),
            "details": getattr(e, "details", None),
            "hint": getattr(e, "hint", None),
        })
        return False

# ----------------- Visual (opcional) -----------------
def make_gantt(df: pd.DataFrame, color_by: str = "progress", group_by_project: bool = True):
    if df.empty:
        return px.line().update_layout(template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    df_plot = df.dropna(subset=["start", "end"]).copy()
    if df_plot.empty:
        return px.line().update_layout(template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    df_plot["progress_label"] = df_plot["progress"].astype(int).astype(str) + "%"
    df_plot["task_label"] = df_plot["task"].astype(str).str.slice(0, 40)
    y = "project_name" if group_by_project else "task_label"
    fig = px.timeline(
        df_plot,
        x_start="start", x_end="end", y=y, color=color_by,
        hover_data={"task": True, "details": True, "owner": True, "collaborators": True,
                    "status": True, "priority": True, "rag": True,
                    "progress": True, "start": "|%Y-%m-%d", "end": "|%Y-%m-%d"},
        text="progress_label",
        title="Cronograma de Proyectos (Gantt)",
        template="plotly_white",
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        bargap=0.2,
        margin=dict(l=10, r=10, t=60, b=10),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        height=520,
    )
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash", opacity=0.6)
    return fig
