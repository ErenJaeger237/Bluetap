import sqlite3
import hashlib
import time

# Name of the database file
DB_NAME = "gateway_meta.db"

class MetadataDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # 1. Users Table
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

        # 2. Nodes Table (For Storage Nodes)
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

        # 3. Files Table (For Metadata)
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

    # --- USER AUTHENTICATION METHODS ---
    
    def add_user(self, username, password, email):
        """Creates a new user or updates existing (for demo)."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (username, password_hash, email) VALUES (?, ?, ?)", 
                       (username, password_hash, email))
        self.conn.commit()

    # --- NODE MANAGEMENT METHODS (This was missing!) ---

    def register_node(self, node_id, ip, port, capacity, metadata=""):
        """Registers a storage node."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO nodes (node_id, ip, port, capacity_bytes, metadata, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                       (node_id, ip, port, capacity, metadata, time.time()))
        self.conn.commit()
        print(f"[*] DB: Registered node {node_id}")

    def list_nodes(self):
        """Returns all registered nodes."""
        cursor = self.conn.cursor()
        # Returns: node_id, ip, port, capacity, last_seen, metadata
        cursor.execute("SELECT node_id, ip, port, capacity_bytes, last_seen, metadata FROM nodes")
        return cursor.fetchall()

    # --- FILE METADATA METHODS ---

    def save_file_metadata(self, upload_id, filename, owner, filesize, chunk_size, total_chunks, nodes_list):
        """Saves file metadata after upload init."""
        nodes_csv = ",".join(nodes_list)
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO files (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, time.time(), owner))
        self.conn.commit()

    def get_file_by_filename(self, filename):
        """Retrieves file metadata by filename."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created FROM files WHERE filename=?", (filename,))
        return cursor.fetchone()