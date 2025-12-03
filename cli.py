import argparse
import os
import sys
from client import client_cli as client

# File to store the session token so you stay logged in
TOKEN_FILE = "session.token"
GATEWAY_ADDR = "localhost:50051"

def save_token_to_disk(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    print(f"💾 Session saved to {TOKEN_FILE}")

def load_token_from_disk():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return f.read().strip()

def cmd_login(args):
    """Handles the 2-step Login/Enrolment Flow"""
    print(f"--- 🔐 Bluetap Login / Enrolment ---")
    print(f"[*] Connecting to {GATEWAY_ADDR} as user '{args.user}'...")
    
    # Step 1: Request OTP (Triggers Auto-Enrolment on Server)
    if client.login(GATEWAY_ADDR, args.user):
        print("❗ An OTP has been sent to the Gateway Server logs.")
        
        # Step 2: Verify OTP
        # client.verify_otp asks for input internally, 
        # but we need to capture the token to save it.
        if client.verify_otp(GATEWAY_ADDR, args.user):
            # Retrieve the token from the client memory
            token = client.get_token()
            if token:
                save_token_to_disk(token)
                print("✅ You are now logged in and ready to upload!")
            else:
                print("❌ Error: Could not retrieve token.")
    else:
        print("❌ Login request failed.")

def cmd_upload(args):
    """Handles File Upload"""
    token = load_token_from_disk()
    if not token:
        print("⛔ You are not logged in. Run: python cli.py login --user <name>")
        return

    # Load token into client
    client.set_token(token)
    
    if not os.path.exists(args.file):
        print(f"❌ File not found: {args.file}")
        return

    print(f"--- 📂 Uploading {args.file} ---")
    client.put_file(GATEWAY_ADDR, args.file)

def cmd_download(args):
    """Handles File Download"""
    token = load_token_from_disk()
    if not token:
        print("⛔ You are not logged in. Run: python cli.py login --user <name>")
        return

    # Load token into client
    client.set_token(token)
    
    print(f"--- 📥 Downloading {args.filename} ---")
    client.download_file(GATEWAY_ADDR, args.filename, args.output)

def main():
    parser = argparse.ArgumentParser(description="Bluetap Distributed File System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # LOGIN Command
    parser_login = subparsers.add_parser("login", help="Login or Register a new user")
    parser_login.add_argument("--user", required=True, help="Username to login/register")

    # UPLOAD Command
    parser_upload = subparsers.add_parser("upload", help="Upload a file")
    parser_upload.add_argument("file", help="Path to the file to upload")

    # DOWNLOAD Command
    parser_download = subparsers.add_parser("download", help="Download a file")
    parser_download.add_argument("filename", help="Name of the file on the server")
    parser_download.add_argument("--output", default="downloaded_file.dat", help="Output path")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "upload":
        cmd_upload(args)
    elif args.command == "download":
        cmd_download(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()