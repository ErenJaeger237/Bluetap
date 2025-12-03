import os
import time
import argparse
import threading
from concurrent import futures
import grpc
import sys

# Ensure we can find the generated modules
if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from node.virtual_disk import VirtualDisk 

# --- HEARTBEAT THREAD ---
# --- HEARTBEAT THREAD (CORRECTED) ---
def heartbeat_loop(gateway_addr, node_id, port):
    """Background thread that sends a pulse every 5 seconds."""
    print(f"💓 Heartbeat service started for {node_id}")
    
    # Wait a moment for server to start
    time.sleep(2)
    
    while True:
        try:
            channel = grpc.insecure_channel(gateway_addr)
            stub = rpc.GatewayStub(channel)
            
            # Create a NodeInfo object
            node_info = pb.NodeInfo(
                node_id=node_id, 
                ip="127.0.0.1", 
                port=port, 
                capacity_bytes=10*1024**3,
                metadata="alive"
            )
            
            # USE RegisterNode AS HEARTBEAT
            # This is safe because it updates 'last_seen' in the DB
            stub.RegisterNode(pb.RegisterNodeRequest(node=node_info))
            
            # Optional: Print a dot so you know it's working
            # print(".", end="", flush=True)

        except Exception as e:
            # Don't crash if gateway is down
            print(f"💔 Heartbeat failed: {e}")
        
        time.sleep(5) # Pulse every 5 seconds
# --- NODE SERVICER ---
class NodeServicer(rpc.NodeServiceServicer):
    def __init__(self, storage_root):
        self.disk = VirtualDisk(storage_root)

    def PutChunks(self, request_iterator, context):
        total_written = 0
        try:
            for chunk in request_iterator:
                # Basic validation
                if not chunk.data: continue
                
                # Write to disk
                ok = self.disk.write_chunk(chunk.upload_id, chunk.chunk_id, chunk.data, chunk.checksum)
                if not ok:
                    print(f"❌ Checksum mismatch for chunk {chunk.chunk_id}")
                    return pb.UploadResult(success=False, message=f"checksum mismatch for chunk {chunk.chunk_id}", received_chunks=total_written)
                
                total_written += 1
                
            return pb.UploadResult(success=True, message=f"all chunks received ({total_written})", received_chunks=total_written)
        except Exception as e:
            print(f"❌ Upload Error: {e}")
            return pb.UploadResult(success=False, message=str(e), received_chunks=total_written)

    def GetChunks(self, request, context):
        # Determine how many chunks to read
        # If end_chunk is 0 or -1, we need to look up total chunks from disk
        end = request.end_chunk
        if end <= 0:
            end = self.disk.get_chunk_count(request.upload_id)

        for cid in range(request.start_chunk, end):
            data = self.disk.read_chunk(request.upload_id, cid)
            if data is None:
                continue
            # Calculate checksum for verification
            checksum = __import__("hashlib").sha256(data).hexdigest()
            yield pb.Chunk(chunk_id=cid, data=data, checksum=checksum)

    def Heartbeat(self, request, context):
        return pb.HeartbeatResponse(ok=True, message="heartbeat accepted")

    def RepairTasks(self, request, context):
        return pb.RepairResponse(ok=True, message="no tasks", missing_chunks=[])

def register_with_gateway(gateway_addr, node_id, ip, port, capacity):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    node = pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity, metadata="")
    try:
        resp = stub.RegisterNode(pb.RegisterNodeRequest(node=node))
        print("Register response:", resp.ok, resp.message)
    except Exception as e:
        print("Register failed:", e)

def serve(node_id, storage_root, host, port, gateway_addr):
    servicer = NodeServicer(storage_root)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    rpc.add_NodeServiceServicer_to_server(servicer, server)
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    server.start()
    print(f"Node {node_id} running on {bind_addr}, storage={storage_root}")
    
    # 1. Attempt Registration
    try:
        register_with_gateway(gateway_addr, node_id, host, port, capacity=10 * 1024**3)
    except Exception as e:
        print("Node registration note:", e)

    # 2. START HEARTBEAT THREAD
    hb_thread = threading.Thread(
        target=heartbeat_loop, 
        args=(gateway_addr, node_id, port),
        daemon=True
    )
    hb_thread.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("node shutting down")
        server.stop(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", default=f"node-{int(time.time())%10000}")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50061)
    parser.add_argument("--storage", default="./node_storage")
    parser.add_argument("--gateway", default="127.0.0.1:50051")
    args = parser.parse_args()
    
    os.makedirs(args.storage, exist_ok=True)
    serve(args.node_id, args.storage, args.host, args.port, args.gateway)