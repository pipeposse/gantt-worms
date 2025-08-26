# app.py
import streamlit as st
import pandas as pd
import main

st.set_page_config(page_title="Gantt Proyectos (Supabase)", layout="wide", page_icon="📊")

# ---------- Estado inicial ----------
if "df" not in st.session_state:
    st.session_state["df"] = main.fetch_tasks()

st.title("🚀 Gantt de Proyectos (Worms)")
st.caption("Editor simple + panel de personas (Owner y Colaboradores) conectado a la tabla users.")

# ---------- Editor (campos de tasks) ----------
st.subheader("✏️ Editor de tareas")

df_edit = st.session_state["df"].copy()
df_edit.insert(0, "BORRAR", False)

config = {
    "id": st.column_config.NumberColumn("ID", help="Autogenerado", disabled=True),
    "project_name": st.column_config.TextColumn("Proyecto"),
    "task": st.column_config.TextColumn("Tarea"),
    "details": st.column_config.TextColumn("Detalles"),
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
    # display-only desde la view:
    "owner_name": st.column_config.TextColumn("Owner (nombre)", disabled=True),
    "collaborators_names": st.column_config.TextColumn("Colaboradores (nombres)", disabled=True),
}

edited = st.data_editor(
    df_edit,
    column_config=config,
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
)

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("💾 Guardar (upsert)"):
        to_save = edited.drop(columns=["BORRAR", "owner_name", "collaborators_names"], errors="ignore")
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
    if st.button("🔄 Recargar"):
        st.session_state["df"] = main.fetch_tasks()
        st.info("Datos recargados.")

st.divider()

# ---------- Personas (Owner + Colaboradores) ----------
st.subheader("👥 Asignar personas")

df_now = st.session_state["df"]
if df_now.empty:
    st.info("No hay tareas aún.")
else:
    # elegir tarea
    options = []
    for _, r in df_now.iterrows():
        label = f"{int(r['id'])} · {r['project_name']} · {r['task']}"
        options.append((int(r["id"]), label))
    task_id = st.selectbox("Elegí una tarea", options=[o[0] for o in options],
                           format_func=lambda x: dict(options)[x])

    # cargar users
    users = main.fetch_users(active_only=True)
    if users.empty:
        st.warning("No hay usuarios en tabla users.")
    else:
        user_map = {row["id"]: f"{row['full_name']} · {row['email']}" for _, row in users.iterrows()}
        user_ids = list(user_map.keys())

        # owner actual
        cur_owner = df_now.loc[df_now["id"] == task_id, "owner_name"].iloc[0]
        cur_owner_id = df_now.loc[df_now["id"] == task_id, "owner_user_id"].iloc[0]

        st.write(f"Owner actual: **{cur_owner or '—'}**")
        sel_owner = st.selectbox(
            "Nuevo owner (opcional)",
            options=[None] + user_ids,
            format_func=lambda x: "— (sin owner)" if x is None else user_map.get(x, str(x)),
            index=(0 if pd.isna(cur_owner_id) or cur_owner_id is None else [None]+user_ids.index(cur_owner_id)+1)
            if user_ids else 0
        )

        # colaboradores actuales
        current_collab_ids = main.get_task_collaborators(task_id)
        sel_collabs = st.multiselect(
            "Colaboradores",
            options=user_ids,
            default=current_collab_ids,
            format_func=lambda x: user_map.get(x, str(x)),
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Guardar personas"):
                ok1 = main.set_task_owner(task_id, sel_owner)
                ok2 = main.replace_task_collaborators(task_id, sel_collabs)
                if ok1 and ok2:
                    st.success("Owner y colaboradores actualizados.")
                    st.session_state["df"] = main.fetch_tasks()
                else:
                    st.warning("No se pudieron actualizar todos los datos (ver mensajes arriba).")
        with c2:
            if main.email_enabled():
                if st.button("✉️ Avisar al owner (email)"):
                    # tomar email del owner elegido (o actual si no cambiaste)
                    owner_id = sel_owner or cur_owner_id
                    if owner_id:
                        email = users.loc[users["id"] == owner_id, "email"].values
                        if len(email):
                            task_row = main.get_task(task_id) or {}
                            subject = f"[Gantt] Tarea asignada: {task_row.get('task','-')} ({task_row.get('project_name','-')})"
                            html = f"""
                            <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial">
                              <h2>📌 Tarea asignada</h2>
                              <p><b>Proyecto:</b> {task_row.get('project_name','-')}<br/>
                                 <b>Tarea:</b> {task_row.get('task','-')}<br/>
                                 <b>Inicio:</b> {task_row.get('start_date','-')} &nbsp; <b>Fin:</b> {task_row.get('end_date','-')}</p>
                              <hr/><p>Gantt Worms</p>
                            </div>
                            """
                            sent = main.send_email(email[0], subject, html)
                            if sent:
                                st.success(f"Email enviado a {email[0]}")
                            else:
                                st.warning("No se pudo enviar el email.")
                    else:
                        st.info("Seleccioná un owner para enviar correo.")

st.divider()

# ---------- Gantt ----------
st.subheader("📈 Gantt")
df_view = st.session_state["df"].copy()
color_by = st.selectbox("Color por", ["progress","status","priority","project_name","rag"], index=0)
group_by_project = st.checkbox("Agrupar por proyecto (eje Y)", value=True)
fig = main.make_gantt(df_view, color_by=color_by, group_by_project=group_by_project)
st.plotly_chart(fig, use_container_width=True)

# ---------- Tabla ----------
st.subheader("📋 Tabla (vista actual)")
st.dataframe(df_view, use_container_width=True)

# ---------- Export ----------
st.subheader("📤 Exportar")
csv_bytes = st.session_state["df"].to_csv(index=False).encode("utf-8")
st.download_button("⬇️ CSV (todo)", data=csv_bytes, file_name="gantt_tasks.csv", mime="text/csv")

st.caption("Owner y colaboradores desde tabla users; tareas en tasks; relación en task_collaborators.")
