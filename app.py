# app.py
import streamlit as st
import pandas as pd
import main

st.set_page_config(page_title="Head de Supabase", layout="wide", page_icon="🔎")

st.title("🔎 Ver head de una tabla (Supabase)")
st.caption("App minimal: conecta a Supabase y muestra los primeros registros de la tabla que elijas.")

with st.sidebar:
    st.subheader("Configuración")
    table = st.text_input("Nombre de la tabla", value="tasks")
    limit = st.number_input("Filas (head)", min_value=1, max_value=1000, value=5, step=1)
    run = st.button("Cargar", use_container_width=True)

# Auto-run al abrir, o al tocar "Cargar"
if run or "auto_ran" not in st.session_state:
    st.session_state["auto_ran"] = True
    try:
        df = main.fetch_head(table, int(limit))
        if df.empty:
            st.info(f"La tabla **{table}** no tiene filas o no devolvió datos.")
        else:
            st.subheader(f"Head de `{table}` (primeras {limit} filas)")
            st.dataframe(df, use_container_width=True)
            with st.expander("Ver JSON crudo"):
                st.write(df.to_dict(orient="records"))
    except Exception as e:
        st.error("No se pudo leer la tabla. Revisá el nombre, permisos o secrets.")
        st.exception(e)

st.markdown("---")
st.caption("Consejos: asegurate de tener SUPABASE_URL y SUPABASE_ANON_KEY en Secrets. "
           "Si la tabla tiene RLS, configurá políticas para permitir `select`.")
