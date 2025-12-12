import argparse
import os
import sys
from client import client_cli as client

TOKEN_FILE = "session.token"
GATEWAY_ADDR = "localhost:50051"

def save_token(t):
    with open(TOKEN_FILE, "w") as f: f.write(t)

def load_token():
    if os.path.exists(TOKEN_FILE): return open(TOKEN_FILE).read().strip()
    return None

def cmd_login(args):
    print(f"--- 🔐 Bluetap Cloud Access ---")
    
    # 1. Try to login/register
    success, msg = client.login(GATEWAY_ADDR, args.user, args.email)
    
    if not success:
        if "User not found" in msg:
            print(f"❌ Account '{args.user}' does not exist.")
            print(f"💡 To create an account, run:\n   python cli.py login --user {args.user} --email your@email.com")
        else:
            print(f"❌ Error: {msg}")
        return

    # 2. If success, OTP was sent
    print(f"✅ {msg}")
    print("   (If you don't see the email, check the Gateway terminal logs for the code)")
    
    if client.verify_otp(GATEWAY_ADDR, args.user):
        t = client.get_token()
        save_token(t)
        print(f"🎉 Welcome, {args.user}! You are logged in.")

def cmd_upload(args):
    t = load_token()
    if not t: return print("⛔ Not logged in.")
    client.set_token(t)
    print(f"--- 📂 Uploading {args.file} ---")
    ok, msg = client.put_file(GATEWAY_ADDR, args.file)
    print(msg)

def cmd_download(args):
    t = load_token()
    if not t: return print("⛔ Not logged in.")
    client.set_token(t)
    print(f"--- 📥 Downloading {args.filename} ---")
    ok, msg = client.download_file(GATEWAY_ADDR, args.filename, args.output)
    print(msg)

def cmd_list(args):
    t = load_token()
    if not t: return print("⛔ Not logged in.")
    client.set_token(t)
    print(f"--- 📂 Files for current user ---")
    files = client.list_files(GATEWAY_ADDR)
    if not files: print("   (No files found)")
    for f in files:
        print(f" - {f.filename} ({f.filesize} bytes) [{f.created_at}]")

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    # Login
    p_login = sub.add_parser("login")
    p_login.add_argument("--user", required=True)
    p_login.add_argument("--email", default="", help="Required for NEW accounts")

    # Upload
    p_up = sub.add_parser("upload")
    p_up.add_argument("file")

    # Download
    p_down = sub.add_parser("download")
    p_down.add_argument("filename")
    p_down.add_argument("--output", default="downloaded.dat")

    # List
    p_list = sub.add_parser("list")

    args = parser.parse_args()
    if args.cmd == "login": cmd_login(args)
    elif args.cmd == "upload": cmd_upload(args)
    elif args.cmd == "download": cmd_download(args)
    elif args.cmd == "list": cmd_list(args)
    else: parser.print_help()

if __name__ == "__main__":
    main()