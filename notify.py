# notify.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import re
import smtplib
from email.message import EmailMessage

import pandas as pd
import streamlit as st
import main  # usamos la conexión y utilidades del módulo original


# ------------------ Helpers de normalización ------------------
def _norm_name(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    # normalizamos espacios y minúsculas (sin quitar tildes para no romper nombres)
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def _split_collaborators(csv_or_list: Any) -> List[str]:
    # reutilizamos el parser del main si existiera, si no, fallback simple
    try:
        parts = main._to_list_from_csv(csv_or_list)  # type: ignore[attr-defined]
        return parts or []
    except Exception:
        if csv_or_list is None:
            return []
        s = str(csv_or_list).strip()
        if not s:
            return []
        return [p.strip() for p in s.split(",") if p.strip()]


# ------------------ Lectura de usuarios (name -> email) ------------------
@st.cache_data(show_spinner=False, ttl=60)
def fetch_user_index() -> Dict[str, Dict[str, str]]:
    """
    Devuelve un índice {nombre_normalizado: {full_name, email, id}} desde la tabla users.
    Si no hay conexión o no existe la tabla, devuelve dict vacío.
    """
    sb = main.get_sb()
    if sb is None:
        return {}
    try:
        res = sb.table("users").select("id, full_name, email").eq("is_active", True).execute()
        rows = res.data or []
        idx: Dict[str, Dict[str, str]] = {}
        for r in rows:
            n = _norm_name(r.get("full_name"))
            if not n:
                continue
            idx[n] = {
                "id": r.get("id"),
                "full_name": r.get("full_name") or "",
                "email": r.get("email") or "",
            }
        return idx
    except Exception:
        return {}


# ------------------ Resolución de destinatarios ------------------
def resolve_recipients(df_rows: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    A partir de filas de tasks (owner y collaborators en texto),
    retorna (emails_unicos, nombres_no_resueltos).
    """
    user_idx = fetch_user_index()
    emails: List[str] = []
    unresolved: List[str] = []

    for _, r in df_rows.iterrows():
        # Owner
        owner_name = r.get("owner")
        nm = _norm_name(owner_name) if owner_name else None
        if nm and nm in user_idx:
            mail = user_idx[nm]["email"]
            if mail and mail not in emails:
                emails.append(mail)
        elif owner_name:
            unresolved.append(str(owner_name))

        # Colaboradores
        for col_name in _split_collaborators(r.get("collaborators")):
            nm2 = _norm_name(col_name)
            if nm2 and nm2 in user_idx:
                mail2 = user_idx[nm2]["email"]
                if mail2 and mail2 not in emails:
                    emails.append(mail2)
            else:
                unresolved.append(str(col_name))

    # limpiar duplicados de "unresolved" manteniendo orden
    seen = set()
    unresolved_unique = []
    for n in unresolved:
        key = _norm_name(n) or n
        if key in seen:
            continue
        seen.add(key)
        unresolved_unique.append(n)

    return emails, unresolved_unique


# ------------------ Construcción del email ------------------
def build_digest_html(df_rows: pd.DataFrame) -> str:
    """
    Construye un HTML con los campos claves de las filas seleccionadas.
    """
    cols = [
        "id", "project_name", "task", "details", "owner", "collaborators",
        "start", "end", "status", "priority", "progress", "rag", "external_link"
    ]
    present_cols = [c for c in cols if c in df_rows.columns]

    # tabla html
    rows_html = []
    for _, r in df_rows.iterrows():
        tds = []
        for c in present_cols:
            v = r.get(c)
            if pd.isna(v):
                v = ""
            if c in ("start", "end") and str(v):
                try:
                    v = pd.to_datetime(v).date().isoformat()
                except Exception:
                    v = str(v)
            tds.append(f"<td style='padding:6px;border:1px solid #ddd'>{v}</td>")
        rows_html.append("<tr>" + "".join(tds) + "</tr>")

    thead = "".join([f"<th style='text-align:left;padding:6px;border-bottom:2px solid #333'>{c}</th>" for c in present_cols])
    tbody = "\n".join(rows_html)
    html = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial">
      <h2>📌 Resumen de tareas seleccionadas</h2>
      <table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;font-size:14px">
        <thead><tr>{thead}</tr></thead>
        <tbody>{tbody}</tbody>
      </table>
      <p style="color:#666;margin-top:12px">Enviado automáticamente desde Gantt Worms.</p>
    </div>
    """
    return html


# ------------------ Envío (SMTP) ------------------
def email_enabled() -> bool:
    return bool(st.secrets.get("EMAIL_HOST") and st.secrets.get("EMAIL_USER") and st.secrets.get("EMAIL_PASSWORD"))

def send_email(to_email: str, subject: str, html_body: str) -> bool:
    try:
        host = st.secrets["EMAIL_HOST"]
        port = int(st.secrets.get("EMAIL_PORT", 587))
        user = st.secrets["EMAIL_USER"]
        pwd = st.secrets["EMAIL_PASSWORD"]
        sender = st.secrets.get("EMAIL_FROM", user)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.set_content("Este aviso requiere un cliente de correo HTML.")
        msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, pwd)
            server.send_message(msg)
        return True
    except Exception as e:
        st.warning(f"No se pudo enviar email a {to_email}. Detalle: {e}")
        return False


# ------------------ Orquestación ------------------
def send_digest_for_rows(df_rows: pd.DataFrame) -> Dict[str, Any]:
    """
    Resuelve destinatarios y envía un único digest a cada uno (mismo contenido).
    Retorna un resumen: {'sent': int, 'failed': [(email, error?)], 'unresolved': [nombres]}
    """
    # asegurar formato (por si viene desde un editor)
    df_norm = main.ensure_schema(df_rows)

    # destinatarios
    recipients, unresolved = resolve_recipients(df_norm)

    # cuerpo y subject
    html = build_digest_html(df_norm)
    qty = len(df_norm)
    first_proj = df_norm["project_name"].dropna().astype(str).head(1).tolist()
    title_hint = f" · {first_proj[0]}" if first_proj else ""
    subject = f"[Gantt] Resumen de {qty} tarea(s){title_hint}"

    results = {"sent": 0, "failed": [], "unresolved": unresolved, "recipients": recipients}

    if not recipients:
        return results

    if not email_enabled():
        # si no hay SMTP configurado, no intentamos enviar
        return results

    # enviar uno por uno
    ok_count = 0
    failed: List[Tuple[str, str]] = []
    for em in recipients:
        try:
            ok = send_email(em, subject, html)
            if ok:
                ok_count += 1
            else:
                failed.append((em, "smtp send returned False"))
        except Exception as e:
            failed.append((em, str(e)))

    results["sent"] = ok_count
    results["failed"] = failed
    return results
