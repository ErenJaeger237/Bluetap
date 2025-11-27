import grpc, time, argparse, os
from concurrent import futures
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from virtual_disk import VirtualDisk

class NodeServicer(rpc.NodeServiceServicer):
    def __init__(self, storage_root):
        self.disk = VirtualDisk(storage_root)
    def PutChunks(self, request_iterator, context):
        upload_id = None; filename = None; total_written = 0
        for chunk in request_iterator:
            upload_id = chunk.upload_id; filename = chunk.filename; cid = chunk.chunk_id; data = chunk.data; checksum = chunk.checksum
            ok = self.disk.write_chunk(upload_id, cid, data, checksum)
            if not ok:
                return pb.UploadResult(success=False, message=f"checksum mismatch for chunk {cid}")
            total_written += 1
        if self.disk.is_complete(upload_id):
            return pb.UploadResult(success=True, message=f"all chunks received ({total_written})")
        else:
            return pb.UploadResult(success=True, message=f"partial received ({total_written})")

def register_with_gateway(gateway_addr, node_id, ip, port, capacity):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    node = pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity)
    req = pb.RegisterNodeRequest(node=node)
    try:
        resp = stub.RegisterNode(req)
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
    register_with_gateway(gateway_addr, node_id, host, port, capacity=10 * 1024**3)
    print(f"Node {node_id} running on {bind_addr}, storage={storage_root}")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
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
