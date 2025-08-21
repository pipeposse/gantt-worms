# main.py
from __future__ import annotations
import io
from dataclasses import dataclass
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, date
from pathlib import Path

DATE_FMT = "%Y-%m-%d"

COLUMNS = [
    "id", "project", "task", "details", "collaborators",
    "start", "end", "progress", "status", "priority"
]

STATUSES = ["Planned", "In Progress", "Blocked", "Done"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]

def _coerce_date(x):
    if pd.isna(x) or x == "":
        return pd.NaT
    if isinstance(x, (pd.Timestamp, datetime, date)):
        return pd.to_datetime(x)
    # try common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return pd.to_datetime(datetime.strptime(str(x), fmt))
        except Exception:
            pass
    # last resort
    return pd.to_datetime(x, errors="coerce")

def sample_data() -> pd.DataFrame:
    today = pd.Timestamp.today().normalize()
    data = [
        [1, "Encuesta Clima ACE", "Diseño cuestionario", "Versión 1 + validación",
         "Felipe, Carla", today - pd.Timedelta(days=7), today + pd.Timedelta(days=2), 75, "In Progress", "High"],
        [2, "Encuesta Clima ACE", "Limpieza de datos", "Detectar y tratar nulos",
         "Felipe", today + pd.Timedelta(days=3), today + pd.Timedelta(days=8), 10, "Planned", "Medium"],
        [3, "Portal BI Ventas", "Definir permisos", "Mapa RLS por área",
         "Gise", today - pd.Timedelta(days=2), today + pd.Timedelta(days=10), 30, "In Progress", "High"],
        [4, "Portal BI Ventas", "Dashboard margen", "Márgenes por BU, semanales",
         "Felipe", today + pd.Timedelta(days=1), today + pd.Timedelta(days=14), 0, "Planned", "High"],
        [5, "CDF Finanzas", "Arqueo ODC/ODV", "Conciliar contra pagos/recibos",
         "Nico V., Fer T.", today - pd.Timedelta(days=10), today - pd.Timedelta(days=1), 100, "Done", "Critical"],
        [6, "RRHH", "Formulario consultas", "Google Forms -> tablero",
         "Felipe", today - pd.Timedelta(days=1), today + pd.Timedelta(days=6), 45, "In Progress", "Medium"],
    ]
    df = pd.DataFrame(data, columns=COLUMNS)
    # ensure dtypes
    df["start"] = df["start"].apply(_coerce_date)
    df["end"] = df["end"].apply(_coerce_date)
    df["progress"] = df["progress"].astype(int)
    return df

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Make sure columns exist with correct order & basic coercions."""
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    # coerce types
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["project"] = df["project"].astype(str)
    df["task"] = df["task"].astype(str)
    df["details"] = df["details"].astype(str)
    df["collaborators"] = df["collaborators"].astype(str)
    df["start"] = df["start"].apply(_coerce_date)
    df["end"] = df["end"].apply(_coerce_date)
    df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int).clip(0,100)
    df["status"] = df["status"].replace({np.nan:"Planned"}).astype(str)
    df["priority"] = df["priority"].replace({np.nan:"Medium"}).astype(str)

    # sort columns
    df = df[COLUMNS]
    return df

def validate(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate and gently fix issues. Returns (df, warnings)."""
    df = ensure_schema(df)
    warnings = []
    # auto-fill missing ids
    if df["id"].isna().any():
        max_id = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int).max() if len(df) else 0
        for idx in df.index:
            if pd.isna(df.at[idx, "id"]):
                max_id += 1
                df.at[idx, "id"] = max_id
        warnings.append("Se autocompletaron IDs faltantes.")
    # start <= end
    mask_bad = (df["start"].notna() & df["end"].notna() & (df["start"] > df["end"]))
    if mask_bad.any():
        swapped = mask_bad.sum()
        df.loc[mask_bad, ["start","end"]] = df.loc[mask_bad, ["end","start"]].values
        warnings.append(f"{swapped} fila(s) tenían start > end y se invirtieron.")
    # clamp progress
    if (df["progress"].lt(0) | df["progress"].gt(100)).any():
        df["progress"] = df["progress"].clip(0,100)
        warnings.append("Se ajustó progress a [0,100].")
    return df, warnings

def filter_df(
    df: pd.DataFrame,
    projects: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    priorities: Optional[List[str]] = None,
    collaborator_substr: Optional[str] = None,
    start_after: Optional[pd.Timestamp] = None,
    end_before: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    out = df.copy()
    if projects:
        out = out[out["project"].isin(projects)]
    if statuses:
        out = out[out["status"].isin(statuses)]
    if priorities:
        out = out[out["priority"].isin(priorities)]
    if collaborator_substr:
        s = collaborator_substr.lower()
        out = out[out["collaborators"].str.lower().str.contains(s, na=False)]
    if start_after:
        out = out[(out["end"].isna()) | (out["end"] >= start_after)]
    if end_before:
        out = out[(out["start"].isna()) | (out["start"] <= end_before)]
    return out

def make_gantt(df: pd.DataFrame, color_by: str = "progress", group_by_project: bool = True):
    df_plot = df.copy()
    df_plot = df_plot.dropna(subset=["start","end"])
    if df_plot.empty:
        return px.line()  # empty fig
    df_plot["progress_label"] = df_plot["progress"].astype(int).astype(str) + "%"
    df_plot["task_label"] = df_plot["task"].str.slice(0, 40)
    y = "task_label" if not group_by_project else "project"
    fig = px.timeline(
        df_plot,
        x_start="start",
        x_end="end",
        y=y,
        color=color_by,
        hover_data={
            "task": True,
            "details": True,
            "collaborators": True,
            "status": True,
            "priority": True,
            "progress": True,
            "start": "|%Y-%m-%d",
            "end": "|%Y-%m-%d",
        },
        text="progress_label",
        title="Cronograma de Proyectos (Gantt)",
        color_discrete_sequence=None,  # let plotly pick
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed")  # Gantt style
    # "Hoy" vertical line
    today = pd.Timestamp.today().normalize()
    fig.add_vline(x=today, line_width=2, line_dash="dash", opacity=0.6)
    fig.update_layout(
        bargap=0.2,
        margin=dict(l=10, r=10, t=60, b=10),
        legend_title_text=color_by.capitalize(),
    )
    return fig

def to_ics(df: pd.DataFrame, cal_name: str = "Proyectos"):
    """Export tasks as a minimal .ics calendar text (events spanning start..end)."""
    df = df.dropna(subset=["start","end"]).copy()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"X-WR-CALNAME:{cal_name}",
        "PRODID:-//Streamlit Gantt//ES",
    ]
    now = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for _, row in df.iterrows():
        uid = f"{row['id']}@streamlit-gantt"
        dtstart = pd.Timestamp(row["start"]).strftime("%Y%m%d")
        # ICS DTEND is non-inclusive -> add 1 day
        dtend = (pd.Timestamp(row["end"]) + pd.Timedelta(days=1)).strftime("%Y%m%d")
        summary = f"{row['project']} – {row['task']} ({int(row['progress'])}%)"
        desc = f"Colaboradores: {row.get('collaborators','')}. Estado: {row.get('status','')}."
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

def load_csv(file_like) -> pd.DataFrame:
    df = pd.read_csv(file_like)
    return ensure_schema(df)

def save_csv(df: pd.DataFrame, path: str | Path):
    df.to_csv(path, index=False)

def template_csv() -> bytes:
    df = ensure_schema(sample_data().iloc[0:0])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
