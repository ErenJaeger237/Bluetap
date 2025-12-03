import sqlite3
import hashlib
import time

DB_NAME = "gateway_meta.db"

class MetadataDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # 1. Users Table (Stores Tokens persistently)
        cursor.execute("""
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

        # 2. Nodes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                ip TEXT,
                port INTEGER,
                capacity_bytes INTEGER,
                metadata TEXT,
                last_seen REAL
            )
        """)

        # 3. Files Table
        cursor.execute("""
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

    # --- USER & TOKEN METHODS (This was missing!) ---
    
    def add_user(self, username, password, email):
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (username, password_hash, email) VALUES (?, ?, ?)", 
                       (username, password_hash, email))
        self.conn.commit()

    def save_token(self, username, token):
        """Saves a token to the database with 1-hour expiry."""
        expiry = time.time() + 3600 # 1 hour from now
        cursor = self.conn.cursor()
        cursor.execute("UPDATE users SET token=?, token_expiry=? WHERE username=?", 
                       (token, expiry, username))
        self.conn.commit()

    def validate_token(self, token):
        """Checks if token exists and is not expired. Returns username or None."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT username, token_expiry FROM users WHERE token=?", (token,))
        row = cursor.fetchone()
        
        if not row:
            return None # Token not found
        
        username, expiry = row
        if time.time() > expiry:
            return None # Token expired
            
        return username

    # --- NODE METHODS ---

    def register_node(self, node_id, ip, port, capacity, metadata=""):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO nodes (node_id, ip, port, capacity_bytes, metadata, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                       (node_id, ip, port, capacity, metadata, time.time()))
        self.conn.commit()
        
    def list_nodes(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT node_id, ip, port, capacity_bytes, last_seen, metadata FROM nodes")
        return cursor.fetchall()

    # --- FILE METHODS ---

    def save_file_metadata(self, upload_id, filename, owner, filesize, chunk_size, total_chunks, nodes_list):
        nodes_csv = ",".join(nodes_list)
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO files (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, time.time(), owner))
        self.conn.commit()

    def get_file_by_filename(self, filename):
        cursor = self.conn.cursor()
        cursor.execute("SELECT upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created FROM files WHERE filename=?", (filename,))
        return cursor.fetchone()