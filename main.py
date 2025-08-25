# main.py
from __future__ import annotations
import os
import pandas as pd

# Streamlit solo para leer secrets y cachear el cliente
import streamlit as st
from supabase import create_client, Client

# Lee credenciales desde Streamlit Secrets o variables de entorno
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY"))

@st.cache_resource
def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError(
            "Faltan credenciales: configurá SUPABASE_URL y SUPABASE_ANON_KEY "
            "en Streamlit Secrets (o variables de entorno)."
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def fetch_head(table: str, limit: int = 5) -> pd.DataFrame:
    """
    Devuelve los primeros `limit` registros de `table` como DataFrame.
    No transforma tipos: es una lectura cruda, simple y robusta.
    """
    sb = get_client()
    res = sb.table(table).select("*").limit(limit).execute()
    data = res.data or []
    return pd.DataFrame(data)
