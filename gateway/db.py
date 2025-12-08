import sqlite3
import hashlib
import time

DB_NAME = "gateway_meta.db"

class MetadataDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        # Users table now stores email permanently
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
        # Nodes Table
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
        # Files Table
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
        self.conn.commit()

    # --- USER METHODS ---
    def get_user(self, username):
        """Find a user to see if they exist."""
        cur = self.conn.cursor()
        cur.execute("SELECT username, email FROM users WHERE username=?", (username,))
        return cur.fetchone()

    def register_user(self, username, email):
        """Register a NEW user."""
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users (username, email) VALUES (?, ?)", (username, email))
        self.conn.commit()

    def save_otp(self, username, otp_code):
        cur = self.conn.cursor()
        expiry = time.time() + 300 # 5 mins
        cur.execute("UPDATE users SET otp_code=?, otp_expiry=? WHERE username=?", (otp_code, expiry, username))
        self.conn.commit()

    def verify_otp_db(self, username, otp_input):
        cur = self.conn.cursor()
        cur.execute("SELECT otp_code, otp_expiry FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        if not row: return False, "User not found"
        code, expiry = row
        if time.time() > expiry: return False, "Expired"
        if code != otp_input: return False, "Wrong Code"
        return True, "OK"

    def save_token(self, username, token):
        cur = self.conn.cursor()
        expiry = time.time() + 3600 # 1 hour
        cur.execute("UPDATE users SET token=?, token_expiry=? WHERE username=?", (token, expiry, username))
        self.conn.commit()

    def validate_token(self, token):
        cur = self.conn.cursor()
        cur.execute("SELECT username, token_expiry FROM users WHERE token=?", (token,))
        row = cur.fetchone()
        if not row: return None
        if time.time() > row[1]: return None
        return row[0]

    # --- NODE & FILE METHODS (Standard) ---
    def register_node(self, node_id, ip, port, capacity, metadata=""):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO nodes (node_id, ip, port, capacity_bytes, metadata, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                       (node_id, ip, port, capacity, metadata, time.time()))
        self.conn.commit()

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

    def get_file_by_filename(self, filename):
        cur = self.conn.cursor()
        cur.execute("SELECT upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created FROM files WHERE filename=?", (filename,))
        return cur.fetchone()

    def get_user_files(self, username):
        cur = self.conn.cursor()
        cur.execute("SELECT filename, upload_id, filesize, created FROM files WHERE owner=? ORDER BY created DESC", (username,))
        return cur.fetchall()