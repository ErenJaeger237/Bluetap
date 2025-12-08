import streamlit as st
import time
import os
from client import client_cli as client

# Configuration
GATEWAY = "localhost:50051"

st.set_page_config(page_title="Bluetap Cloud", page_icon="☁️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .reportview-container { background: #f0f2f6 }
    .sidebar .sidebar-content { background: #ffffff }
    h1 { color: #2e86de; }
    .stButton>button { width: 100%; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/000000/cloud-storage.png", width=100)
    st.title("Bluetap System")
    st.markdown("---")
    st.subheader("📡 Status")
    st.success("System Online")
    st.caption(f"Gateway: {GATEWAY}")
    
    if st.session_state.get('token'):
        st.write(f"👤 **{st.session_state.get('login_user')}**")
        if st.button("Logout"):
            st.session_state['token'] = None
            st.session_state['otp_sent'] = False
            for key in list(st.session_state.keys()):
                if key.startswith("ready_"):
                    del st.session_state[key]
            st.rerun()

# --- MAIN APP LOGIC ---

if 'token' not in st.session_state:
    st.session_state['token'] = None
if 'otp_sent' not in st.session_state:
    st.session_state['otp_sent'] = False

if not st.session_state['token']:
    # === LOGIN SCREEN ===
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Bluetap Secure Cloud")
        st.divider()

        if not st.session_state['otp_sent']:
            with st.form("login_form"):
                st.subheader("Login / Register")
                username = st.text_input("Username", placeholder="e.g. alice")
                email = st.text_input("Email (Required for new users)", placeholder="you@gmail.com")
                submit = st.form_submit_button("Send Access Code")
                
                if submit:
                    if not username:
                        st.error("Username is required.")
                    else:
                        with st.spinner("Contacting Gateway..."):
                            ok, msg = client.login(GATEWAY, username, email)
                        if ok:
                            st.session_state['otp_sent'] = True
                            st.session_state['login_user'] = username
                            st.session_state['login_email'] = email
                            st.success(f"✅ {msg}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Connection Failed: {msg}")
        else:
            st.info(f"📧 Code sent to **{st.session_state.get('login_email') or 'Server Logs'}**")
            otp = st.text_input("Enter 6-digit Code", max_chars=6)
            if st.button("Verify & Enter"):
                ok, token = client.verify_otp_and_get_token(GATEWAY, st.session_state['login_user'], otp)
                if ok:
                    st.session_state['token'] = token
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Code.")
            if st.button("Back"):
                st.session_state['otp_sent'] = False
                st.rerun()

else:
    # === DASHBOARD SCREEN ===
    client.set_token(st.session_state['token'])
    st.title(f"📂 {st.session_state['login_user']}'s Cloud Drive")
    
    # Upload
    with st.container():
        uploaded_file = st.file_uploader("Upload File", label_visibility="collapsed")
        if uploaded_file is not None:
            if st.button("Start Upload"):
                temp_path = f"temp_{uploaded_file.name}"
                with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                def update_progress(chunk_id, fname, node):
                    status_text.text(f"🚀 Sending chunk {chunk_id} to {node}...")
                    progress_bar.progress(min(100, (chunk_id + 1) * 10))

                ok, msg = client.put_file(GATEWAY, temp_path, progress_callback=update_progress)
                if ok:
                    status_text.text("✅ Complete!")
                    progress_bar.progress(100)
                    time.sleep(1)
                    os.remove(temp_path)
                    st.rerun()
                else:
                    st.error(f"Upload failed: {msg}")

    st.divider()

    # File List
    files = client.list_files(GATEWAY)
    if not files:
        st.info("No files found.")
    else:
        c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
        c1.markdown("**Name**")
        c2.markdown("**Size**")
        c3.markdown("**Date**")
        c4.markdown("**Action**")
        
        for f in files:
            col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
            col1.write(f"📄 {f.filename}")
            col2.write(f"{f.filesize} B")
            col3.write(f.created_at)
            
            with col4:
                retr_key = f"btn_retr_{f.upload_id}"
                ready_key = f"ready_{f.upload_id}"
                
                if st.session_state.get(ready_key):
                    local_path = f"downloaded_{f.filename}"
                    if os.path.exists(local_path):
                        with open(local_path, "rb") as fh:
                            st.download_button("💾 Save", fh, file_name=f.filename, key=f"dl_{f.upload_id}")
                else:
                    if st.button("☁️ Retrieve", key=retr_key):
                        with st.spinner("Fetching..."):
                            out_path = f"downloaded_{f.filename}"
                            ok, msg = client.download_file(GATEWAY, f.filename, out_path)
                            if ok:
                                st.session_state[ready_key] = True
                                st.rerun()
                            else:
                                st.error(f"{msg}")  # <--- SHOWS REAL ERROR NOW
            st.markdown("---")