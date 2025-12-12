import streamlit as st
import time
import os
import datetime
import pandas as pd
from client import client_cli as client

# Configuration
GATEWAY = "localhost:50051"

# CAMEROON REGION COORDINATES (Lat, Lon)
REGION_COORDS = {
    "Yaoundé": [3.8480, 11.5021],
    "Douala": [4.0511, 9.7679],
    "Buea": [4.1550, 9.2435],
    "Bamenda": [5.9631, 10.1591],
    "Garoua": [9.3014, 13.3977],
    "Maroua": [10.5930, 14.3208],
    "Bafoussam": [5.4778, 10.4176]
}

st.set_page_config(page_title="Bluetap Command Center", page_icon="💧", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .reportview-container { background: #f0f8ff }
    h1 { color: #0077b6; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .metric-card { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/color/100/000000/water-tower.png", width=80)
    st.title("Bluetap Portal")
    st.caption("National Water Grid")
    st.markdown("---")
    
    if st.session_state.get('token'):
        st.write(f"👷 User: **{st.session_state.get('login_user')}**")
        st.success(f"System Status: ● Online")
        if st.button("Logout"):
            st.session_state['token'] = None
            st.session_state['otp_sent'] = False
            st.rerun()

# --- HELPER: PARSE METADATA ---
def parse_reports_for_map(files):
    map_data = []
    
    for f in files:
        # Format: [Region][Urgency]_Description_Time.ext
        # Default to Yaounde if unknown
        lat, lon = REGION_COORDS["Yaoundé"]
        urgency = "Normal"
        
        # Try to find region in filename
        for reg_name, coords in REGION_COORDS.items():
            # Check sanitised name
            clean_reg = reg_name.replace("é", "e").replace(" ", "")
            if f"[{clean_reg}]" in f.filename or f"[{reg_name}]" in f.filename:
                # Add slight random jitter so markers don't stack perfectly
                lat, lon = coords[0] + (time.time() % 0.01), coords[1] + (time.time() % 0.01)
        
        if "[CRITICAL]" in f.filename: urgency = "CRITICAL"
        elif "[High]" in f.filename: urgency = "High"
        
        # Color code: Red for Critical, Blue for Normal
        color = "#ff0000" if urgency == "CRITICAL" else "#0000ff"
        size = 200 if urgency == "CRITICAL" else 80
        
        map_data.append({
            "lat": lat,
            "lon": lon,
            "title": f.filename,
            "size": size,
            "color": color,
            "urgency": urgency
        })
        
    return pd.DataFrame(map_data)

# --- MAIN APP LOGIC ---

if 'token' not in st.session_state: st.session_state['token'] = None
if 'otp_sent' not in st.session_state: st.session_state['otp_sent'] = False

if not st.session_state['token']:
    # === LOGIN SCREEN ===
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.title("💧 Bluetap Login")
        st.info("Authorized Personnel Only")
        
        if not st.session_state['otp_sent']:
            with st.form("login"):
                user = st.text_input("Username")
                email = st.text_input("Email")
                if st.form_submit_button("Request Access Code"):
                    ok, msg = client.login(GATEWAY, user, email)
                    if ok:
                        st.session_state['otp_sent'] = True
                        st.session_state['login_user'] = user
                        st.session_state['login_email'] = email
                        st.rerun()
                    else:
                        st.error(msg)
        else:
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
    files = client.list_files(GATEWAY)
    
    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active Nodes", "2 (Replicated)", "Stable")
    k2.metric("Reports Stored", f"{len(files)}")
    critical_count = sum(1 for f in files if "CRITICAL" in f.filename)
    k3.metric("Critical Alerts", f"{critical_count}", delta_color="inverse", delta=critical_count)
    
    st.divider()

    # TABS
    tab1, tab2, tab3 = st.tabs(["🗺️ Situation Room", "📝 Submit Report", "🗃️ Archives"])

    # --- MAP TAB (NEW!) ---
    with tab1:
        st.subheader("Real-Time Infrastructure Map")
        if not files:
            st.info("No data available for mapping.")
        else:
            map_df = parse_reports_for_map(files)
            
            # Interactive Map
            st.map(map_df, latitude="lat", longitude="lon", size="size", color="color", zoom=6)
            
            st.caption("🔴 Red = Critical Faults | 🔵 Blue = Standard Reports")

    # --- UPLOAD TAB ---
    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            region = st.selectbox("Region", list(REGION_COORDS.keys()))
            issue_type = st.selectbox("Issue Type", ["Leakage", "Broken Pump", "Contamination", "Routine Check"])
        with c2:
            urgency = st.radio("Urgency Level", ["Normal", "High", "CRITICAL"])

        uploaded_file = st.file_uploader("Attach Photo/Document")
        
        if uploaded_file and st.button("🚀 Submit Report", type="primary"):
            timestamp = int(time.time())
            ext = uploaded_file.name.split('.')[-1]
            safe_region = region.replace(" ", "").replace("é", "e")
            safe_issue = issue_type.replace(" ", "")
            
            # Construct Smart Filename
            smart_filename = f"[{safe_region}][{urgency}]_{safe_issue}_{timestamp}.{ext}"
            
            temp_path = f"temp_{smart_filename}"
            with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
            
            progress = st.progress(0, text="Initiating distributed upload...")
            status = st.empty()
            
            def update_ui(chunk_id, fname, node):
                status.text(f"Replicating block {chunk_id} to {node}...")
                progress.progress(min(100, (chunk_id+1)*10))

            ok, msg = client.put_file(GATEWAY, temp_path, progress_callback=update_ui)
            
            if ok:
                progress.progress(100)
                status.text("✅ Data persisted.")
                st.success(f"Report submitted!")
                time.sleep(1)
                os.remove(temp_path)
                st.rerun()
            else:
                st.error(msg)

    # --- LIST TAB ---
    with tab3:
        for f in files:
            with st.container():
                c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
                c1.markdown(f"**{f.filename}**")
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
                        if st.button("Retrieve", key=f"fetch_{f.upload_id}"):
                            ok, msg = client.download_file(GATEWAY, f.filename, local_path)
                            if ok:
                                st.session_state[ready_key] = True
                                st.rerun()
                            else:
                                st.error(msg)
            st.divider()