import grpc
import hashlib
import os
import sys

# Adjust path to find generated modules
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

SESSION_TOKEN = None

# --- AUTHENTICATION ---

def login(gateway_addr, username):
    """Step 1: Ask Gateway to send an OTP."""
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    print(f"[*] Requesting OTP for {username}...")
    try:
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
    global SESSION_TOKEN 
    
    otp_code = input("📩 Enter the 6-digit OTP: ")
    
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    
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

# --- UPLOAD ---

def put_file(gateway_addr, filepath):
    global SESSION_TOKEN
    
    if not SESSION_TOKEN:
        print("⛔ Error: You are not logged in.")
        return

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    
    # --- STEP 1: Ask Gateway for Permission (With Replication) ---
    print(f"[*] Requesting upload metadata for {filename} (Replication=2)...")
    channel = grpc.insecure_channel(gateway_addr)
    gateway_stub = rpc.GatewayStub(channel)

    try:
        # REQUEST REPLICATION = 2 HERE
        meta_resp = gateway_stub.PutMeta(
            pb.PutMetaRequest(
                token=SESSION_TOKEN, 
                filename=filename, 
                filesize=filesize,
                chunk_size=524288,
                replication=2  # <--- CHANGED FROM 1 TO 2
            )
        )
    except grpc.RpcError as e:
        print(f"❌ Gateway Error: {e.details()}")
        return

    upload_id = meta_resp.upload_id
    nodes = meta_resp.nodes

    if not nodes:
        print("❌ Error: Gateway returned no storage nodes.")
        return

    print(f"[*] Gateway assigned {len(nodes)} storage nodes.")

    # --- STEP 2: Loop Through Nodes and Upload to Each ---
    for i, target_node in enumerate(nodes):
        node_addr = f"{target_node.ip}:{target_node.port}"
        print(f"\n🚀 [Replica {i+1}/{len(nodes)}] Uploading to Node: {node_addr}")

        node_channel = grpc.insecure_channel(node_addr)
        node_stub = rpc.NodeServiceStub(node_channel)

        # We redefine the generator here so it opens the file fresh for every node
        def chunk_generator():
            with open(filepath, "rb") as f:
                chunk_id = 0
                while True:
                    data = f.read(524288)
                    if not data: break
                    checksum = hashlib.sha256(data).hexdigest()
                    yield pb.ChunkUpload(
                        upload_id=upload_id, 
                        filename=filename, 
                        chunk_id=chunk_id, 
                        data=data, 
                        checksum=checksum
                    )
                    chunk_id += 1
                    print(f"   -> Sending chunk {chunk_id}...", end='\r')

        try:
            transfer_resp = node_stub.PutChunks(chunk_generator())
            print(f"\n   ✅ Success: {transfer_resp.message}")
        except grpc.RpcError as e:
            print(f"\n   ❌ Error uploading to this node: {e.details()}")

    print("\n✅ All replications processed.")

    # ... (existing code) ...

def set_token(token):
    """Helper to set the session token from an external script."""
    global SESSION_TOKEN
    SESSION_TOKEN = token
    
def get_token():
    """Helper to get the current token."""
    return SESSION_TOKEN