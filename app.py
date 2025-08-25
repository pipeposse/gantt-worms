# app.py
import streamlit as st
import pandas as pd
from datetime import timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main

st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

# =========================
# Estilos y layout
# =========================
CUSTOM_CSS = """
<style>
/* Contenedor principal más aireado */
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
/* Badges simples */
.badge {display:inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.8rem;}
.badge.rag-Verde {background: #E6F4EA; color: #137333;}
.badge.rag-Amarillo {background: #FEF7E0; color: #B06E00;}
.badge.rag-Rojo {background: #FCE8E6; color: #A50E0E;}
/* Botonera */
.action-bar .stButton>button {border-radius: 10px; padding: 0.45rem 0.9rem;}
/* KPIs */
.kpi {padding: 0.9rem; border-radius: 12px; background: #f8f9fb; border: 1px solid #eef1f5;}
.kpi h3 {margin: 0; font-size: 0.95rem; color: #6b7280;}
.kpi .num {font-size: 1.6rem; font-weight: 700; margin-top: 0.25rem;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =========================
# Carga inicial
# =========================
if "df_full" not in st.session_state:
    st.session_state["df_full"] = main.fetch_tasks()

st.title("🚀 Gantt de Proyectos")
st.caption("Edición directa, filtros rápidos y vista Gantt con línea de hoy. Persistencia en Supabase.")

# KPIs rápidos
total, in_prog, done, overdue = main.kpi_counts(st.session_state["df_full"])
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="kpi"><h3>Total tareas</h3><div class="num">{total}</div></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="kpi"><h3>En progreso</h3><div class="num">{in_prog}</div></div>', unsafe_allow_html=True)
with c3: st.markdown(f'<div class="kpi"><h3>Completadas</h3><div class="num">{done}</div></div>', unsafe_allow_html=True)
with c4: st.markdown(f'<div class="kpi"><h3>Vencidas</h3><div class="num">{overdue}</div></div>', unsafe_allow_html=True)

st.markdown("---")

# =========================
# Editor (fuente de verdad)
# =========================
st.subheader("✏️ Editor de tareas")
with st.expander("Abrir editor", expanded=True):
    df = st.session_state["df_full"]
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filter=True, sortable=True, editable=True)

    gb.configure_column("id", type=["numericColumn"], editable=False)
    gb.configure_column("project_name", header_name="Proyecto")
    gb.configure_column("task", header_name="Tarea")
    gb.configure_column("details", header_name="Detalles", flex=2)
    gb.configure_column("owner", header_name="Owner")
    gb.configure_column("collaborators", header_name="Colaboradores (coma-separados)")
    gb.configure_column("start", header_name="Inicio", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("end", header_name="Fin", type=["dateColumn"],
                        valueFormatter="value && new Date(value).toISOString().slice(0,10)")
    gb.configure_column("progress", header_name="Progreso (%)", type=["numericColumn"], minWidth=130)

    gb.configure_column("status", header_name="Estado",
                        cellEditor="agSelectCellEditor",
                        cellEditorParams={"values": main.ENUM_STATUS})
    gb.configure_column("priority", header_name="Prioridad",
                        cellEditor="agSelectCellEditor",
                        cellEditorParams={"values": main.ENUM_PRIORITY})
    gb.configure_column("rag", header_name="RAG",
                        cellEditor="agSelectCellEditor",
                        cellEditorParams={"values": main.ENUM_RAG})
    gb.configure_column("milestone", header_name="Milestone")

    gb.configure_column("phase", header_name="Fase")
    gb.configure_column("workstream", header_name="Workstream")
    gb.configure_column("tags", header_name="Tags (coma-separados)")
    gb.configure_column("external_link", header_name="Link externo", flex=1)

    gb.configure_selection("multiple", use_checkbox=True)
    grid = AgGrid(
        df,
        gridOptions=gb.build(),
        theme="alpine",  # estética limpia
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=420,
    )

    edited_df = pd.DataFrame(grid["data"])
    selected = grid["selected_rows"]

    # Normalizar/asegurar
    edited_df = main.ensure_schema(edited_df)
    st.session_state["df_full"] = edited_df

    st.markdown('<div class="action-bar">', unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns([1,1,1,2])
    with a1:
        if st.button("➕ Agregar tarea"):
            new_row = pd.DataFrame([{
                "id": None,
                "project_name": "Nuevo Proyecto",
                "task": "Nueva tarea",
                "details": "",
                "owner": "",
                "collaborators": "",
                "start": pd.Timestamp.today(),
                "end": pd.Timestamp.today() + pd.Timedelta(days=7),
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
            st.toast("Fila agregada. No olvides 💾 Guardar (upsert).")

    with a2:
        if st.button("🗑️ Borrar seleccionadas"):
            if selected:
                sel_ids = [r.get("id") for r in selected if r.get("id") is not None]
                if sel_ids:
                    main.delete_tasks(sel_ids)  # borra en DB
                    st.session_state["df_full"] = st.session_state["df_full"][~st.session_state["df_full"]["id"].isin(sel_ids)]
                    st.success("Registros eliminados en Supabase.")
                else:
                    # Son filas nuevas aún sin ID -> solo las saco de session_state
                    to_drop = pd.DataFrame(selected).dropna(subset=["task"])
                    if not to_drop.empty:
                        st.session_state["df_full"] = st.session_state["df_full"][~st.session_state["df_full"]["task"].isin(to_drop["task"])]
                        st.info("Filas locales sin ID eliminadas. Guardá para sincronizar.")
            else:
                st.warning("No hay filas seleccionadas.")

    with a3:
        if st.button("💾 Guardar (upsert)"):
            main.upsert_tasks(st.session_state["df_full"])
            st.success("Cambios guardados en Supabase.")
            st.session_state["df_full"] = main.fetch_tasks()

    with a4:
        if st.button("🔄 Recargar desde Supabase"):
            st.session_state["df_full"] = main.fetch_tasks()
            st.info("Datos recargados.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# =========================
# Filtros de vista
# =========================
st.sidebar.title("🔎 Filtros")
df_view = st.session_state["df_full"].copy()

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

# =========================
# Tabs de visualización
# =========================
tab_gantt, tab_table, tab_cal = st.tabs(["📈 Gantt", "📋 Tabla", "📅 Calendario"])

with tab_gantt:
    color_by = st.selectbox("Color por", ["progress", "status", "priority", "project_name", "rag"], index=0)
    group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
    fig = main.make_gantt(df_view, color_by=color_by, group_by_project=group_by_project)
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.dataframe(df_view, use_container_width=True, height=420)

with tab_cal:
    st.write("Calendario mensual básico (vista filtrada).")
    today = pd.Timestamp.today()
    month = st.date_input("Mes", value=today.date().replace(day=1))
    if isinstance(month, tuple): month = month[0]
    month_start = pd.Timestamp(month).replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    subset = st.session_state["df_full"].copy()
    subset = subset[
        (subset["start"].notna()) & (subset["end"].notna()) &
        (subset["end"] >= month_start) & (subset["start"] <= month_end)
    ]
    rows = []
    for _, r in subset.iterrows():
        d0, d1 = pd.Timestamp(r["start"]).date(), pd.Timestamp(r["end"]).date()
        d = d0
        while d <= d1:
            if month_start.date() <= d <= month_end.date():
                rows.append({
                    "date": d,
                    "project": r["project_name"],
                    "task": r["task"],
                    "owner": r["owner"],
                    "progress": int(r["progress"]),
                    "status": r["status"],
                    "rag": r["rag"]
                })
            d += timedelta(days=1)
    cal_df = pd.DataFrame(rows)
    if cal_df.empty:
        st.info("No hay tareas en este mes.")
    else:
        st.dataframe(cal_df.sort_values(["date","project","task"]), use_container_width=True, height=360)

# =========================
# Export
# =========================
st.subheader("📤 Exportar")
c1, c2 = st.columns(2)
with c1:
    csv_bytes = st.session_state["df_full"].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
with c2:
    ics_text = main.to_ics(df_view if not df_view.empty else st.session_state["df_full"], cal_name="Proyectos")
    st.download_button("📅 ICS (vista)", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

st.caption("UI moderna con AgGrid + Plotly. Datos persistidos en Supabase.")
