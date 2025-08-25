# app.py
import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main
import supabase_client as sbc

st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

st.title("🚀 Dashboard Proyectos (Supabase)")
st.caption("Conexión directa a la tabla `tasks` en Supabase.")

# =========================
# 1. Estado de conexión
# =========================
ok, data = main.check_connection()
if not ok:
    st.error(f"❌ Error al conectar con Supabase: {data}")
    st.stop()

# Inicializar session_state
if "df_full" not in st.session_state:
    st.session_state["df_full"] = main.df_from_supabase(data)

df_full = st.session_state["df_full"]

st.success("✅ Conectado correctamente a Supabase")

# =========================
# 2. Vista tabla cruda
# =========================
st.subheader("📋 Tabla `tasks` desde Supabase")
st.dataframe(df_full, use_container_width=True, height=350)

# KPIs
total, in_prog, done, overdue = main.kpi_counts(df_full)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total tareas", total)
c2.metric("En progreso", in_prog)
c3.metric("Completadas", done)
c4.metric("Vencidas", overdue)

st.markdown("---")

# =========================
# 3. Formulario para crear tareas
# =========================
st.subheader("🆕 Crear nueva tarea")
with st.form("new_task_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    project_name = col1.text_input("Proyecto *")
    task = col2.text_input("Tarea *")
    details = st.text_area("Detalles")
    owner = st.text_input("Owner")
    collaborators = st.text_input("Colaboradores (coma-separados)")
    col3, col4 = st.columns(2)
    start_date = col3.date_input("Fecha inicio", pd.Timestamp.today())
    end_date = col4.date_input("Fecha fin", pd.Timestamp.today() + pd.Timedelta(days=7))
    progress = st.slider("Progreso (%)", 0, 100, 0)
    col5, col6, col7 = st.columns(3)
    status = col5.selectbox("Estado", main.ENUM_STATUS, index=0)
    priority = col6.selectbox("Prioridad", main.ENUM_PRIORITY, index=1)
    rag = col7.selectbox("RAG", [""] + main.ENUM_RAG, index=0)

    submitted = st.form_submit_button("➕ Agregar")
    if submitted:
        if not project_name or not task:
            st.error("Proyecto y Tarea son obligatorios.")
        elif end_date < start_date:
            st.error("La fecha de fin no puede ser anterior a la de inicio.")
        else:
            new_row = {
                "project_name": project_name,
                "task": task,
                "details": details,
                "owner": owner,
                "collaborators": [c.strip() for c in collaborators.split(",")] if collaborators else None,
                "start_date": pd.to_datetime(start_date).date(),
                "end_date": pd.to_datetime(end_date).date(),
                "progress": progress,
                "status": status,
                "priority": priority,
                "rag": rag if rag else None,
            }
            sbc.insert_rows([new_row])
            st.success(f"Tarea '{task}' agregada a Supabase.")
            # refrescar
            _, data = main.check_connection()
            st.session_state["df_full"] = main.df_from_supabase(data)
            st.experimental_rerun()

st.markdown("---")

# =========================
# 4. Editor interactivo (CRUD)
# =========================
st.subheader("✏️ Editor de tareas")

gb = GridOptionsBuilder.from_dataframe(df_full)
gb.configure_default_column(resizable=True, filter=True, sortable=True, editable=True)

# Configurar enums editables
gb.configure_column("status", cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_STATUS})
gb.configure_column("priority", cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_PRIORITY})
gb.configure_column("rag", cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_RAG})

gb.configure_selection("multiple", use_checkbox=True)

grid = AgGrid(
    df_full,
    gridOptions=gb.build(),
    theme="alpine",
    update_mode=GridUpdateMode.MODEL_CHANGED,
    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    fit_columns_on_grid_load=True,
    height=420,
)

edited_df = pd.DataFrame(grid["data"])
selected = grid["selected_rows"]

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("💾 Guardar cambios (upsert)"):
        payload = main.payload_for_upsert(edited_df)
        sbc.upsert_rows(payload)
        st.success("Cambios guardados en Supabase.")
        # refrescar
        _, data = main.check_connection()
        st.session_state["df_full"] = main.df_from_supabase(data)
        st.experimental_rerun()

with c2:
    if st.button("🗑️ Eliminar seleccionadas"):
        if selected:
            ids = [r.get("id") for r in selected if r.get("id")]
            if ids:
                sbc.delete_by_ids(ids)
                st.success(f"Eliminadas {len(ids)} filas.")
                _, data = main.check_connection()
                st.session_state["df_full"] = main.df_from_supabase(data)
                st.experimental_rerun()
            else:
                st.warning("Las filas seleccionadas no tienen ID válido.")
        else:
            st.warning("Seleccioná filas para borrar.")

with c3:
    if st.button("🔄 Recargar"):
        _, data = main.check_connection()
        st.session_state["df_full"] = main.df_from_supabase(data)
        st.experimental_rerun()

st.markdown("---")

# =========================
# 5. Vista Gantt
# =========================
st.subheader("📈 Vista Gantt")
fig = main.make_gantt(edited_df)
st.plotly_chart(fig, use_container_width=True)
