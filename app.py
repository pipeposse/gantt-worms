# app.py
import streamlit as st
import pandas as pd
import main

st.set_page_config(page_title="Head de tabla (Supabase mínimo)", layout="wide", page_icon="🔎")

st.title("🔎 Head de una tabla en Supabase (versión mínima)")

with st.sidebar:
    st.subheader("Configuración")
    table = st.text_input("Nombre de la tabla", value="tasks")
    limit = st.number_input("Filas (head)", min_value=1, max_value=1000, value=5, step=1)
    st.caption("Configura SUPABASE_URL y SUPABASE_ANON_KEY en Secrets.")

# Ejecutamos SIEMPRE (sin botón) para que haya algo en pantalla
df, meta = main.fetch_head(table, int(limit))

# Estado de conexión (siempre visible)
st.markdown("### Estado de conexión")
colA, colB, colC = st.columns(3)
colA.metric("Secrets presentes", "Sí" if meta["secrets_present"] else "No")
colB.metric("Leyendo de Supabase", "Sí" if meta["used_supabase"] else "No")
colC.metric("Filas mostradas", len(df))

if meta["error"]:
    st.info("Modo seguro: muestro datos de ejemplo si falla Supabase.")
    with st.expander("Detalle del error (útil para logs)"):
        st.code(meta["error"])

# Resultado
st.markdown(f"### Head de `{table}`")
if df.empty:
    st.warning("La tabla no devolvió filas (o no existe). Probá otro nombre o revisá permisos/RLS.")
else:
    st.dataframe(df, use_container_width=True)
    with st.expander("JSON crudo"):
        st.write(df.to_dict(orient="records"))

st.markdown("---")
st.caption("Entrega mínima garantizada: si Supabase falla, igual muestra datos de ejemplo y el estado.")
