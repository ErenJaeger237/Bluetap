import sqlite3
import hashlib
import time

DB_NAME = "gateway_meta.db"

class MetadataDB:
    def __init__(self):
        print("[-] Loading Database...")
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        
        # 1. Users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                email TEXT,
                otp_code TEXT,
                otp_expiry REAL,
                token TEXT,
                token_expiry REAL
            )
        """)

        # 2. Nodes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                ip TEXT,
                port INTEGER,
                capacity_bytes INTEGER,
                metadata TEXT,
                last_seen REAL
            )
        """)

        # 3. Files
        cur.execute("""
            CREATE TABLE IF NOT EXISTS files (
                upload_id TEXT PRIMARY KEY,
                filename TEXT,
                filesize INTEGER,
                chunk_size INTEGER,
                total_chunks INTEGER,
                nodes_csv TEXT,
                created REAL,
                owner TEXT
            )
        """)

        # 4. AUDIT LOGS (NEW!)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                username TEXT,
                action TEXT,
                details TEXT
            )
        """)
        
        self.conn.commit()

    # --- AUDIT LOGGING (NEW!) ---
    def log_event(self, username, action, details):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO audit_logs (timestamp, username, action, details) VALUES (?, ?, ?, ?)",
                    (time.time(), username, action, details))
        self.conn.commit()
        # Also print to terminal for debugging
        print(f"📝 [AUDIT] {username} -> {action}: {details}")

    def get_audit_logs(self, limit=100):
        cur = self.conn.cursor()
        cur.execute("SELECT timestamp, username, action, details FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        return cur.fetchall()

    # --- USER METHODS ---
    
    def get_user(self, username):
        cur = self.conn.cursor()
        cur.execute("SELECT username, email FROM users WHERE username=?", (username,))
        return cur.fetchone()

    def register_user(self, username, email):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users (username, email) VALUES (?, ?)", (username, email))
        self.conn.commit()
        self.log_event(username, "REGISTER", f"New user with email {email}")

    def save_otp(self, username, otp_code):
        cur = self.conn.cursor()
        expiry = time.time() + 300
        cur.execute("UPDATE users SET otp_code=?, otp_expiry=? WHERE username=?", (otp_code, expiry, username))
        self.conn.commit()

    def verify_otp_db(self, username, otp_input):
        cur = self.conn.cursor()
        cur.execute("SELECT otp_code, otp_expiry FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        
        if not row: return False, "User not found"
        
        code, expiry = row
        if time.time() > expiry: return False, "Expired"
        if code != otp_input: 
            self.log_event(username, "LOGIN_FAIL", "Invalid OTP entered")
            return False, "Wrong Code"
        
        return True, "OK"

    def add_user(self, username, password, email):
        self.register_user(username, email)

    def save_token(self, username, token):
        cur = self.conn.cursor()
        expiry = time.time() + 3600
        cur.execute("UPDATE users SET token=?, token_expiry=? WHERE username=?", (token, expiry, username))
        self.conn.commit()
        self.log_event(username, "LOGIN_SUCCESS", "Session token issued")

    def validate_token(self, token):
        cur = self.conn.cursor()
        cur.execute("SELECT username, token_expiry FROM users WHERE token=?", (token,))
        row = cur.fetchone()
        if not row: return None
        if time.time() > row[1]: return None
        return row[0]

    # --- NODE & FILE METHODS ---

    def register_node(self, node_id, ip, port, capacity, metadata=""):
        cur = self.conn.cursor()
        # Check if it existed before to log correctly
        cur.execute("SELECT node_id FROM nodes WHERE node_id=?", (node_id,))
        exists = cur.fetchone()
        
        cur.execute("INSERT OR REPLACE INTO nodes (node_id, ip, port, capacity_bytes, metadata, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                       (node_id, ip, port, capacity, metadata, time.time()))
        self.conn.commit()
        
        if not exists:
            self.log_event("SYSTEM", "NODE_JOIN", f"Node {node_id} joined the cluster")

    def list_nodes(self):
        cur = self.conn.cursor()
        cur.execute("SELECT node_id, ip, port, capacity_bytes, last_seen, metadata FROM nodes")
        return cur.fetchall()

    def save_file_metadata(self, upload_id, filename, owner, filesize, chunk_size, total_chunks, nodes_list):
        nodes_csv = ",".join(nodes_list)
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO files (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, time.time(), owner))
        self.conn.commit()
        
        self.log_event(owner, "UPLOAD", f"File: {filename} ({filesize} bytes) -> {nodes_csv}")

    def get_file_by_filename(self, filename):
        cur = self.conn.cursor()
        cur.execute("SELECT upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created FROM files WHERE filename=?", (filename,))
        return cur.fetchone()

    def get_user_files(self, username):
        cur = self.conn.cursor()
        cur.execute("SELECT filename, upload_id, filesize, created FROM files WHERE owner=? ORDER BY created DESC", (username,))
        return cur.fetchall()