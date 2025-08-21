# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
from io import StringIO
from pathlib import Path

import main  # local module

st.set_page_config(page_title="Gantt Proyectos", layout="wide", page_icon="📊")

# ---------- Sidebar ----------
st.sidebar.title("📋 Configuración")
st.sidebar.caption("Carga, filtros y exportaciones")

src = st.sidebar.radio("Fuente de datos", ["Ejemplo", "Subir CSV", "En blanco"], index=0, horizontal=True)

if src == "Ejemplo":
    df = main.sample_data()
elif src == "Subir CSV":
    up = st.sidebar.file_uploader("CSV con columnas estándar", type=["csv"])
    if up is not None:
        df = main.load_csv(up)
    else:
        st.sidebar.info("Subí un archivo CSV para continuar.")
        df = main.sample_data()
else:
    df = main.ensure_schema(pd.DataFrame())

# Filters
st.sidebar.subheader("Filtros")
projects = st.sidebar.multiselect("Proyecto", sorted(df["project"].dropna().unique().tolist()))
statuses = st.sidebar.multiselect("Estado", main.STATUSES)
priorities = st.sidebar.multiselect("Prioridad", main.PRIORITIES)
collab = st.sidebar.text_input("Buscar por colaborador (contiene)")
date_range = st.sidebar.date_input("Rango de fechas (muestra tareas que tocan este rango)",
                                   value=None)

start_after = pd.to_datetime(date_range[0]) if isinstance(date_range, tuple) and date_range[0] else None
end_before = pd.to_datetime(date_range[1]) if isinstance(date_range, tuple) and date_range[1] else None

df = main.filter_df(df, projects, statuses, priorities, collab, start_after, end_before)

# ---------- Header ----------
st.title("🚀 Gantt de Proyectos (Streamlit)")
st.write(
    "Administra visualmente tus proyectos: edita tareas en tabla, filtra y compartí el Gantt. "
    "Exportá a CSV o calendario (.ics) para agendar en Google/Outlook."
)

# ---------- Editable Grid ----------
st.subheader("✏️ Editor de tareas")
with st.expander("Ver/ocultar editor", expanded=True):
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filter=True, sortable=True, editable=True)
    # column configurations
    gb.configure_column("id", type=["numericColumn"], editable=False)
    gb.configure_column("project", header_name="Proyecto")
    gb.configure_column("task", header_name="Tarea")
    gb.configure_column("details", header_name="Detalles", flex=2)
    gb.configure_column("collaborators", header_name="Colaboradores (coma-separados)")
    gb.configure_column("start", header_name="Inicio", type=["dateColumn"], valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("end", header_name="Fin", type=["dateColumn"], valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("progress", header_name="Progreso (%)", type=["numericColumn"], minWidth=130)
    gb.configure_column("status", header_name="Estado", cellEditor="agSelectCellEditor", cellEditorParams={"values": main.STATUSES})
    gb.configure_column("priority", header_name="Prioridad", cellEditor="agSelectCellEditor", cellEditorParams={"values": main.PRIORITIES})

    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    grid_options = gb.build()

    grid = AgGrid(
        df,
        gridOptions=grid_options,
        theme="material",
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=350,
    )
    edited_df = grid["data"]
    selected = grid["selected_rows"]

    col1, col2, col3, col4 = st.columns([1,1,1,2])
    if col1.button("➕ Agregar tarea"):
        new_row = pd.DataFrame([{
            "id": None, "project": "", "task": "", "details": "",
            "collaborators": "", "start": pd.NaT, "end": pd.NaT,
            "progress": 0, "status": "Planned", "priority": "Medium"
        }])
        edited_df = pd.concat([pd.DataFrame(edited_df), new_row], ignore_index=True)

    if col2.button("🗑️ Borrar seleccionadas"):
        if selected:
            sel_ids = [r["id"] for r in selected if r.get("id") is not None]
            edited_df = pd.DataFrame(edited_df)
            if sel_ids:
                edited_df = edited_df[~edited_df["id"].isin(sel_ids)]
        else:
            st.warning("No hay filas seleccionadas.")

    if col3.button("🧬 Duplicar seleccionadas"):
        if selected:
            dup = pd.DataFrame(selected).copy()
            dup["id"] = None  # se reasignará
            edited_df = pd.concat([pd.DataFrame(edited_df), dup], ignore_index=True)
        else:
            st.warning("No hay filas seleccionadas.")

# Validate & coerce
edited_df = pd.DataFrame(edited_df)
edited_df, warns = main.validate(edited_df)
if warns:
    st.info(" ; ".join(warns))

# ---------- Tabs: Gantt / Tabla / Calendario ----------
tab_gantt, tab_table, tab_cal = st.tabs(["📈 Gantt", "📋 Tabla", "📅 Calendario simple"])

with tab_gantt:
    left, right = st.columns([5,2])
    with right:
        color_by = st.selectbox("Color por", ["progress", "status", "priority", "project"], index=0)
        group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
        st.caption("Consejo: usá filtros en la barra lateral para foco por proyecto/estado.")

    fig = main.make_gantt(edited_df, color_by=color_by, group_by_project=group_by_project)
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.dataframe(edited_df, use_container_width=True)

with tab_cal:
    st.write("Calendario mensual básico por días con tareas que se solapan en el mes elegido.")
    # choose month
    today = pd.Timestamp.today()
    month = st.date_input("Mes", value=today.date().replace(day=1))
    if isinstance(month, tuple):
        month = month[0]
    month_start = pd.Timestamp(month).replace(day=1)
    month_end = (month_start + pd.offsets.MonthEnd(1))
    subset = main.filter_df(edited_df, start_after=month_start, end_before=month_end)
    # expand tasks into daily rows
    cal_rows = []
    for _, r in subset.dropna(subset=["start","end"]).iterrows():
        d0 = pd.Timestamp(r["start"]).date()
        d1 = pd.Timestamp(r["end"]).date()
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
            d = d + timedelta(days=1)
    cal_df = pd.DataFrame(cal_rows)
    if cal_df.empty:
        st.info("No hay tareas en este mes.")
    else:
        st.dataframe(cal_df.sort_values(["date","project","task"]), use_container_width=True, height=350)

# ---------- Exports ----------
st.subheader("📤 Exportar")
c1, c2, c3 = st.columns([1,1,2])

with c1:
    csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")

with c2:
    ics_text = main.to_ics(edited_df, cal_name="Proyectos")
    st.download_button("📅 Exportar ICS", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

with c3:
    st.caption("Tip: compartí esta app en un servidor (Streamlit Community Cloud / servidor propio) y los directores podrán ver el Gantt en tiempo real.")

st.markdown("---")
st.caption("Hecho con ❤️ en Streamlit + Plotly.")

