# app.py
import streamlit as st
import pandas as pd
import main

st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

# ---------- Estado inicial ----------
if "df" not in st.session_state:
    st.session_state.df = main.fetch_tasks()

sb_ok = main.supabase_ready()
st.sidebar.markdown("### 🔌 Conexión")
if sb_ok:
    st.sidebar.success("Supabase conectado")
else:
    st.sidebar.warning("Modo demo: sin Supabase (solo lectura)")

st.title("🚀 Gantt de Proyectos")
st.caption("UI robusta (st.data_editor). Si no hay DB, se muestran datos de ejemplo para no cortar la demo.")

# ---------- Editor (nativo) ----------
st.subheader("✏️ Editor de tareas")
df_edit = st.session_state.df.copy()
df_edit.insert(0, "BORRAR", False)

config = {
    "id": st.column_config.NumberColumn("ID", help="Autogenerado", disabled=True),
    "project_name": st.column_config.TextColumn("Proyecto"),
    "task": st.column_config.TextColumn("Tarea"),
    "details": st.column_config.TextColumn("Detalles"),
    "owner": st.column_config.TextColumn("Owner"),
    "collaborators": st.column_config.TextColumn("Colaboradores (coma-separados)"),
    "start": st.column_config.DateColumn("Inicio", format="YYYY-MM-DD"),
    "end": st.column_config.DateColumn("Fin", format="YYYY-MM-DD"),
    "progress": st.column_config.NumberColumn("Progreso (%)", min_value=0, max_value=100, step=1),
    "status": st.column_config.SelectboxColumn("Estado", options=main.ENUM_STATUS),
    "priority": st.column_config.SelectboxColumn("Prioridad", options=main.ENUM_PRIORITY),
    "rag": st.column_config.SelectboxColumn("RAG", options=[""] + main.ENUM_RAG),
    "milestone": st.column_config.CheckboxColumn("Milestone"),
    "baseline_start": st.column_config.DateColumn("Baseline inicio", format="YYYY-MM-DD"),
    "baseline_end": st.column_config.DateColumn("Baseline fin", format="YYYY-MM-DD"),
    "actual_start": st.column_config.DateColumn("Real inicio", format="YYYY-MM-DD"),
    "actual_end": st.column_config.DateColumn("Real fin", format="YYYY-MM-DD"),
    "phase": st.column_config.TextColumn("Fase"),
    "workstream": st.column_config.TextColumn("Workstream"),
    "tags": st.column_config.TextColumn("Tags (coma-separados)"),
    "external_link": st.column_config.LinkColumn("Link externo"),
}

edited = st.data_editor(
    df_edit,
    column_config=config,
    use_container_width=True,
    num_rows="dynamic",  # permite agregar filas desde la UI
    hide_index=True,
)

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("💾 Guardar (upsert)", use_container_width=True):
        to_save = edited.drop(columns=["BORRAR"], errors="ignore")
        to_save = main.ensure_schema(to_save)
        if sb_ok:
            main.upsert_tasks(to_save)
            st.success("Cambios guardados en Supabase.")
            st.session_state.df = main.fetch_tasks()
        else:
            st.info("Modo demo: cambios aplicados solo en pantalla (no persistidos).")
            st.session_state.df = to_save

with col2:
    if st.button("🗑️ Borrar marcadas", use_container_width=True):
        ids = edited.loc[edited["BORRAR"] == True, "id"].dropna().astype(int).tolist()
        if ids:
            if sb_ok:
                main.delete_tasks(ids)
                st.success(f"Eliminadas {len(ids)} fila(s) en Supabase.")
                st.session_state.df = main.fetch_tasks()
            else:
                st.info("Modo demo: solo se ocultan en pantalla.")
                st.session_state.df = st.session_state.df[~st.session_state.df["id"].isin(ids)]
        else:
            st.warning("No hay filas con ID marcadas para borrar.")

with col3:
    if st.button("🔄 Recargar desde Supabase", use_container_width=True):
        st.session_state.df = main.fetch_tasks()
        st.info("Datos recargados.")

st.divider()

# ---------- Filtros y Gantt ----------
st.sidebar.title("🔎 Filtros")
df_view = st.session_state.df.copy()

projects = st.sidebar.multiselect("Proyecto", sorted(df_view["project_name"].dropna().unique().tolist()))
statuses = st.sidebar.multiselect("Estado", main.ENUM_STATUS)
priorities = st.sidebar.multiselect("Prioridad", main.ENUM_PRIORITY)
rag_filter = st.sidebar.multiselect("RAG", main.ENUM_RAG)
owner = st.sidebar.text_input("Owner contiene…")
date_range = st.sidebar.date_input("Rango de fechas", value=None)

if projects:   df_view = df_view[df_view["project_name"].isin(projects)]
if statuses:   df_view = df_view[df_view["status"].isin(statuses)]
if priorities: df_view = df_view[df_view["priority"].isin(priorities)]
if rag_filter: df_view = df_view[df_view["rag"].isin(rag_filter)]
if owner:      df_view = df_view[df_view["owner"].str.contains(owner, case=False, na=False)]

start_after = pd.to_datetime(date_range[0]) if isinstance(date_range, tuple) and date_range[0] else None
end_before  = pd.to_datetime(date_range[1]) if isinstance(date_range, tuple) and date_range[1] else None
if start_after is not None:
    df_view = df_view[(df_view["end"].isna()) | (df_view["end"] >= start_after)]
if end_before is not None:
    df_view = df_view[(df_view["start"].isna()) | (df_view["start"] <= end_before)]

st.subheader("📈 Gantt")
mostrar_gantt = st.toggle("Mostrar Gantt", value=True, help="Apagalo si hubiera problemas de render.")
if mostrar_gantt:
    try:
        fig = main.make_gantt(df_view, color_by=st.selectbox("Color por", ["progress","status","priority","project_name","rag"], index=0),
                              group_by_project=st.checkbox("Agrupar por proyecto (eje Y)", value=True))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error("No pude renderizar el Gantt. Muestro tabla.")
        st.exception(e)

st.subheader("📋 Tabla (vista filtrada)")
st.dataframe(df_view, use_container_width=True)

# ---------- Export ----------
st.subheader("📤 Exportar")
csv_bytes = st.session_state.df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
