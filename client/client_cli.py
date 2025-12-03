import grpc
import hashlib
import os
import sys

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

SESSION_TOKEN = None

def set_token(token):
    global SESSION_TOKEN
    SESSION_TOKEN = token
    
def get_token():
    return SESSION_TOKEN

# --- AUTHENTICATION ---

def login(gateway_addr, username, email_or_phone=""):
    """Request OTP, optionally sending it to email/phone."""
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    print(f"[*] Requesting OTP for {username} (Contact: {email_or_phone or 'None'})...")
    try:
        # Pass the email to the RequestOTP RPC
        response = stub.RequestOTP(pb.RequestOTPRequest(
            username=username, 
            email_or_phone=email_or_phone
        ))
        
        if response.ok:
            return True, response.message
        else:
            return False, response.message
            
    except grpc.RpcError as e:
        return False, str(e.details())

def verify_otp_and_get_token(gateway_addr, username, otp_code):
    global SESSION_TOKEN 
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    try:
        response = stub.VerifyOTP(pb.VerifyOTPRequest(username=username, otp_code=otp_code))
        if response.ok and response.token:
            SESSION_TOKEN = response.token
            return True, response.token
        return False, response.message
    except grpc.RpcError as e:
        return False, str(e.details())

def verify_otp(gateway_addr, username):
    """Interactive CLI version of verify."""
    otp_code = input("📩 Enter the 6-digit OTP: ")
    ok, token = verify_otp_and_get_token(gateway_addr, username, otp_code)
    if ok:
        print(f"✅ Authentication Successful!")
        return True
    print(f"❌ Verification failed.")
    return False

# --- FILE OPERATIONS ---

def list_files(gateway_addr):
    if not SESSION_TOKEN: return []
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    try:
        resp = stub.ListFiles(pb.ListFilesRequest(token=SESSION_TOKEN))
        return resp.files
    except grpc.RpcError:
        return []

def put_file(gateway_addr, filepath, progress_callback=None):
    if not SESSION_TOKEN: return False, "Not logged in"
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    channel = grpc.insecure_channel(gateway_addr)
    gateway_stub = rpc.GatewayStub(channel)

    try:
        meta_resp = gateway_stub.PutMeta(pb.PutMetaRequest(token=SESSION_TOKEN, filename=filename, filesize=filesize, chunk_size=524288, replication=2))
    except grpc.RpcError as e:
        return False, f"Gateway Error: {e.details()}"

    nodes = meta_resp.nodes
    if not nodes: return False, "No live nodes available"

    for i, target_node in enumerate(nodes):
        node_addr = f"{target_node.ip}:{target_node.port}"
        node_channel = grpc.insecure_channel(node_addr)
        node_stub = rpc.NodeServiceStub(node_channel)

        def chunk_generator():
            with open(filepath, "rb") as f:
                chunk_id = 0
                while True:
                    data = f.read(524288)
                    if not data: break
                    checksum = hashlib.sha256(data).hexdigest()
                    yield pb.ChunkUpload(upload_id=meta_resp.upload_id, filename=filename, chunk_id=chunk_id, data=data, checksum=checksum)
                    if progress_callback: progress_callback(chunk_id, filename, node_addr)
                    chunk_id += 1

        try:
            node_stub.PutChunks(chunk_generator())
        except grpc.RpcError:
            pass 
            
    return True, "Upload complete"

def download_file(gateway_addr, filename, output_path):
    if not SESSION_TOKEN: return False, "Not logged in"
    channel = grpc.insecure_channel(gateway_addr)
    gateway_stub = rpc.GatewayStub(channel)

    try:
        resp = gateway_stub.GetMeta(pb.GetMetaRequest(token=SESSION_TOKEN, filename=filename))
    except grpc.RpcError as e:
        return False, f"Gateway Error: {e.details()}"

    if not resp.file.nodes: return False, "No nodes found"

    target_node = resp.file.nodes[0]
    node_addr = f"{target_node.ip}:{target_node.port}"
    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    try:
        chunk_stream = node_stub.GetChunks(pb.GetChunksRequest(upload_id=resp.file.upload_id, start_chunk=0, end_chunk=resp.file.total_chunks))
        with open(output_path, "wb") as f:
            for chunk in chunk_stream:
                f.write(chunk.data)
        return True, "Download successful"
    except grpc.RpcError as e:
        return False, f"Node Error: {e.details()}"