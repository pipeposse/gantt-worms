# app.py
import streamlit as st
import pandas as pd
import main
import notify
st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

# ---------- Estado inicial ----------
if "df" not in st.session_state:
    st.session_state["df"] = main.fetch_tasks()

st.title("🚀 Gantt de Proyectos (Worms)")
st.caption("Edición nativa con `st.data_editor`. Guardá con 💾 y recargá desde Supabase cuando quieras.")

# ---------- Editor ----------
st.subheader("✏️ Editor de tareas")

df_edit = st.session_state["df"].copy()
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
    num_rows="dynamic",
    hide_index=True,
)

# ---------- Acciones ----------
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💾 Guardar (upsert)"):
        to_save = edited.drop(columns=["BORRAR"], errors="ignore")
        to_save = main.ensure_schema(to_save)

        ok = main.upsert_tasks(to_save)
        if ok:
            st.success("Cambios guardados en Supabase.")
            st.session_state["df"] = main.fetch_tasks()
        else:
            st.warning("No se guardó. Revisá el bloque de error mostrado arriba.")

with col2:
    if st.button("🗑️ Borrar marcadas"):
        ids = edited.loc[edited["BORRAR"] == True, "id"].dropna().astype(int).tolist()
        if ids:
            ok_del = main.delete_tasks(ids)
            if ok_del:
                st.success(f"Eliminadas {len(ids)} fila(s).")
                st.session_state["df"] = main.fetch_tasks()
            else:
                st.warning("No se pudo borrar (ver error arriba).")
        else:
            st.warning("No hay filas con ID marcadas para borrar.")

with col3:
    if st.button("🔄 Recargar desde Supabase"):
        st.session_state["df"] = main.fetch_tasks()
        st.info("Datos recargados.")

st.divider()

# ---------- Filtros de vista ----------
st.sidebar.title("🔎 Filtros")
df_view = st.session_state["df"].copy()

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

# ---------- Gantt ----------
st.subheader("📈 Gantt")
color_by = st.selectbox("Color por", ["progress","status","priority","project_name","rag"], index=0)
group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
fig = main.make_gantt(df_view, color_by=color_by, group_by_project=group_by_project)
st.plotly_chart(fig, use_container_width=True)

# ---------- Tabla simple ----------
st.subheader("📋 Tabla (vista filtrada)")
st.dataframe(df_view, use_container_width=True)

# ---------- Export ----------
st.subheader("📤 Exportar")
csv_bytes = st.session_state["df"].to_csv(index=False).encode("utf-8")
st.download_button("⬇️ CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")

st.caption("UI simple y robusta: st.data_editor + Supabase. Si querés, luego reactivamos AgGrid.")

st.divider()
st.subheader("📣 Espacio de notificación")

st.caption("Seleccioná las filas a notificar. Se enviará un correo al Owner y a los colaboradores, resolviendo emails desde la tabla `users` por nombre.")

# Tabla de selección (no modifica la DB)
df_notify = st.session_state["df"].copy()
df_notify.insert(0, "ENVIAR", False)

cols_min = [
    "ENVIAR", "id", "project_name", "task", "owner", "collaborators",
    "start", "end", "status", "priority", "progress"
]
present_cols = [c for c in cols_min if c in df_notify.columns]
df_notify = df_notify[present_cols]

notify_cfg = {
    "ENVIAR": st.column_config.CheckboxColumn("Enviar"),
    "id": st.column_config.NumberColumn("ID", disabled=True),
    "project_name": st.column_config.TextColumn("Proyecto", disabled=True),
    "task": st.column_config.TextColumn("Tarea", disabled=True),
    "owner": st.column_config.TextColumn("Owner", disabled=True),
    "collaborators": st.column_config.TextColumn("Colaboradores", disabled=True),
    "start": st.column_config.DateColumn("Inicio", format="YYYY-MM-DD", disabled=True),
    "end": st.column_config.DateColumn("Fin", format="YYYY-MM-DD", disabled=True),
    "status": st.column_config.TextColumn("Estado", disabled=True),
    "priority": st.column_config.TextColumn("Prioridad", disabled=True),
    "progress": st.column_config.NumberColumn("Progreso (%)", disabled=True),
}

pick = st.data_editor(
    df_notify,
    column_config=notify_cfg,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    key="notify_editor",
)

c1, c2 = st.columns([1,2])
with c1:
    preview_only = st.checkbox("Solo previsualizar (no enviar)", value=not notify.email_enabled())

selected = pick[pick["ENVIAR"] == True] if "ENVIAR" in pick else pd.DataFrame()

