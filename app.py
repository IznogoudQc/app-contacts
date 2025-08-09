import os
import streamlit as st
from supabase import create_client, Client
from datetime import datetime

st.set_page_config(page_title="Contacts", page_icon="📇", layout="centered")

# --- Config Supabase depuis variables d'env ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xxx.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "ey...")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- Helpers ---
def set_session(user, access_token):
    st.session_state["user"] = user
    st.session_state["access_token"] = access_token

def get_authed_client() -> Client:
    token = st.session_state.get("access_token")
    if token:
        return create_client(
            SUPABASE_URL,
            SUPABASE_ANON_KEY,
            options={"headers": {"Authorization": f"Bearer {token}"}}
        )
    return supabase

def ensure_profile(client):
    # Crée la ligne profile si absente
    uid = st.session_state["user"].id
    email = st.session_state["user"].email
    res = client.table("profiles").select("id").eq("id", uid).single().execute()
    if not res.data:
        client.table("profiles").insert({"id": uid, "email": email}).execute()

def logout():
    st.session_state.clear()
    st.rerun()

# --- Auth ---
st.title("📇 Mes contacts (Supabase + Streamlit)")

if "user" not in st.session_state:
    st.session_state["user"] = None

if not st.session_state["user"]:
    tab_login, tab_signup = st.tabs(["Se connecter", "Créer un compte"])

    with tab_login:
        email = st.text_input("Email")
        pwd = st.text_input("Mot de passe", type="password")
        if st.button("Connexion"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                set_session(res.user, res.session.access_token)
                st.success("Connecté.")
                st.rerun()
            except Exception as e:
                st.error(f"Échec connexion: {e}")

    with tab_signup:
        email2 = st.text_input("Email (inscription)", key="email2")
        pwd2 = st.text_input("Mot de passe (inscription)", type="password", key="pwd2")
        if st.button("Créer mon compte"):
            try:
                supabase.auth.sign_up({"email": email2, "password": pwd2})
                st.success("Compte créé. Vérifie ta boîte email si la confirmation est activée.")
            except Exception as e:
                st.error(f"Échec inscription: {e}")
    st.stop()

# --- App (après login) ---
st.write(f"Bonjour **{st.session_state['user'].email}**")
st.button("Se déconnecter", on_click=logout)

client = get_authed_client()
ensure_profile(client)  # garantit la ligne dans profiles

st.subheader("➕ Ajouter un contact")
with st.form("add_contact", clear_on_submit=True):
    full_name = st.text_input("Nom complet", placeholder="Ex: Marie Tremblay")
    phone = st.text_input("Téléphone", placeholder="+1 514 ...")
    email_c = st.text_input("Email (contact)")
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Enregistrer")
    if submitted:
        if not full_name.strip():
            st.warning("Le nom est obligatoire.")
        else:
            uid = st.session_state["user"].id
            try:
                client.table("contacts").insert({
                    "user_id": uid,
                    "full_name": full_name.strip(),
                    "phone": phone.strip() or None,
                    "email": email_c.strip() or None,
                    "notes": notes.strip() or None
                }).execute()
                st.success("Contact ajouté.")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur insertion: {e}")

st.subheader("📜 Mes contacts")
try:
    uid = st.session_state["user"].id
    resp = client.table("contacts").select("*").eq("user_id", uid).order("created_at", desc=True).execute()
    rows = resp.data or []
    if not rows:
        st.info("Aucun contact pour l’instant.")
    else:
        for r in rows:
            ts = r.get("created_at")
            if isinstance(ts, str):
                ts = ts.replace("Z", "")
            st.markdown(
                f"**{r['full_name']}**  \n"
                f"📞 {r.get('phone','-')}   |   ✉️ {r.get('email','-')}  \n"
                f"🗒️ {r.get('notes','')}  \n"
                f"🕒 {ts}"
            )
            # Boutons d'action
            cols = st.columns(3)
            with cols[0]:
                if st.button("🗑️ Supprimer", key=f"del_{r['id']}"):
                    try:
                        client.table("contacts").delete().eq("id", r["id"]).execute()
                        st.success("Supprimé.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur suppression: {e}")
except Exception as e:
    st.error(f"Erreur lecture: {e}")

