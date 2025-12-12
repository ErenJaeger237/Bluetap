import os
from client.client_cli import login, verify_otp, download_file

GATEWAY_ADDR = "localhost:50051"
TEST_USER = "demo"
DOWNLOAD_FILENAME = "test_upload_file.txt" # The file we uploaded earlier
OUTPUT_FILENAME = "downloaded_test_file.txt"

def main():
    print("\n--- 📥 STARTING BLUETAP DOWNLOAD TEST ---")

    # 1. Login again (since tokens are ephemeral in memory)
    print("[*] Authenticating...")
    login(GATEWAY_ADDR, TEST_USER)
    
    # 2. Verify OTP
    print("\n❗ Check Gateway terminal for OTP and enter it below:")
    if not verify_otp(GATEWAY_ADDR, TEST_USER):
        print("❌ Login Failed")
        return

    # 3. Attempt Download
    print(f"\n--- 💾 DOWNLOADING {DOWNLOAD_FILENAME} ---")
    
    if os.path.exists(OUTPUT_FILENAME):
        os.remove(OUTPUT_FILENAME) # Cleanup previous run

    success = download_file(GATEWAY_ADDR, DOWNLOAD_FILENAME, OUTPUT_FILENAME)
    
    if success:
        # Verify content matches
        with open(OUTPUT_FILENAME, "r") as f:
            content = f.read()
            print(f"\n📜 File Content:\n{'-'*20}\n{content}\n{'-'*20}")
            if "Bluetap secure upload" in content:
                print("✅ CONTENT VERIFIED! System is fully operational.")
            else:
                print("⚠️ Content mismatch.")

if __name__ == "__main__":
    main()