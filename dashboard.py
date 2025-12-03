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
    .success-msg { color: green; font-weight: bold; }
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
            # Clear cache
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
    # ==========================
    # 🔐 LOGIN / REGISTER SCREEN
    # ==========================
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("🔐 Bluetap Secure Cloud")
        st.markdown("Access your distributed files securely.")
        st.divider()

        # Step 1: User Request
        if not st.session_state['otp_sent']:
            with st.form("login_form"):
                st.subheader("Login or Register")
                username = st.text_input("Username", placeholder="e.g. alice")
                email = st.text_input("Email (Required for new users)", placeholder="you@gmail.com")
                submit = st.form_submit_button("Send Access Code")
                
                if submit:
                    if not username:
                        st.error("Username is required.")
                    else:
                        with st.spinner("Contacting Gateway..."):
                            # CALL GATEWAY with EMAIL
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

        # Step 2: OTP Verification
        else:
            st.info(f"📧 An OTP code has been sent to **{st.session_state.get('login_email') or 'Server Logs'}**")
            st.caption("Please check your inbox (or the server terminal if email is not configured).")
            
            otp = st.text_input("Enter the 6-digit Code", max_chars=6)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Verify & Enter"):
                    with st.spinner("Verifying..."):
                        ok, token = client.verify_otp_and_get_token(GATEWAY, st.session_state['login_user'], otp)
                        
                    if ok:
                        st.session_state['token'] = token
                        st.success("Welcome back!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ Invalid Code. Please try again.")
            
            with col_b:
                if st.button("Cancel / Back"):
                    st.session_state['otp_sent'] = False
                    st.rerun()

else:
    # ==========================
    # ☁️ DASHBOARD SCREEN
    # ==========================
    client.set_token(st.session_state['token'])
    
    st.title(f"📂 {st.session_state['login_user']}'s Cloud Drive")
    
    # --- UPLOAD SECTION ---
    with st.container():
        st.markdown("### ⬆️ Upload File")
        uploaded_file = st.file_uploader("Drag and drop files here", label_visibility="collapsed")
        
        if uploaded_file is not None:
            if st.button("Start Upload"):
                # Save temp
                temp_path = f"temp_{uploaded_file.name}"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Progress UI
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(chunk_id, fname, node):
                    status_text.text(f"🚀 Replicating chunk {chunk_id} to Node ({node})...")
                    progress_bar.progress(min(100, (chunk_id + 1) * 10))

                # Do Upload
                ok, msg = client.put_file(GATEWAY, temp_path, progress_callback=update_progress)
                
                if ok:
                    progress_bar.progress(100)
                    status_text.text("✅ Replication Complete!")
                    st.balloons()
                    time.sleep(1)
                    os.remove(temp_path)
                    st.rerun()
                else:
                    st.error(f"Upload failed: {msg}")

    st.divider()

    # --- FILE LIST SECTION ---
    st.markdown("### 🗃️ Your Files")
    
    # Fetch list
    files = client.list_files(GATEWAY)
    
    if not files:
        st.info("Your drive is empty. Upload a file above!")
    else:
        # Header Row
        c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
        c1.markdown("**Name**")
        c2.markdown("**Size**")
        c3.markdown("**Date**")
        c4.markdown("**Action**")
        
        for f in files:
            with st.container():
                col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
                col1.write(f"📄 {f.filename}")
                col2.write(f"{f.filesize} B")
                col3.write(f.created_at)
                
                with col4:
                    # Unique keys for every button
                    retr_key = f"btn_retr_{f.upload_id}"
                    ready_key = f"ready_{f.upload_id}"
                    
                    if st.session_state.get(ready_key):
                        # Show Download Button
                        local_path = f"downloaded_{f.filename}"
                        if os.path.exists(local_path):
                            with open(local_path, "rb") as fh:
                                st.download_button(
                                    label="💾 Download",
                                    data=fh,
                                    file_name=f.filename,
                                    mime="application/octet-stream",
                                    key=f"dl_{f.upload_id}"
                                )
                    else:
                        # Show Retrieve Button
                        if st.button("☁️ Retrieve", key=retr_key):
                            with st.spinner("Fetching from grid..."):
                                out_path = f"downloaded_{f.filename}"
                                ok, msg = client.download_file(GATEWAY, f.filename, out_path)
                                if ok:
                                    st.session_state[ready_key] = True
                                    st.rerun()
                                else:
                                    st.error("Error fetching file")
                st.markdown("---")