if st.button("✉️ Construir y (si aplica) enviar"):
    if selected.empty:
        st.warning("No marcaste ninguna fila.")
    else:
        # Preview del HTML
        html = notify.build_digest_html(selected)
        st.markdown("**Vista previa del correo:**", help="Esto es exactamente lo que recibirán los destinatarios.")
        st.markdown(html, unsafe_allow_html=True)

        # Resolver destinatarios
        recipients, unresolved = notify.resolve_recipients(selected)
        st.write(f"**Destinatarios resueltos ({len(recipients)}):**", recipients)
        if unresolved:
            st.warning(f"Nombres sin email en `users` ({len(unresolved)}): {unresolved}")

        # Envío real (si hay SMTP y no es solo preview)
        if not preview_only and notify.email_enabled() and recipients:
            res = notify.send_digest_for_rows(selected)
            st.success(f"Enviados: {res['sent']} / Destinatarios: {len(res['recipients'])}")
            if res["failed"]:
                st.error(f"Fallidos: {res['failed']}")
        else:
            st.info("Solo previsualización (o SMTP no configurado). No se enviaron correos.")


# ========== Mapeo de destinatarios por tarea ==========
st.divider()
st.subheader("📬 Mapeo de destinatarios por tarea")

# Intentamos leer las vistas SQL si existen; si no, calculamos el mapeo en Python.
sb = main.get_sb()

def _safe_query(table_name: str):
    if sb is None:
        return pd.DataFrame()
    try:
        res = sb.table(table_name).select("*").order("project_name").order("task_id").execute()
        return pd.DataFrame(res.data or [])
    except Exception:
        return pd.DataFrame()

df_sum = _safe_query("tasks_recipients_summary")

if not df_sum.empty:
    st.dataframe(df_sum, use_container_width=True)
    with st.expander("Ver detalle por destinatario (expandido)", expanded=False):
        df_exp = _safe_query("tasks_recipients_expanded")
        st.dataframe(df_exp, use_container_width=True)
        st.caption("resolved = true => email resuelto en users. Si es false, añadí el nombre a la tabla users.")
else:
    # --------- Fallback: resolver en la app sin vistas SQL ---------
    st.info("Mostrando mapeo calculado en la app (si querés vistas SQL, ejecutá los scripts propuestos).")

    # 1) Cargar usuarios activos
    users_df = pd.DataFrame()
    if sb is not None:
        try:
            ures = sb.table("users").select("full_name,email,is_active").execute()
            users_df = pd.DataFrame(ures.data or [])
            if not users_df.empty and "is_active" in users_df.columns:
                users_df = users_df[users_df["is_active"].fillna(True)]
        except Exception:
            users_df = pd.DataFrame()

    # 2) Normalizar nombre -> email
    def _norm_name(s):
        if s is None:
            return None
        s = str(s).strip()
        if not s:
            return None
        return " ".join(s.split()).lower()

    name_to_email = {}
    if not users_df.empty:
        for _, u in users_df.iterrows():
            nn = _norm_name(u.get("full_name"))
            if nn:
                name_to_email[nn] = u.get("email")

    # 3) Helpers
    def _split_csv(s):
        if s is None:
            return []
        s = str(s).strip()
        if not s:
            return []
        return [p.strip() for p in s.split(",") if p.strip()]

    # 4) Construir mapeo usando el DF actual (tareas cargadas en la app)
    rows = []
    for _, r in st.session_state["df"].iterrows():
        owner_email = name_to_email.get(_norm_name(r.get("owner")))
        collabs = _split_csv(r.get("collaborators"))
        collab_emails = sorted({
            name_to_email.get(_norm_name(x))
            for x in collabs
            if name_to_email.get(_norm_name(x))
        })
        unresolved = sorted({
            x for x in collabs
            if _norm_name(x) not in name_to_email
        })
        rows.append({
            "task_id": r.get("id"),
            "project_name": r.get("project_name"),
            "task": r.get("task"),
            "owner_email": owner_email,
            "collaborator_emails": ", ".join(collab_emails) if collab_emails else None,
            "collaborator_unresolved_names": ", ".join(unresolved) if unresolved else None
        })

    map_df = pd.DataFrame(rows)
    st.dataframe(map_df, use_container_width=True)


st.divider()
st.subheader("🔧 Test SMTP")
test_to = st.text_input("Enviar mail de prueba a:", value="tu-email@gmail.com")
if st.button("Enviar prueba"):
    if not notify.email_enabled():
        st.error("Faltan EMAIL_* en secrets.")
    else:
        ok = notify.send_email(
            to_email=test_to,
            subject="[Gantt] Prueba SMTP",
            html_body="<b>¡Funciona!</b> Esta es una prueba desde Streamlit."
        )
        st.success("Enviado ✅" if ok else "Falló ❌")
