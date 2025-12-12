import streamlit as st
import time
import os
import sys
import datetime

# Add the client directory to the path if running directly
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client import client_cli as client

# Configuration
GATEWAY = "localhost:50051"

st.set_page_config(page_title="Bluetap Cloud Storage", page_icon="☁️", layout="wide")

# --- CUSTOM CSS & INITIAL SETUP ---
st.markdown("""
<style>
    /* Main container background */
    .stApp {
        background-color: #f8f9fa;
    }
    /* Button styling for a modern look */
    .stButton>button {
        border-radius: 8px;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        box-shadow: 0 4px 10px rgba(46, 134, 222, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if 'token' not in st.session_state: st.session_state['token'] = None
if 'otp_sent' not in st.session_state: st.session_state['otp_sent'] = False
if 'login_user' not in st.session_state: st.session_state['login_user'] = None
if 'current_view' not in st.session_state: st.session_state['current_view'] = 'files'


# --- SIDEBAR ---
def render_sidebar():
    with st.sidebar:
        st.image("https://placehold.co/100x100/2e86de/ffffff?text=BT", width=100)
        st.title("Bluetap Cloud")
        st.markdown("---")

        if st.session_state.get('token'):
            st.subheader("User Session")
            st.info(f"👤 **{st.session_state.get('login_user')}**")
            
            st.markdown("---")
            st.subheader("Navigation")
            
            # Simple Navigation Buttons
            if st.button("📂 My Files", use_container_width=True):
                st.session_state['current_view'] = 'files'
                st.rerun()
            
            st.markdown("---")
            
            # Logout Button
            if st.button("🚪 Logout", use_container_width=True, help="End your current session"):
                st.session_state['token'] = None
                st.session_state['otp_sent'] = False
                for key in list(st.session_state.keys()):
                    if key.startswith("ready_"): del st.session_state[key]
                st.rerun()
        else:
            st.caption("Please log in to access storage services.")

# --- UI Components ---

def render_login():
    """Handles the user login/authentication flow."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #2e86de;'>🔑 Secure Login</h1>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center; color: #6c757d;'>Access your decentralized cloud storage.</div>", unsafe_allow_html=True)
        st.divider()

        if not st.session_state['otp_sent']:
            with st.form("login_form", clear_on_submit=False):
                st.subheader("Login / Register")
                username = st.text_input("Username", placeholder="e.g. alice", key="form_username")
                email = st.text_input("Email", placeholder="you@gmail.com (Required for new users)", key="form_email")
                submit = st.form_submit_button("Send Access Code 📧", type="primary")
                
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
                            st.success(f"✅ Code sent! {msg}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Connection Failed: {msg}")
        else:
            st.info(f"A 6-digit OTP has been requested for **{st.session_state.get('login_user')}**.")
            otp = st.text_input("Enter 6-digit Code", max_chars=6)
            
            col_verify, col_back = st.columns(2)
            with col_verify:
                if st.button("Verify & Login", type="primary"):
                    ok, token = client.verify_otp_and_get_token(GATEWAY, st.session_state['login_user'], otp)
                    if ok:
                        st.session_state['token'] = token
                        st.success("Welcome back! Loading dashboard...")
                        st.rerun()
                    else:
                        st.error("❌ Invalid Code. Please check your logs/email.")
            with col_back:
                 if st.button("← Go Back"):
                    st.session_state['otp_sent'] = False
                    st.session_state['login_user'] = None
                    st.rerun()

