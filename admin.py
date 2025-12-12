import streamlit as st
import sqlite3
import pandas as pd
import time
import os

# Configuration
DB_PATH = "gateway_meta.db"

st.set_page_config(page_title="Bluetap Admin Control", page_icon="🛡️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    h1, h2, h3 { color: #2c3e50; }
    .status-online { color: #27ae60; font-weight: bold; }
    .status-offline { color: #c0392b; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- DB HELPERS ---
def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)

def load_data(query):
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# --- LOGIN ---
if 'admin_logged_in' not in st.session_state:
    st.session_state['admin_logged_in'] = False

if not st.session_state['admin_logged_in']:
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.image("https://img.icons8.com/dusk/100/000000/admin-settings-male.png", width=100)
        st.title("🛡️ Admin Portal")
        
        with st.form("admin_login"):
            user = st.text_input("Admin User")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Access Control Plane"):
                # HARDCODED ADMIN CREDENTIALS FOR DEMO
                if user == "admin" and pw == "admin123":
                    st.session_state['admin_logged_in'] = True
                    st.rerun()
                else:
                    st.error("Access Denied")
    st.stop()

# --- MAIN DASHBOARD ---

# Sidebar
with st.sidebar:
    st.title("🛡️ Supervisor")
    st.success("Connected to Metadata Store")
    if st.button("Refresh Data"):
        st.rerun()
    st.markdown("---")
    if st.button("Logout"):
        st.session_state['admin_logged_in'] = False
        st.rerun()

st.title("📊 System Health & Telemetry")

# 1. KPIs
users_df = load_data("SELECT * FROM users")
files_df = load_data("SELECT * FROM files")
nodes_df = load_data("SELECT * FROM nodes")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Registered Users", len(users_df))
k2.metric("Total Files Stored", len(files_df))
total_storage = files_df['filesize'].sum() if not files_df.empty else 0
k3.metric("Storage Used", f"{total_storage / 1024:.2f} KB")
k4.metric("Registered Nodes", len(nodes_df))

st.markdown("---")

# 2. NODE HEALTH MONITOR (The Critical Part)
st.subheader("🖥️ Distributed Infrastructure Status")

if nodes_df.empty:
    st.warning("No nodes registered in the system.")
else:
    # Calculate Live Status
    current_time = time.time()
    
    # Create status list
    node_status = []
    for index, row in nodes_df.iterrows():
        last_seen = row['last_seen']
        # If seen in last 20 seconds, it's alive
        is_alive = (current_time - last_seen) < 20
        status_text = "🟢 ONLINE" if is_alive else "🔴 OFFLINE/DEAD"
        uptime_text = f"{current_time - last_seen:.1f}s ago"
        
        node_status.append({
            "Node ID": row['node_id'],
            "Address": f"{row['ip']}:{row['port']}",
            "Capacity": f"{row['capacity_bytes'] / (1024**3):.0f} GB",
            "Last Heartbeat": uptime_text,
            "Status": status_text
        })
    
    status_df = pd.DataFrame(node_status)
    
    # Display styled dataframe
    st.dataframe(
        status_df, 
        use_container_width=True,
        column_config={
            "Status": st.column_config.TextColumn(
                "Health",
                help="Real-time status based on heartbeats",
                validate="^🟢"
            )
        }
    )

    # Live Visualization of Cluster
    c1, c2 = st.columns([2, 1])
    with c1:
        st.caption("Load Distribution (Files per Node)")
        # This is an estimation query since our nodes_csv is a string list
        # For the demo chart, we just show capacity or raw node count
        st.bar_chart(status_df.set_index("Node ID")["Status"]) # Simplified visualization

# 3. USER & FILE AUDIT
st.markdown("---")
tab1, tab2 = st.tabs(["👥 User Directory", "🗃️ Global File Audit"])

with tab1:
    st.dataframe(users_df[['username', 'email']], use_container_width=True)

with tab2:
    st.dataframe(
        files_df[['filename', 'owner', 'filesize', 'nodes_csv', 'created']],
        use_container_width=True,
        column_config={
            "nodes_csv": "Replicated On",
            "created": st.column_config.NumberColumn("Timestamp", format="%d")
        }
    )