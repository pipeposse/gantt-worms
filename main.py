Acá tenés el **`main.py` actualizado** (parcheado para el error de `pd.NA` y con CRUD + Gantt). Pega tal cual:

```python
# main.py
from __future__ import annotations
import os
from datetime import datetime, date
import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client, Client
import plotly.express as px

# ----------------- Config -----------------
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
def get_sb() -> Client | None:
    try:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return None
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        return None

def supabase_ready() -> bool:
    return get_sb() is not None

# ----------------- Utils -----------------
def _coerce_date(x):
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

def _to_list_from_csv(s):
    """
    "a, b, c" -> ["a","b","c"]
    Maneja None / pd.NA / np.nan y listas ya válidas.
    """
    if s is None:
        return None
    try:
        if pd.isna(s):
            return None
    except Exception:
        pass
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip() != ""]
    s = str(s).strip()
    if s == "" or s.lower() in ("nan", "none", "<na>"):
        return None
    return [p.strip() for p in s.split(",") if p.strip() != ""]

def _to_csv_from_list(lst):
    """
    Lista -> "a, b, c" para mostrar en la UI.
    """
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

# ----------------- Schema & transforms -----------------
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in FRONT_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    # tipos
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")

    # columnas tipo texto: mantener como object y pasar NA -> None
    text_like = [
        "project_name", "task", "details", "owner",
        "status", "priority", "rag", "phase",
        "workstream", "tags", "external_link", "collaborators"
    ]
    for c in text_like:
        df[c] = df[c].astype("object")
        df[c] = df[c].where(~pd.isna(df[c]), None)

    # fechas
    for c in ["start", "end", "baseline_start", "baseline_end", "actual_start", "actual_end"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # numéricos / booleanos
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int).clip(0, 100)
    df["milestone"] = df["milestone"].apply(lambda v: False if v is None or (isinstance(v, float) and pd.isna(v)) else bool(v))

    # enums (aplicar default si viene vacío/incorrecto)
    mask_status_bad = df["status"].isna() | ~df["status"].isin(ENUM_STATUS)
    df.loc[mask_status_bad, "status"] = "No iniciado"

    mask_prio_bad = df["priority"].isna() | ~df["priority"].isin(ENUM_PRIORITY)
    df.loc[mask_prio_bad, "priority"] = "Media"

    # RAG puede ser None; si viene texto inválido, limpiar a None
    df.loc[~df["rag"].isin(ENUM_RAG) & ~df["rag"].isna(), "rag"] = None

    return df[FRONT_COLS]

def df_from_supabase(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return ensure_schema(pd.DataFrame(columns=FRONT_COLS))
    df = pd.DataFrame(rows).rename(columns={"start_date": "start", "end_date": "end"})
    # arrays -> csv string para UI
    if "collaborators" in df.columns:
        df["collaborators"] = df["collaborators"].apply(_to_csv_from_list)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_to_csv_from_list) if isinstance(df["tags"], pd.Series) else _to_csv_from_list(df["tags"])
    return ensure_schema(df)

def payload_for_upsert(df: pd.DataFrame) -> list[dict]:
    df = ensure_schema(df)
    out: list[dict] = []
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

# ----------------- CRUD -----------------
def fetch_tasks() -> pd.DataFrame:
    sb = get_sb()
    if sb is None:
        # Fallback demo
        demo = pd.DataFrame([
            {"id": 1, "project_name": "Demo", "task": "Tarea 1", "status": "No iniciado", "priority": "Media", "progress": 0},
            {"id": 2, "project_name": "Demo", "task": "Tarea 2", "status": "En progreso", "priority": "Alta", "progress": 50},
        ])
        # garantizar columnas
        return ensure_schema(demo)
    res = sb.table(TABLE).select("*").order("project_name").order("start_date").execute()
    return df_from_supabase(res.data or [])

def upsert_tasks(df: pd.DataFrame):
    sb = get_sb()
    if sb is None:
        st.warning("Sin conexión a Supabase: cambios NO persistidos (demo).")
        return
    payload = payload_for_upsert(df)
    if payload:
        sb.table(TABLE).upsert(payload, on_conflict="id").execute()

def delete_tasks(ids: list[int]):
    if not ids:
        return
    sb = get_sb()
    if sb is None:
        st.warning("Sin conexión a Supabase: borrado NO persistido (demo).")
        return
    sb.table(TABLE).delete().in_("id", ids).execute()

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
```
