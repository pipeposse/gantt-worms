# app.py
import os
import tempfile
import streamlit as st
import pandas as pd
from datetime import timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import main  # utilidades: sample_data, ensure_schema, validate, make_gantt, to_ics

st.set_page_config(page_title="Gantt Proyectos", layout="wide", page_icon="📊")

# ---------------- Utilidades de archivo ----------------
def abspath(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p.strip()))

def parent_writable(path: str) -> bool:
    folder = os.path.dirname(path) or "."
    return os.access(folder, os.W_OK)

def file_writable(path: str) -> bool:
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    return parent_writable(path)

def save_atomic(path: str, df: pd.DataFrame):
    """Escritura atómica: escribe a temp y reemplaza."""
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="tasks_", suffix=".csv",
                                        dir=os.path.dirname(path) or ".")
    os.close(tmp_fd)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)
        return True, ""
    except Exception as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False, str(e)

def load_or_init(path: str) -> pd.DataFrame:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            df = pd.read_csv(path)
            return main.ensure_schema(df)
        except Exception:
            st.warning("No pude leer el CSV. Inicio con datos de ejemplo.")
    # si no existe o está vacío -> crear con sample_data
    df = main.sample_data()
    ok, err = save_atomic(path, df)
    if not ok:
        st.warning(f"No pude crear {path}: {err}")
    return df

# ---------------- Ruta del archivo (elección del usuario) ----------------
st.sidebar.title("📄 Archivo de datos")
ruta_input = st.sidebar.text_input("Ruta de tareas (CSV)", value="./tareas.txt")
TARGET_PATH = abspath(ruta_input)

existe = os.path.exists(TARGET_PATH)
puedo_leer = os.access(TARGET_PATH, os.R_OK) if existe else parent_writable(TARGET_PATH)
puedo_escribir = file_writable(TARGET_PATH)

st.sidebar.caption(f"Ruta absoluta: `{TARGET_PATH}`")
st.sidebar.write(
    f"**Existe:** {'✅' if existe else '❌'} | "
    f"**Lectura:** {'✅' if puedo_leer else '❌'} | "
    f"**Escritura:** {'✅' if puedo_escribir else '❌'}"
)

col_sb1, col_sb2 = st.sidebar.columns(2)
if col_sb1.button("📦 Crear/Inicializar", use_container_width=True):
    df_init = main.sample_data()
    ok, err = save_atomic(TARGET_PATH, df_init)
    if ok:
        st.sidebar.success("Archivo inicializado con sample_data().")
    else:
        st.sidebar.error(f"No se pudo crear el archivo: {err}")

if "df_full" not in st.session_state or st.session_state.get("loaded_from") != TARGET_PATH:
    # Cargar desde la ruta elegida
    st.session_state["df_full"] = load_or_init(TARGET_PATH)
    st.session_state["loaded_from"] = TARGET_PATH

# ---------------- Header ----------------
st.title("🚀 Gantt de Proyectos (Streamlit)")
if puedo_escribir:
    st.caption(f"Guardando cambios en: `{TARGET_PATH}` (escritura atómica activada)")
else:
    st.caption(f"**Solo lectura**: no hay permiso de escritura en `{TARGET_PATH}`. Editás en memoria pero NO se escribirá el archivo.")

# ---------------- Editor (fuente de verdad) ----------------
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
        update_mode=GridUpdateMode.MODEL_CHANGED,  # captura ediciones celda a celda
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=360,
    )

    edited_df = pd.DataFrame(grid["data"])
    selected = grid["selected_rows"]

    # Validar para consistencia interna
    validated_df, warns = main.validate(edited_df)
    if warns:
        st.info(" ; ".join(warns))

    # Actualizar en memoria
    st.session_state["df_full"] = validated_df

    # Guardar SI hay permiso
    autosave = st.checkbox("💾 Guardado automático en el archivo", value=True)
    if autosave and puedo_escribir:
        ok, err = save_atomic(TARGET_PATH, st.session_state["df_full"])
        if not ok:
            st.error(f"No se pudo guardar en archivo: {err}")
    elif autosave and not puedo_escribir:
        st.warning("No hay permiso de escritura. Se omitió el guardado automático.")

    c1, c2, c3, c4 = st.columns(4)
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
        if puedo_escribir:
            save_atomic(TARGET_PATH, st.session_state["df_full"])

    if c2.button("🗑️ Borrar seleccionadas"):
        if selected:
            sel_ids = [r.get("id") for r in selected if r.get("id") is not None]
            if sel_ids:
                st.session_state["df_full"] = st.session_state["df_full"][~st.session_state["df_full"]["id"].isin(sel_ids)]
                if puedo_escribir:
                    save_atomic(TARGET_PATH, st.session_state["df_full"])
            else:
                st.warning("Las filas seleccionadas no tienen ID aún. Editá una celda para autogenerar IDs y volvé a intentar.")
        else:
            st.warning("No hay filas seleccionadas.")

    if c3.button("🧬 Duplicar seleccionadas"):
        if selected:
            dup = pd.DataFrame(selected).copy()
            dup["id"] = None
            st.session_state["df_full"] = pd.concat([st.session_state["df_full"], dup], ignore_index=True)
            if puedo_escribir:
                save_atomic(TARGET_PATH, st.session_state["df_full"])
        else:
            st.warning("No hay filas seleccionadas.")

    if c4.button("💾 Guardar ahora en archivo"):
        if puedo_escribir:
            ok, err = save_atomic(TARGET_PATH, st.session_state["df_full"])
            if ok:
                st.success("Guardado en archivo realizado.")
            else:
                st.error(f"No se pudo guardar: {err}")
        else:
            st.error("Sin permiso de escritura en el archivo/ruta indicada.")

st.info(f"Archivo actual: `{TARGET_PATH}`")

# ---------------- Filtros de vista ----------------
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

# ---------------- Tabs de visualización ----------------
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

# ---------------- Export ----------------
st.subheader("📤 Exportar")
col1, col2 = st.columns(2)
with col1:
    csv_bytes = st.session_state["df_full"].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")
with col2:
    ics_text = main.to_ics(df_view if not df_view.empty else st.session_state["df_full"], cal_name="Proyectos")
    st.download_button("📅 Exportar ICS (vista)", data=ics_text.encode("utf-8"), file_name="gantt_calendar.ics", mime="text/calendar")

st.markdown("---")
st.caption("Hecho con ❤️ por Pipeta en Streamlit + Plotly + AgGrid")
