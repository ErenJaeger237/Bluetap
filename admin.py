import streamlit as st
import sqlite3
import pandas as pd
import time
import os
import subprocess
import sys
import re
import datetime

# Configuration
DB_PATH = "gateway_meta.db"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = "50051"

st.set_page_config(page_title="Bluetap Admin Control", page_icon="🛡️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; }
    h1, h2, h3 { color: #2c3e50; }
    .status-online { color: #27ae60; font-weight: bold; }
    .status-offline { color: #c0392b; font-weight: bold; }
    div[data-testid="stDataFrame"] { border: 1px solid #ddd; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- DB HELPERS ---
def get_db_connection():
    if not os.path.exists(DB_PATH): return None
    return sqlite3.connect(DB_PATH)

def load_data(query):
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# --- NODE OPS ---
def spawn_node(node_id, port):
    cmd = f"python -m node.node_server --node-id {node_id} --port {port} --storage ./{node_id}_storage --gateway {GATEWAY_HOST}:{GATEWAY_PORT}"
    try:
        if sys.platform == "win32":
            full_cmd = f'start "Bluetap Node: {node_id}" cmd /k "{cmd}"'
            subprocess.Popen(full_cmd, shell=True)
        else:
            subprocess.Popen(cmd.split(), shell=False)
        return True, f"Launched {node_id} on port {port}"
    except Exception as e:
        return False, str(e)

def kill_node_process(port):
    try:
        if sys.platform == "win32":
            netstat = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
            pid = None
            for line in netstat.splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    break
            if pid:
                subprocess.run(f"taskkill /F /PID {pid}", shell=True)
                return True, f"Terminated process {pid}"
            else:
                return False, f"No process on port {port}"
        else:
            return False, "Kill only supported on Windows in this demo"
    except Exception as e:
        return False, str(e)

# --- LOGIN ---
if 'admin_logged_in' not in st.session_state: st.session_state['admin_logged_in'] = False

if not st.session_state['admin_logged_in']:
    c1, c2, c3 = st.columns([1,1,1])
    with c2:
        st.title("🛡️ Admin Portal")
        with st.form("admin_login"):
            user = st.text_input("Admin User")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if user == "admin" and pw == "admin123":
                    st.session_state['admin_logged_in'] = True
                    st.rerun()
                else: st.error("Access Denied")
    st.stop()

# --- MAIN DASHBOARD ---
nodes_df = load_data("SELECT * FROM nodes")
users_df = load_data("SELECT * FROM users")
files_df = load_data("SELECT * FROM files")
audit_df = load_data("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 500")

# Format Timestamps
if not audit_df.empty:
    audit_df['Time'] = audit_df['timestamp'].apply(lambda x: datetime.datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M:%S'))
    audit_df = audit_df[['Time', 'username', 'action', 'details']]

# Sidebar
with st.sidebar:
    st.title("🛡️ Supervisor")
    if st.button("Refresh Data"): st.rerun()
    st.markdown("---")
    
    st.subheader("🚀 Orchestration")
    next_char = chr(65 + len(nodes_df)) if not nodes_df.empty else 'A'
    sugg_port = (nodes_df['port'].max() + 1) if not nodes_df.empty else 50061
    with st.expander("➕ Add Node"):
        nid = st.text_input("ID", f"node{next_char}")
        np = st.number_input("Port", sugg_port, step=1)
        if st.button("Launch Instance"):
            ok, msg = spawn_node(nid, np)
            if ok: st.success(msg); time.sleep(1); st.rerun()
    
    st.markdown("---")
    if st.button("Logout"):
        st.session_state['admin_logged_in'] = False
        st.rerun()

# Body
st.title("📊 System Health & Telemetry")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Registered Users", len(users_df))
k2.metric("Total Files", len(files_df))
k3.metric("System Events", len(audit_df))
k4.metric("Active Nodes", len(nodes_df))

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📜 Forensic Audit Trail", "🖥️ Infrastructure", "🗃️ Files"])

# TAB 1: AUDIT LOGS (NEW!)
with tab1:
    st.subheader("System Activity Log")
    
    # Filters
    c1, c2 = st.columns(2)
    user_filter = c1.multiselect("Filter by User", audit_df['username'].unique() if not audit_df.empty else [])
    action_filter = c2.multiselect("Filter by Action", audit_df['action'].unique() if not audit_df.empty else [])
    
    filtered_df = audit_df
    if user_filter: filtered_df = filtered_df[filtered_df['username'].isin(user_filter)]
    if action_filter: filtered_df = filtered_df[filtered_df['action'].isin(action_filter)]
    
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# TAB 2: NODES
with tab2:
    if nodes_df.empty:
        st.warning("No nodes.")
    else:
        # Node Table with Kill Switch
        cols = st.columns([1, 2, 2, 2, 1])
        cols[0].markdown("**ID**")
        cols[1].markdown("**Address**")
        cols[2].markdown("**Heartbeat**")
        cols[3].markdown("**Status**")
        cols[4].markdown("**Action**")
        
        current_time = time.time()
        for _, row in nodes_df.iterrows():
            last_seen = row['last_seen']
            is_alive = (current_time - last_seen) < 20
            
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 1])
                c1.write(f"**{row['node_id']}**")
                c2.write(f"{row['ip']}:{row['port']}")
                c3.write(f"{current_time - last_seen:.1f}s ago")
                
                if is_alive:
                    c4.success("ONLINE")
                    if c5.button("💀 Kill", key=f"k_{row['node_id']}"):
                        kill_node_process(row['port'])
                        st.rerun()
                else:
                    c4.error("OFFLINE")
                    if c5.button("♻️ Revive", key=f"r_{row['node_id']}"):
                        spawn_node(row['node_id'], row['port'])
                        st.rerun()
                st.divider()

# TAB 3: FILES
with tab3:
    st.dataframe(files_df[['filename', 'owner', 'filesize', 'nodes_csv']], use_container_width=True)