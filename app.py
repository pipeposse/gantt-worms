# app.py
import streamlit as st
import pandas as pd
from datetime import timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main  # helpers + conexión + CRUD (Supabase)

st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

# ==============================
# Carga inicial desde Supabase
# ==============================
if "df_full" not in st.session_state:
    st.session_state["df_full"] = main.fetch_tasks()

st.title("🚀 Gantt de Proyectos (Streamlit + Supabase)")
st.caption("Editá en la grilla, luego usá 💾 Guardar (upsert) para sincronizar con Supabase. Podés borrar y recargar.")

# ==============================
# Editor (fuente de verdad)
# ==============================
st.subheader("✏️ Editor de tareas")
df_full = st.session_state["df_full"]

with st.expander("Abrir editor", expanded=True):
    gb = GridOptionsBuilder.from_dataframe(df_full)
    gb.configure_default_column(resizable=True, filter=True, sortable=True, editable=True)

    # columnas y editores
    gb.configure_column("id", header_name="ID", type=["numericColumn"], editable=False, maxWidth=120)
    gb.configure_column("project_name", header_name="Proyecto")
    gb.configure_column("task", header_name="Tarea")
    gb.configure_column("details", header_name="Detalles", flex=2)
    gb.configure_column("owner", header_name="Owner")
    gb.configure_column("collaborators", header_name="Colaboradores (coma-separados)")
    gb.configure_column("start", header_name="Inicio", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("end", header_name="Fin", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("baseline_start", header_name="Baseline inicio", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("baseline_end", header_name="Baseline fin", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("actual_start", header_name="Real inicio", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("actual_end", header_name="Real fin", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("progress", header_name="Progreso (%)", type=["numericColumn"], minWidth=140)
    gb.configure_column("status", header_name="Estado",
                        cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_STATUS})
    gb.configure_column("priority", header_name="Prioridad",
                        cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_PRIORITY})
    gb.configure_column("rag", header_name="RAG",
                        cellEditor="agSelectCellEditor", cellEditorParams={"values": main.ENUM_RAG})
    gb.configure_column("milestone", header_name="Milestone", type=["booleanColumn"])
    gb.configure_column("phase", header_name="Fase")
    gb.configure_column("workstream", header_name="Workstream")
    gb.configure_column("tags", header_name="Tags (coma-separados)")
    gb.configure_column("external_link", header_name="Link externo", flex=1)

    # columnas de auditoría solo lectura si existen
    if "created_at" in df_full.columns:
        gb.configure_column("created_at", editable=False)
    if "updated_at" in df_full.columns:
        gb.configure_column("updated_at", editable=False)

    gb.configure_selection("multiple", use_checkbox=True)

    grid = AgGrid(
        df_full,
        gridOptions=gb.build(),
        theme="material",
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=420,
    )

    edited_df = pd.DataFrame(grid["data"])
    selected = grid["selected_rows"]

    # Normalizar/asegurar esquema y persistir en sesión (todavía sin guardar en DB)
    st.session_state["df_full"] = main.ensure_schema(edited_df)

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("➕ Agregar tarea"):
        new_row = pd.DataFrame([{
            "id": None,
            "project_name": "Nuevo Proyecto",
            "task": "Nueva tarea",
            "details": "",
            "owner": "",
            "collaborators": "",
            "baseline_start": pd.NaT,
            "baseline_end": pd.NaT,
            "start": pd.Timestamp.today(),
            "end": pd.Timestamp.today() + pd.Timedelta(days=7),
            "actual_start": pd.NaT,
            "actual_end": pd.NaT,
            "progress": 0,
            "status": "No iniciado",
            "priority": "Media",
            "rag": "",
            "milestone": False,
            "phase": "",
            "workstream": "",
            "tags": "",
            "external_link": ""
        }])
        st.session_state["df_full"] = pd.concat([st.session_state["df_full"], new_row], ignore_index=True)

    if c2.button("🗑️ Borrar seleccionadas"):
        if selected:
            sel_ids = [r.get("id") for r in selected if r.get("id") is not None]
            # Borra en DB las que ya tienen ID
            if sel_ids:
                main.delete_tasks(sel_ids)
            # Quita de la vista todas (con o sin id)
            def _row_not_selected(row):
                # si no tiene id, lo comparamos por campos clave
                if pd.isna(row.get("id")):
                    for s in selected:
                        # heurística simple para coincidir fila nueva
                        if (str(s.get("task","")).strip() == str(row.get("task","")).strip()
                            and str(s.get("project_name","")).strip() == str(row.get("project_name","")).strip()):
                            return False
                    return True
                return row.get("id") not in sel_ids

            st.session_state["df_full"] = st.session_state["df_full"][st.session_state["df_full"].apply(_row_not_selected, axis=1)]
        else:
            st.warning("No hay filas seleccionadas.")

    if c3.button("💾 Guardar (upsert)"):
        main.upsert_tasks(st.session_state["df_full"])
        st.success("Cambios guardados en Supabase.")
        # refrescar para traer IDs autogenerados y timestamps
        st.session_state["df_full"] = main.fetch_tasks()

    if c4.button("🔄 Recargar desde Supabase"):
        st.session_state["df_full"] = main.fetch_tasks()
        st.info("Datos recargados.")

# ==============================
# Filtros de vista (no escriben)
# ==============================
st.sidebar.title("🔎 Filtros de vista")
df_view = st.session_state["df_full"].copy()

projects = st.sidebar.multiselect("Proyecto", sorted(df_view["project_name"].dropna().unique().tolist()))
statuses = st.sidebar.multiselect("Estado", main.ENUM_STATUS)
priorities = st.sidebar.multiselect("Prioridad", main.ENUM_PRIORITY)
rag_filter = st.sidebar.multiselect("RAG", main.ENUM_RAG)
owner = st.sidebar.text_input("Owner contiene…")
date_range = st.sidebar.date_input("Rango de fechas", value=None)

if projects:
    df_view = df_view[df_view["project_name"].isin(projects)]
if statuses:
    df_view = df_view[df_view["status"].isin(statuses)]
if priorities:
    df_view = df_view[df_view["priority"].isin(priorities)]
if rag_filter:
    df_view = df_view[df_view["rag"].isin(rag_filter)]
if owner:
    df_view = df_view[df_view["owner"].str.contains(owner, case=False, na=False)]

start_after = pd.to_datetime(date_range[0]) if isinstance(date_range, tuple) and date_range[0] else None
end_before = pd.to_datetime(date_range[1]) if isinstance(date_range, tuple) and date_range[1] else None
if start_after is not None:
    df_view = df_view[(df_view["end"].isna()) | (df_view["end"] >= start_after)]
if end_before is not None:
    df_view = df_view[(df_view["start"].isna()) | (df_view["start"] <= end_before)]

# ==============================
# Tabs de visualización
# ==============================
tab_gantt, tab_table, tab_cal = st.tabs(["📈 Gantt", "📋 Tabla", "📅 Calendario"])

with tab_gantt:
    color_by = st.selectbox("Color por", ["progress", "status", "priority", "project_name", "rag"], index=0)
    group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
    fig = main.make_gantt(df_view, color_by=color_by, group_by_project=group_by_project)
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.dataframe(df_view, use_container_width=True)

with tab_cal:
    today = pd.Timestamp.today()
    month = st.date_input("Mes", value=today.date().replace(day=1))
    if isinstance(month, tuple):
        month = month[0]
    month_start = pd.Timestamp(month).replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    subset = st.session_state["df_full"].copy()
    subset = subset[
        (subset["start"].notna()) & (subset["end"].notna()) &
        (subset["end"] >= month_start) & (subset["start"] <= month_end)
    ]

    cal_rows = []
    for _, r in subset.iterrows():
        d0, d1 = pd.Timestamp(r["start"]).date(), pd.Timestamp(r["end"]).date()
        d = d0
        while d <= d1:
            if month_start.date() <= d <= month_end.date():
                cal_rows.append({
                    "date": d,
                    "project": r["project_name"],
                    "task": r["task"],
                    "owner": r["owner"],
                    "progress": int(r["progress"]),
                    "status": r["status"],
                    "rag": r["rag"]
                })
            d += timedelta(days=1)

    cal_df = pd.DataFrame(cal_rows)
    if cal_df.empty:
        st.info("No hay tareas en este mes.")
    else:
        st.dataframe(cal_df.sort_values(["date","project","task"]), use_container_width=True, height=360)

# ==============================
# Export
# ==============================
st.subheader("📤 Exportar")
c1, c2 = st.columns(2)
with c1:
    csv_bytes = st.session_state["df_full"].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
with c2:
    ics_text = main.to_ics(df_view if not df_view.empty else st.session_state["df_full"], cal_name="Proyectos")
    st.download_button("📅 ICS (vista)", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

st.caption("Conectado a Supabase mediante st-supabase-connection · CRUD completo desde la grilla.")