def render_dashboard():
    """Renders the main file management view."""
    client.set_token(st.session_state['token'])
    st.markdown(f"<h1 style='color: #2e86de;'>☁️ Welcome, {st.session_state['login_user']}</h1>", unsafe_allow_html=True)
    st.caption(f"Gateway Status: Online at {GATEWAY}")
    st.divider()

    # --- UPLOAD SECTION ---
    with st.container(border=True):
        st.subheader("Upload New File")
        uploaded_file = st.file_uploader("Select a file for upload:", label_visibility="collapsed")
        
        if uploaded_file is not None:
            if st.button(f"⬆️ Upload '{uploaded_file.name}'", type="primary", use_container_width=True):
                # 1. Save file to temporary path
                temp_path = f"temp_{uploaded_file.name}"
                try:
                    with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
                except Exception as e:
                    st.error(f"Failed to save file locally: {e}")
                    return

                # 2. Upload Logic
                progress_bar = st.progress(0, text="Initializing upload...")
                status_text = st.empty()
                
                def update_progress(chunk_id, fname, node):
                    # Progress calculation is simple for demo
                    status_text.text(f"🚀 Sending chunk {chunk_id} to {node}...")
                    progress_bar.progress(min(100, (chunk_id + 1) * 10))

                ok, msg = client.put_file(GATEWAY, temp_path, progress_callback=update_progress)
                
                # 3. Finalize
                if ok:
                    status_text.text(f"✅ Upload Complete: {msg}")
                    progress_bar.progress(100)
                    time.sleep(1)
                    st.success(f"File '{uploaded_file.name}' uploaded successfully.")
                else:
                    status_text.text("Upload Failed")
                    st.error(f"Upload failed: {msg}")
                
                # Cleanup local temporary file
                if os.path.exists(temp_path): os.remove(temp_path)
                
                # Force reload file list
                if ok: st.rerun()


    st.markdown("---")
    
    # --- FILE LIST SECTION ---
    st.subheader("My Cloud Files")
    
    files = client.list_files(GATEWAY)
    
    if not files:
        st.info("Your drive is empty. Upload a file above!")
        return

    # Header Row
    col_name, col_size, col_date, col_action = st.columns([5, 1.5, 2, 2])
    col_name.markdown("**File Name**")
    col_size.markdown("**Size (Bytes)**")
    col_date.markdown("**Date**")
    col_action.markdown("**Action**")
    st.markdown("---")
    
    # File Rows
    for f in files:
        col_name, col_size, col_date, col_action = st.columns([5, 1.5, 2, 2])
        
        # Format date string nicely
        try:
            created_at = datetime.datetime.strptime(f.created_at, '%a %b %d %H:%M:%S %Y').strftime('%Y-%m-%d %H:%M')
        except:
            created_at = f.created_at # Fallback if time format is unexpected

        col_name.write(f"📄 **{f.filename}**")
        col_size.write(f"{f.filesize:,}")
        col_date.write(created_at)
        
        with col_action:
            retr_key = f"btn_retr_{f.upload_id}"
            ready_key = f"ready_{f.upload_id}"
            local_path = f"downloaded_{f.filename}"
            
            if st.session_state.get(ready_key) and os.path.exists(local_path):
                # State: File is downloaded and ready to be served
                with open(local_path, "rb") as fh:
                    st.download_button("💾 Download", fh, file_name=f.filename, key=f"dl_{f.upload_id}", use_container_width=True, type="secondary")
            else:
                # State: Initial Retrieve Button
                if st.button("⬇️ Retrieve", key=retr_key, use_container_width=True, type="primary"):
                    with st.spinner(f"Fetching '{f.filename}' from nodes..."):
                        # Ensure the output path is set
                        ok, msg = client.download_file(GATEWAY, f.filename, local_path)
                        
                        if ok:
                            # Set state to indicate readiness and rerender to show download button
                            st.session_state[ready_key] = True
                            st.success(f"File retrieved locally. Click 'Download' to save.")
                            st.rerun()
                        else:
                            st.error(f"Retrieval failed: {msg}")
        
        st.markdown("<div style='border-bottom: 1px solid #dee2e6; margin-top: 5px; margin-bottom: 5px;'></div>", unsafe_allow_html=True)


# --- MAIN ENTRY POINT ---

render_sidebar()

if not st.session_state['token']:
    render_login()
else:
    render_dashboard()