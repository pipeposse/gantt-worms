# supabase_client.py
import os
from supabase import create_client, Client
import streamlit as st




# Cargar desde secrets.toml
url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]

supabase: Client = create_client(url, key)

TABLE = "tasks"

def fetch_all():
    return supabase.table(TABLE).select("*").execute().data

def insert_rows(rows: list[dict]):
    if rows:
        return supabase.table(TABLE).insert(rows).execute()

def upsert_rows(rows: list[dict]):
    if rows:
        return supabase.table(TABLE).upsert(rows).execute()

def delete_by_ids(ids: list[int]):
    if ids:
        return supabase.table(TABLE).delete().in_("id", ids).execute()
