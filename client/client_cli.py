import grpc, hashlib, os, sys, argparse
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

SESSION_TOKEN = None
CHUNK_SIZE_DEFAULT = 512 * 1024

def login(gateway_addr, username):
    """Step 1: Ask Gateway to send an OTP."""
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayServiceStub(channel)
    print(f"[*] Requesting OTP for {username}...")
    try:
        # Note: Check if your proto uses RequestOTPRequest or LoginRequest
        # Based on our history, we switched to an OTP flow:
        response = stub.RequestOTP(pb.RequestOTPRequest(username=username))
        
        if response.ok:
            print(f"✅ OTP Sent! Check the Gateway logs (server terminal).")
            return True
        else:
            print(f"❌ Login failed: {response.message}")
            return False
            
    except grpc.RpcError as e:
        print(f"❌ Connection error: {e.details()}")
        return False

def verify_otp(gateway_addr, username):
    """Step 2: Send OTP to get the Token."""
    global SESSION_TOKEN # We will save the token here
    
    otp_code = input("📩 Enter the 6-digit OTP: ")
    
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayServiceStub(channel)
    
    try:
        response = stub.VerifyOTP(pb.VerifyOTPRequest(username=username, otp_code=otp_code))
        
        if response.ok and response.token:
            SESSION_TOKEN = response.token
            print(f"✅ Authentication Successful!")
            print(f"🔑 Token stored in memory.")
            return True
        else:
            print(f"❌ Verification failed: {response.message}")
            return False
            
    except grpc.RpcError as e:
        print(f"❌ Error: {e.details()}")
        return False
def put_file(gateway_addr, filepath):
    global SESSION_TOKEN
    
    if not SESSION_TOKEN:
        print("⛔ Error: You are not logged in.")
        return

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayServiceStub(channel)

    print(f"[*] Uploading {filename}...")
    
    # Authenticate the request
    auth_metadata = (('authorization', f"Bearer {SESSION_TOKEN}"),)

    try:
        response = stub.PutMeta(
            pb.PutMetaRequest(filename=filename, size=filesize),
            metadata=auth_metadata # <--- IMPORTANT: Sending token here
        )
        
        if response.ok:
            print(f"✅ Upload Approved. ID: {response.upload_id}")
            # Add your chunk upload logic here if it's not already there
        else:
            print(f"❌ Upload Denied: {response.message}")
            
    except grpc.RpcError as e:
        print(f"❌ RPC Error: {e.details()}")

    def chunk_generator():
        with open(filepath, "rb") as f:
            chunk_id = 0
            while True:
                data = f.read(CHUNK_SIZE_DEFAULT)
                if not data:
                    break
                checksum = hashlib.sha256(data).hexdigest()
                yield pb.ChunkUpload(upload_id=response.upload_id, filename=filename, chunk_id=chunk_id, data=data, checksum=checksum)
                chunk_id += 1
    
    try:
        resp = stub.PutChunks(chunk_generator(), metadata=auth_metadata)
        print("Upload result:", resp.success, resp.message)
    except grpc.RpcError as e:
        print(f"❌ RPC Error: {e.details()}")

if __name__ == "__main__":
    GATEWAY = "localhost:50051"
    USER = "demo"

    # 1. Start Login
    if login(GATEWAY, USER):
        # 2. Verify OTP
        if verify_otp(GATEWAY, USER):
            # 3. Perform Secure Actions
            put_file(GATEWAY, "./test_file.txt")