# main.py
from __future__ import annotations
import os
import pandas as pd
import streamlit as st

# ---------- Credenciales ----------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY"))

def _have_secrets() -> bool:
    return bool(SUPABASE_URL) and bool(SUPABASE_ANON_KEY)

# ---------- Cliente Supabase (carga perezosa y tolerante) ----------
def _get_sb():
    """Devuelve cliente Supabase o None si no hay credenciales o si falla el import."""
    if not _have_secrets():
        return None
    try:
        # Import diferido: si la lib no está, no rompe el import del módulo
        from supabase import create_client, Client  # type: ignore
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        return None

# ---------- Datos de ejemplo como fallback ----------
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": 1, "project_name": "Demo", "task": "Tarea 1", "status": "No iniciado"},
            {"id": 2, "project_name": "Demo", "task": "Tarea 2", "status": "En progreso"},
            {"id": 3, "project_name": "Demo", "task": "Tarea 3", "status": "Completado"},
        ]
    )

# ---------- API sencilla ----------
def fetch_head(table: str, limit: int = 5) -> tuple[pd.DataFrame, dict]:
    """
    Intenta leer las primeras `limit` filas de `table` desde Supabase.
    Si no hay conexión o hay error, devuelve datos de ejemplo y un dict con info de estado.
    """
    meta = {
        "secrets_present": _have_secrets(),
        "used_supabase": False,
        "error": None,
    }
    sb = _get_sb()
    if sb is None:
        meta["error"] = "Sin cliente Supabase (faltan secrets o fallo el import)."
        return sample_df().head(limit), meta

    try:
        res = sb.table(table).select("*").limit(limit).execute()
        data = res.data or []
        meta["used_supabase"] = True
        return pd.DataFrame(data), meta
    except Exception as e:
        meta["error"] = str(e)
        return sample_df().head(limit), meta
