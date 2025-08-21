# app.py
import os
import tempfile
import streamlit as st
import pandas as pd
from datetime import timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main  # módulo local

st.set_page_config(page_title="Gantt Proyectos", layout="wide", page_icon="📊")

FILE_PATH = "tareas.txt"

# -------- utilidades de IO (robusto/atómico) --------
def load_tasks(path: str) -> pd.DataFrame:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        df = main.sample_data()
        save_tasks(path, df)
        return df
    df = pd.read_csv(path)
    return main.ensure_schema(df)

def save_tasks(path: str, df: pd.DataFrame):
    # escritura atómica para evitar archivos truncos
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="tasks_", suffix=".csv", dir=os.path.dirname(path) or ".")
    os.close(tmp_fd)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)  # move atomically
    except Exception as e:
        st.error(f"Error guardando {path}: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

# ---------- cargar en memoria TODA la data para el editor ----------
if "df_full" not in st.session_state:
    st.session_state["df_full"] = load_tasks(FILE_PATH)

# ---------- Header ----------
st.title("🚀 Gantt de Proyectos (Streamlit)")
st.caption("El editor modifica TODAS las tareas y guarda automáticamente en `tareas.txt`. Los filtros solo afectan la vista.")

# ---------- Editor (sin filtros, fuente de la verdad) ----------
st.subheader("✏️ Editor (todas las tareas)")
df_full = st.session_state["df_full"]

with st.expander("Abrir editor", expanded=True):
    gb = GridOptionsBuilder.from_dataframe(df_full)
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
        df_full,
        gridOptions=gb.build(),
        theme="material",
        update_mode=GridUpdateMode.MODEL_CHANGED,  # captura ediciones en celdas
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=360,
    )

    edited_df = pd.DataFrame(grid["data"])
    selected = grid["selected_rows"]

    # Validar para mantener consistencia (ids, fechas, progress)
    validated_df, warns = main.validate(edited_df)
    if warns:
        st.info(" ; ".join(warns))

    # Persistir SIEMPRE lo que ve el usuario en el editor (aunque quede vacío)
    st.session_state["df_full"] = validated_df
    save_tasks(FILE_PATH, st.session_state["df_full"])

    c1, c2, c3 = st.columns(3)
    if c1.button("➕ Agregar tarea"):
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
        st.session_state["df_full"] = pd.concat([st.session_state["df_full"], pd.DataFrame([new_row])], ignore_index=True)
        save_tasks(FILE_PATH, st.session_state["df_full"])

    if c2.button("🗑️ Borrar seleccionadas"):
        if selected:
            sel_ids = [r.get("id") for r in selected if r.get("id") is not None]
            if sel_ids:
                st.session_state["df_full"] = st.session_state["df_full"][~st.session_state["df_full"]["id"].isin(sel_ids)]
                save_tasks(FILE_PATH, st.session_state["df_full"])
            else:
                st.warning("Las filas seleccionadas no tienen ID asignado aún. Editá/guarda una celda para autogenerar IDs y volvé a intentar.")
        else:
            st.warning("No hay filas seleccionadas.")

    if c3.button("🧬 Duplicar seleccionadas"):
        if selected:
            dup = pd.DataFrame(selected).copy()
            dup["id"] = None  # para que validate() reasigne id
            st.session_state["df_full"] = pd.concat([st.session_state["df_full"], dup], ignore_index=True)
            save_tasks(FILE_PATH, st.session_state["df_full"])
        else:
            st.warning("No hay filas seleccionadas.")

st.success(f"✅ Cambios guardados en {FILE_PATH}")

# ---------- Filtros (SOLO vista) ----------
st.sidebar.title("🔎 Filtros de vista")
df_view = st.session_state["df_full"].copy()

projects = st.sidebar.multiselect("Proyecto", sorted(df_view["project"].dropna().unique().tolist()))
statuses = st.sidebar.multiselect("Estado", main.STATUSES)
priorities = st.sidebar.multiselect("Prioridad", main.PRIORITIES)
collab = st.sidebar.text_input("Buscar por colaborador (contiene)")
date_range = st.sidebar.date_input("Rango de fechas", value=None)

start_after = pd.to_datetime(date_range[0]) if isinstance(date_range, tuple) and date_range[0] else None
end_before = pd.to_datetime(date_range[1]) if isinstance(date_range, tuple) and date_range[1] else None

df_view = main.filter_df(df_view, projects, statuses, priorities, collab, start_after, end_before)

# ---------- Tabs de visualización ----------
tab_gantt, tab_table, tab_cal = st.tabs(["📈 Gantt", "📋 Tabla (vista filtrada)", "📅 Calendario"])

with tab_gantt:
    color_by = st.selectbox("Color por", ["progress", "status", "priority", "project"], index=0)
    group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
    fig = main.make_gantt(df_view, color_by=color_by, group_by_project=group_by_project)
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.dataframe(df_view, use_container_width=True)

with tab_cal:
    today = pd.Timestamp.today()
    month = st.date_input("Mes", value=today.date().replace(day=1))
    if isinstance(month, tuple): month = month[0]
    month_start = pd.Timestamp(month).replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(1)

    subset = main.filter_df(st.session_state["df_full"], start_after=month_start, end_before=month_end)
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
    csv_bytes = st.session_state["df_full"].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
with col2:
    ics_text = main.to_ics(df_view if not df_view.empty else st.session_state["df_full"], cal_name="Proyectos")
    st.download_button("📅 Exportar ICS (vista)", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

st.markdown("---")
st.caption("Hecho con ❤️ en Streamlit + Plotly + AgGrid")
