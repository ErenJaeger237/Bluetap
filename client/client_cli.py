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
    
    # 1. Ask Gateway for Metadata/Permission
    print(f"[*] Requesting upload metadata for {filename}...")
    channel = grpc.insecure_channel(gateway_addr)
    gateway_stub = rpc.GatewayStub(channel)

    try:
        meta_resp = gateway_stub.PutMeta(
            pb.PutMetaRequest(
                token=SESSION_TOKEN, 
                filename=filename, 
                filesize=filesize,
                chunk_size=524288, # 512KB
                replication=1
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

    # 2. Upload Data to the Storage Node
    target_node = nodes[0]
    node_addr = f"{target_node.ip}:{target_node.port}"
    print(f"[*] Redirecting to Storage Node: {node_addr} (Upload ID: {upload_id})")

    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    def chunk_generator():
        with open(filepath, "rb") as f:
            chunk_id = 0
            while True:
                data = f.read(524288) # Read 512KB
                if not data:
                    break
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
        print(f"\n✅ Upload Result: {transfer_resp.message}")
        
    except grpc.RpcError as e:
        print(f"\n❌ Node Transfer Error: {e.details()}")

# --- DOWNLOAD (This was missing!) ---

def download_file(gateway_addr, filename, output_path):
    global SESSION_TOKEN
    
    if not SESSION_TOKEN:
        print("⛔ Error: You are not logged in.")
        return False

    # 1. Ask Gateway for Location
    print(f"[*] Requesting download metadata for {filename}...")
    channel = grpc.insecure_channel(gateway_addr)
    gateway_stub = rpc.GatewayStub(channel)

    try:
        resp = gateway_stub.GetMeta(pb.GetMetaRequest(token=SESSION_TOKEN, filename=filename))
    except grpc.RpcError as e:
        print(f"❌ Gateway Error: {e.details()}")
        return False

    file_info = resp.file
    if not file_info.nodes:
        print("❌ Error: No nodes found for this file.")
        return False

    # 2. Download from Node
    target_node = file_info.nodes[0]
    node_addr = f"{target_node.ip}:{target_node.port}"
    print(f"[*] Downloading from Node: {node_addr}")

    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    try:
        chunk_stream = node_stub.GetChunks(
            pb.GetChunksRequest(
                upload_id=file_info.upload_id,
                start_chunk=0,
                end_chunk=file_info.total_chunks
            )
        )
        
        with open(output_path, "wb") as f:
            chunks_received = 0
            for chunk in chunk_stream:
                f.write(chunk.data)
                chunks_received += 1
                print(f"   <- Received chunk {chunk.chunk_id}...", end='\r')
        
        print(f"\n✅ Download Complete: {output_path} ({chunks_received} chunks)")
        return True

    except grpc.RpcError as e:
        print(f"\n❌ Node Download Error: {e.details()}")
        return False