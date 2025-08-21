# app.py
import streamlit as st
import pandas as pd
from datetime import timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main  # módulo local con funciones auxiliares

st.set_page_config(page_title="Gantt Proyectos", layout="wide", page_icon="📊")

# ---------- Inicializar datos ----------
if "df" not in st.session_state:
    st.session_state["df"] = main.sample_data()

# ---------- Sidebar ----------
st.sidebar.title("📋 Configuración")
st.sidebar.caption("Carga, filtros y exportaciones")

src = st.sidebar.radio("Fuente de datos", ["Ejemplo", "Subir CSV", "En blanco"], index=0, horizontal=True)

if src == "Ejemplo":
    st.session_state["df"] = main.sample_data()
elif src == "Subir CSV":
    up = st.sidebar.file_uploader("CSV con columnas estándar", type=["csv"])
    if up is not None:
        st.session_state["df"] = main.load_csv(up)
    else:
        st.sidebar.info("Subí un archivo CSV para continuar.")
else:
    st.session_state["df"] = main.ensure_schema(pd.DataFrame())

# Filtros
df = st.session_state["df"]
st.sidebar.subheader("Filtros")
projects = st.sidebar.multiselect("Proyecto", sorted(df["project"].dropna().unique().tolist()))
statuses = st.sidebar.multiselect("Estado", main.STATUSES)
priorities = st.sidebar.multiselect("Prioridad", main.PRIORITIES)
collab = st.sidebar.text_input("Buscar por colaborador (contiene)")
date_range = st.sidebar.date_input("Rango de fechas", value=None)

start_after = pd.to_datetime(date_range[0]) if isinstance(date_range, tuple) and date_range[0] else None
end_before = pd.to_datetime(date_range[1]) if isinstance(date_range, tuple) and date_range[1] else None

df = main.filter_df(df, projects, statuses, priorities, collab, start_after, end_before)

# ---------- Header ----------
st.title("🚀 Gantt de Proyectos (Streamlit)")
st.write("Administra visualmente tus proyectos: edita tareas en tabla, filtra y compartí el Gantt. "
         "Exportá a CSV o calendario (.ics).")

# ---------- Editable Grid ----------
st.subheader("✏️ Editor de tareas")
with st.expander("Ver/ocultar editor", expanded=True):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filter=True, sortable=True, editable=True)
    gb.configure_column("id", type=["numericColumn"], editable=False)
    gb.configure_column("project", header_name="Proyecto")
    gb.configure_column("task", header_name="Tarea")
    gb.configure_column("details", header_name="Detalles", flex=2)
    gb.configure_column("collaborators", header_name="Colaboradores")
    gb.configure_column("start", header_name="Inicio", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("end", header_name="Fin", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("progress", header_name="Progreso (%)", type=["numericColumn"], minWidth=130)
    gb.configure_column("status", header_name="Estado",
                        cellEditor="agSelectCellEditor", cellEditorParams={"values": main.STATUSES})
    gb.configure_column("priority", header_name="Prioridad",
                        cellEditor="agSelectCellEditor", cellEditorParams={"values": main.PRIORITIES})
    gb.configure_selection("multiple", use_checkbox=True)

    grid = AgGrid(
        df,
        gridOptions=gb.build(),
        theme="material",
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=350,
    )

    edited_df = pd.DataFrame(grid["data"])
    selected = grid["selected_rows"]

    # Guardar cambios en session_state
    st.session_state["df"], warns = main.validate(edited_df)
    if warns:
        st.info(" ; ".join(warns))

    col1, col2, col3 = st.columns(3)
    if col1.button("➕ Agregar tarea"):
        new_row = {
            "id": None,
            "project": "Nuevo Proyecto",
            "task": "Nueva tarea",
            "details": "",
            "collaborators": "",
            "start": pd.Timestamp.today(),
            "end": pd.Timestamp.today() + pd.Timedelta(days=7),
            "progress": 0,
            "status": "Planned",
            "priority": "Medium",
        }
        st.session_state["df"] = pd.concat([st.session_state["df"], pd.DataFrame([new_row])], ignore_index=True)

    if col2.button("🗑️ Borrar seleccionadas"):
        if selected:
            sel_ids = [r["id"] for r in selected if r.get("id") is not None]
            st.session_state["df"] = st.session_state["df"][~st.session_state["df"]["id"].isin(sel_ids)]
        else:
            st.warning("No hay filas seleccionadas.")

    if col3.button("🧬 Duplicar seleccionadas"):
        if selected:
            dup = pd.DataFrame(selected).copy()
            dup["id"] = None
            st.session_state["df"] = pd.concat([st.session_state["df"], dup], ignore_index=True)
        else:
            st.warning("No hay filas seleccionadas.")

# ---------- Tabs ----------
tab_gantt, tab_table, tab_cal = st.tabs(["📈 Gantt", "📋 Tabla", "📅 Calendario"])

with tab_gantt:
    color_by = st.selectbox("Color por", ["progress", "status", "priority", "project"], index=0)
    group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
    fig = main.make_gantt(st.session_state["df"], color_by=color_by, group_by_project=group_by_project)
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.dataframe(st.session_state["df"], use_container_width=True)

with tab_cal:
    today = pd.Timestamp.today()
    month = st.date_input("Mes", value=today.date().replace(day=1))
    if isinstance(month, tuple): month = month[0]
    month_start = pd.Timestamp(month).replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    subset = main.filter_df(st.session_state["df"], start_after=month_start, end_before=month_end)

    cal_rows = []
    for _, r in subset.dropna(subset=["start", "end"]).iterrows():
        d0, d1 = pd.Timestamp(r["start"]).date(), pd.Timestamp(r["end"]).date()
        d = d0
        while d <= d1:
            if month_start.date() <= d <= month_end.date():
                cal_rows.append({
                    "date": d,
                    "project": r["project"],
                    "task": r["task"],
                    "collaborators": r["collaborators"],
                    "progress": int(r["progress"]),
                    "status": r["status"],
                })
            d += timedelta(days=1)
    cal_df = pd.DataFrame(cal_rows)
    if cal_df.empty:
        st.info("No hay tareas en este mes.")
    else:
        st.dataframe(cal_df.sort_values(["date","project","task"]), use_container_width=True, height=350)

# ---------- Export ----------
st.subheader("📤 Exportar")
col1, col2 = st.columns(2)
with col1:
    csv_bytes = st.session_state["df"].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
with col2:
    ics_text = main.to_ics(st.session_state["df"], cal_name="Proyectos")
    st.download_button("📅 Exportar ICS", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

st.markdown("---")
st.caption("Hecho con ❤️ en Streamlit + Plotly + AgGrid")
