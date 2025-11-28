# node/node_server.py
import os, time, argparse
from concurrent import futures
import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from node.virtual_disk import VirtualDisk  # relative import if module installed

class NodeServicer(rpc.NodeServiceServicer):
    def __init__(self, storage_root):
        self.disk = VirtualDisk(storage_root)
    def PutChunks(self, request_iterator, context):
        upload_id = None; filename = None; total_written = 0
        # If client sends a first metadata message, handle it; else accept stream of chunks
        for chunk in request_iterator:
            upload_id = chunk.upload_id; filename = chunk.filename; cid = chunk.chunk_id; data = chunk.data; checksum = chunk.checksum
            # ensure manifest exists: create if missing with conservative defaults
            try:
                ok = self.disk.write_chunk(upload_id, cid, data, checksum)
            except Exception:
                ok = False
            if not ok:
                return pb.UploadResult(success=False, message=f"checksum mismatch for chunk {cid}", received_chunks=total_written)
            total_written += 1
        if self.disk.is_complete(upload_id):
            return pb.UploadResult(success=True, message=f"all chunks received ({total_written})", received_chunks=total_written)
        else:
            return pb.UploadResult(success=True, message=f"partial received ({total_written})", received_chunks=total_written)

    def GetChunks(self, request, context):
        upload_id = request.upload_id
        start = request.start_chunk or 0
        end = request.end_chunk or self.disk.get_chunk_count(upload_id)
        for cid in range(start, end):
            data = self.disk.read_chunk(upload_id, cid)
            if data is None:
                continue
            checksum = __import__("hashlib").sha256(data).hexdigest()
            yield pb.Chunk(chunk_id=cid, data=data, checksum=checksum)

    def Heartbeat(self, request, context):
        # Accept heartbeat; in real system we'd notify coordinator/gateway
        return pb.HeartbeatResponse(ok=True, message="heartbeat accepted")

    def RepairTasks(self, request, context):
        # stub: no repair tasks
        return pb.RepairResponse(ok=True, message="no tasks", missing_chunks=[])

def register_with_gateway(gateway_addr, node_id, ip, port, capacity):
    import grpc
    from generated import bluetap_pb2 as pb
    from generated import bluetap_pb2_grpc as rpc
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
    # attempt to register with gateway once
    try:
        register_with_gateway(gateway_addr, node_id, host, port, capacity=10 * 1024**3)
    except Exception as e:
        print("Node registration note:", e)
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
    parser.add_argument("--gateway", default="127.0.0.1:50052")
    args = parser.parse_args()
    os.makedirs(args.storage, exist_ok=True)
    serve(args.node_id, args.storage, args.host, args.port, args.gateway)
