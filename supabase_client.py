from supabase import create_client, Client
import streamlit as st

# SIN decorador
def get_supabase_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)



if __name__ == "__main__":
    client = get_supabase_client()
    try:
        res = client.table("productos").select("*").limit(1).execute()
        if res.data:
            print("✅ Conexión exitosa con Supabase.")
            print("Primer registro:", res.data[0])
        else:
            print("⚠️ Conexión establecida, pero tabla vacía.")
    except Exception as e:
        print("❌ Error al conectar con Supabase:", e)
