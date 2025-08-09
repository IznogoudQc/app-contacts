import os
from datetime import datetime
import streamlit as st
from supabase import create_client, Client, ClientOptions

# ----------------------------
# Configuration générale
# ----------------------------
st.set_page_config(page_title="Mes contacts (Supabase + Streamlit)", page_icon="📇", layout="centered")

# Récupère les secrets (Streamlit Cloud) avec fallback sur variables d'env
def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]  # type: ignore[attr-defined]
    except Exception:
        return os.environ.get(key, default)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("SUPABASE_URL / SUPABASE_ANON_KEY manquants (Settings → Secrets).")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ----------------------------
# Helpers session
# ----------------------------
def set_session(user, access_token: str | None):
    st.session_state["user"] = user
    st.session_state["access_token"] = access_token

def get_authed_client() -> Client:
    """Retourne un client Supabase qui porte le token utilisateur (pour RLS)."""
    token = st.session_state.get("access_token")
    if token:
        return create_client(
            SUPABASE_URL,
            SUPABASE_ANON_KEY,
            options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
    return supabase

def ensure_profile(client: Client):
    """Crée la ligne dans public.profiles si absente (lié à auth.uid())."""
    uid = st.session_state["user"].id
    email = st.session_state["user"].email
    try:
        res = client.table("profiles").select("id").eq("id", uid).single().execute()
        if not res.data:
            client.table("profiles").insert({"id": uid, "email": email}).execute()
    except Exception:
        # Si .single() lève (not found), on tente l'insert
        try:
            client.table("profiles").insert({"id": uid, "email": email}).execute()
        except Exception:
            pass

def logout():
    st.session_state.clear()
    st.rerun()

# ----------------------------
# UI - Titre
# ----------------------------
st.title("📇 Mes contacts (Supabase + Streamlit)")

# ----------------------------
# Auth
# ----------------------------
if "user" not in st.session_state:
    st.session_state["user"] = None
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None

if not st.session_state["user"]:
    tabs = st.tabs(["Se connecter", "Créer un compte"])

    with tabs[0]:
        email = st.text_input("Email")
        pwd = st.text_input("Mot de passe", type="password")
        if st.button("Connexion", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": email.strip(), "password": pwd})
                set_session(res.user, res.session.access_token if res.session else None)
                st.success("Connecté.")
                st.rerun()
            except Exception as e:
                st.error(f"Échec connexion: {e}")

    with tabs[1]:
        email2 = st.text_input("Email (inscription)", key="email2")
        pwd2 = st.text_input("Mot de passe (inscription)", type="password", key="pwd2")
        if st.button("Créer mon compte", use_container_width=True):
            try:
                supabase.auth.sign_up({"email": email2.strip(), "password": pwd2})
                st.success("Compte créé. Vérifie ta boîte email si la confirmation est activée.")
            except Exception as e:
                st.error(f"Échec inscription: {e}")

    st.stop()

# ----------------------------
# App (après login)
# ----------------------------
st.write(f"Bonjour **{st.session_state['user'].email}**")
st.button("Se déconnecter", on_click=logout, type="secondary")

client = get_authed_client()
ensure_profile(client)

st.divider()
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
            try:
                client.table("contacts").insert({
                    "user_id": st.session_state["user"].id,
                    "full_name": full_name.strip(),
                    "phone": phone.strip() or None,
                    "email": email_c.strip() or None,
                    "notes": notes.strip() or None
                }).execute()
                st.success("Contact ajouté.")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur insertion: {e}")

st.divider()
st.subheader("📜 Mes contacts")

# Lecture
try:
    uid = st.session_state["user"].id
    resp = client.table("contacts").select("*").eq("user_id", uid).order("created_at", desc=True).execute()
    rows = resp.data or []
    if not rows:
        st.info("Aucun contact pour l’instant.")
    else:
        for r in rows:
            ts = r.get("created_at")
            ts_txt = ts.replace("Z", "") if isinstance(ts, str) else str(ts)

            with st.expander(f"👤 {r['full_name']}  —  {ts_txt}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**Téléphone :** {r.get('phone','-')}")
                    st.write(f"**Email :** {r.get('email','-')}")
                    if r.get("notes"):
                        st.write(f"**Notes :** {r['notes']}")

                # Edition rapide
                with st.form(f"edit_{r['id']}"):
                    st.markdown("**Modifier**")
                    e_full = st.text_input("Nom", value=r["full_name"], key=f"e_full_{r['id']}")
                    e_phone = st.text_input("Téléphone", value=r.get("phone") or "", key=f"e_phone_{r['id']}")
                    e_email = st.text_input("Email", value=r.get("email") or "", key=f"e_email_{r['id']}")
                    e_notes = st.text_area("Notes", value=r.get("notes") or "", key=f"e_notes_{r['id']}")
                    colu1, colu2 = st.columns(2)
                    if colu1.form_submit_button("💾 Sauvegarder", use_container_width=True):
                        try:
                            client.table("contacts").update({
                                "full_name": e_full.strip(),
                                "phone": e_phone.strip() or None,
                                "email": e_email.strip() or None,
                                "notes": e_notes.strip() or None
                            }).eq("id", r["id"]).execute()
                            st.success("Modifié.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur modification: {e}")
                    if colu2.form_submit_button("🗑️ Supprimer", use_container_width=True):
                        try:
                            client.table("contacts").delete().eq("id", r["id"]).execute()
                            st.success("Supprimé.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur suppression: {e}")
except Exception as e:
    st.error(f"Erreur lecture: {e}")
