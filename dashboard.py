import streamlit as st
import time
import os
import datetime
from client import client_cli as client

# Configuration
GATEWAY = "localhost:50051"

st.set_page_config(page_title="Bluetap Water Mgmt", page_icon="💧", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .reportview-container { background: #f0f8ff }
    h1 { color: #0077b6; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .status-critical { color: red; font-weight: bold; }
    .status-normal { color: green; font-weight: bold; }
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/color/100/000000/water-tower.png", width=80)
    st.title("Bluetap Portal")
    st.caption("Community Water Management")
    st.markdown("---")
    
    if st.session_state.get('token'):
        st.write(f"👷 User: **{st.session_state.get('login_user')}**")
        st.write(f"📍 Role: **Field Technician**")
        st.success(f"System Status: Online")
        
        st.markdown("---")
        if st.button("Logout"):
            st.session_state['token'] = None
            st.session_state['otp_sent'] = False
            for key in list(st.session_state.keys()):
                if key.startswith("ready_"): del st.session_state[key]
            st.rerun()

# --- MAIN APP LOGIC ---

if 'token' not in st.session_state: st.session_state['token'] = None
if 'otp_sent' not in st.session_state: st.session_state['otp_sent'] = False

if not st.session_state['token']:
    # === LOGIN SCREEN ===
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.title("💧 Bluetap Login")
        st.markdown("Secure Access for Council & Technicians")
        with st.form("login"):
            user = st.text_input("Username", placeholder="e.g. technician_1")
            email = st.text_input("Official Email")
            if st.form_submit_button("Request Access Code"):
                ok, msg = client.login(GATEWAY, user, email)
                if ok:
                    st.session_state['otp_sent'] = True
                    st.session_state['login_user'] = user
                    st.session_state['login_email'] = email
                    st.rerun()
                else:
                    st.error(f"Error: {msg}")
        
        if st.session_state['otp_sent']:
            st.info("Enter the code sent to your email/terminal.")
            otp = st.text_input("OTP Code", type="password")
            if st.button("Verify"):
                ok, token = client.verify_otp_and_get_token(GATEWAY, st.session_state['login_user'], otp)
                if ok:
                    st.session_state['token'] = token
                    st.rerun()
                else:
                    st.error("Invalid Code")

else:
    # === MAIN APPLICATION ===
    client.set_token(st.session_state['token'])
    
    # Header Statistics
    files = client.list_files(GATEWAY)
    
    # Dashboard Stats
    k1, k2, k3 = st.columns(3)
    k1.metric("Active Nodes", "2 (Replicated)", delta="Healthy")
    k2.metric("Reports Stored", f"{len(files)}")
    k3.metric("Storage Used", "Distributed", delta_color="off")
    
    st.divider()

    # TABS for Workflow
    tab1, tab2 = st.tabs(["📝 Submit New Report", "🗃️ Report Archive"])

    with tab1:
        st.subheader("New Infrastructure Report")
        
        c1, c2 = st.columns(2)
        with c1:
            region = st.selectbox("Region", ["Yaoundé", "Douala", "Buea", "Bamenda", "Garoua"])
            issue_type = st.selectbox("Issue Type", ["Leakage", "Broken Pump", "Contamination", "Routine Check", "Meter Reading"])
        with c2:
            urgency = st.radio("Urgency Level", ["Normal", "High", "CRITICAL"])
            notes = st.text_input("Short Description", placeholder="e.g. Main pipe burst at Mokolo")

        uploaded_file = st.file_uploader("Attach Photo/Document", type=['jpg', 'png', 'pdf', 'txt'])
        
        if uploaded_file and st.button("🚀 Submit Report to Cloud", type="primary"):
            # RENAME FILE TO INCLUDE METADATA (The Trick!)
            # Format: [REGION][URGENCY] filename
            timestamp = int(time.time())
            ext = uploaded_file.name.split('.')[-1]
            # Sanitize inputs
            safe_region = region.replace(" ", "")
            safe_issue = issue_type.replace(" ", "")
            
            # Construct "Smart Filename"
            smart_filename = f"[{safe_region}][{urgency}]_{safe_issue}_{timestamp}.{ext}"
            
            # Save Temp
            temp_path = f"temp_{smart_filename}"
            with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
            
            # Progress bar
            progress = st.progress(0, text="Initiating distributed upload...")
            status = st.empty()
            
            def update_ui(chunk_id, fname, node):
                status.text(f"Replicating block {chunk_id} to {node}...")
                progress.progress(min(100, (chunk_id+1)*10))

            ok, msg = client.put_file(GATEWAY, temp_path, progress_callback=update_ui)
            
            if ok:
                progress.progress(100)
                status.text("✅ Data persisted to distributed nodes.")
                st.success(f"Report ID {smart_filename} submitted successfully!")
                time.sleep(2)
                os.remove(temp_path)
                st.rerun()
            else:
                st.error(f"Submission Failed: {msg}")

    with tab2:
        st.subheader("Archived Community Reports")
        
        # Filter Logic
        filter_reg = st.multiselect("Filter by Region", ["Yaoundé", "Douala", "Buea", "Bamenda", "Garoua"])
        
        if not files:
            st.info("No reports found in the system.")
        else:
            # Table Header
            cl1, cl2, cl3, cl4 = st.columns([4, 2, 2, 2])
            cl1.markdown("**Report Details**")
            cl2.markdown("**Size**")
            cl3.markdown("**Date**")
            cl4.markdown("**Action**")
            st.markdown("---")

            for f in files:
                # Parse metadata from filename if possible
                display_name = f.filename
                tag = ""
                if display_name.startswith("["):
                    # Visual cleanup for the UI
                    tag = "🚨 " if "CRITICAL" in display_name else "✅ "
                
                # Apply filter
                if filter_reg:
                    # If filter is active, check if filename contains any selected region
                    if not any(reg.replace(" ", "") in f.filename for reg in filter_reg):
                        continue

                with st.container():
                    c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
                    c1.markdown(f"{tag}`{f.filename}`")
                    c2.text(f"{f.filesize} B")
                    c3.text(f.created_at)
                    
                    with c4:
                        # Retrieval Logic
                        ready_key = f"ready_{f.upload_id}"
                        local_path = f"downloaded_{f.filename}"
                        
                        if st.session_state.get(ready_key) and os.path.exists(local_path):
                            with open(local_path, "rb") as fh:
                                st.download_button("💾 Open", fh, file_name=f.filename, key=f"dl_{f.upload_id}")
                        else:
                            if st.button("☁️ Retrieve", key=f"fetch_{f.upload_id}"):
                                with st.spinner("Locating blocks..."):
                                    ok, msg = client.download_file(GATEWAY, f.filename, local_path)
                                    if ok:
                                        st.session_state[ready_key] = True
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    st.divider()