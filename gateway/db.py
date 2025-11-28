import sqlite3
import hashlib
import secrets
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
                email TEXT
            )
        """)
        # 2. OTP Table (Temporary codes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS otps (
                username TEXT PRIMARY KEY,
                otp_code TEXT,
                timestamp REAL
            )
        """)
        # 3. Tokens Table (Active sessions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                username TEXT,
                timestamp REAL
            )
        """)
        self.conn.commit()

    def create_user(self, username, password, email):
        """Creates a new user with a hashed password."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)", 
                           (username, password_hash, email))
            self.conn.commit()
            print(f"✅ User '{username}' created successfully.")
            return True
        except sqlite3.IntegrityError:
            print(f"❌ User '{username}' already exists.")
            return False

    def verify_user(self, username, password):
        """Checks if username/password match."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor = self.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username=? AND password_hash=?", 
                       (username, password_hash))
        return cursor.fetchone() is not None

    def save_otp(self, username, otp_code):
        """Saves an OTP for a user (overwrites old ones)."""
        cursor = self.conn.cursor()
        cursor.execute("REPLACE INTO otps (username, otp_code, timestamp) VALUES (?, ?, ?)", 
                       (username, otp_code, time.time()))
        self.conn.commit()

    def verify_otp(self, username, otp_code):
        """Checks if OTP is correct and not expired (valid for 5 mins)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT otp_code, timestamp FROM otps WHERE username=?", (username,))
        row = cursor.fetchone()
        
        if not row:
            return False, "No OTP request found."
        
        stored_otp, timestamp = row
        if time.time() - timestamp > 300: # 300 seconds = 5 mins
            return False, "OTP expired."
        
        if stored_otp == otp_code:
            # Clear OTP after use
            cursor.execute("DELETE FROM otps WHERE username=?", (username,))
            self.conn.commit()
            return True, "Success"
        
        return False, "Invalid OTP."

    def save_token(self, username, token):
        """Saves a session token."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO tokens (token, username, timestamp) VALUES (?, ?, ?)", 
                       (token, username, time.time()))
        self.conn.commit()

    def validate_token(self, token):
        """Checks if a token is valid."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT username FROM tokens WHERE token=?", (token,))
        row = cursor.fetchone()
        if row:
            return True, row[0]
        return False, None
    
    