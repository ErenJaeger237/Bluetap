import os
import sys

# --- ADJUST THIS LINE IF YOUR FUNCTIONS ARE IN client_cli.py ---
# Try: from client.cli import login, verify_otp, put_file 
from client.client_cli import login, verify_otp, put_file
# -----------------------------------------------------------------

GATEWAY_ADDR = "localhost:50051"
TEST_USER = "demo"
TEST_FILE_PATH = "./test_upload_file.txt"

def ensure_test_file():
    """Creates a small dummy file needed for the test."""
    if not os.path.exists(TEST_FILE_PATH):
        with open(TEST_FILE_PATH, "w") as f:
            f.write("This is a small test file for Bluetap secure upload validation.\n")
            f.write("It proves that authentication and authorization are functioning.\n")
        print(f"[*] Created dummy file: {TEST_FILE_PATH}")
    else:
        print(f"[*] Dummy file found: {TEST_FILE_PATH}")

def main():
    print("\n--- 🔐 STARTING BLUETAP SECURE LOGIN TEST ---")
    ensure_test_file()

    # Step 1: Request OTP
    if not login(GATEWAY_ADDR, TEST_USER):
        print("❌ Test Failed: Could not request OTP. Check Gateway server status.")
        return

    # Step 2: Verify OTP and acquire Token
    print("\n❗ IMPORTANT: Check the Gateway terminal for the 6-digit OTP code.\n")
    if not verify_otp(GATEWAY_ADDR, TEST_USER):
        print("❌ Test Failed: OTP verification failed.")
        return
    
    # Step 3: Attempt Secure Action (PutMeta)
    print("\n--- 📂 ATTEMPTING SECURE FILE UPLOAD ---")
    put_file(GATEWAY_ADDR, TEST_FILE_PATH)
    
    print("\n✅ Authentication Test Complete.")

if __name__ == "__main__":
    # Add your client folder to the Python path if running from the root
    if os.path.isdir('client') and os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())
    
    main()