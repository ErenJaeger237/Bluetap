import grpc
import os
import sys
import hashlib
import math
import argparse
from generated import bluetap_pb2 as pb

from generated import bluetap_pb2_grpc as rpc

CHUNK_SIZE_DEFAULT = 512 * 1024  # 512 KB

def login(gateway_addr, username, password):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)
    resp = stub.Login(pb.AuthRequest(username=username, password=password))
    return resp.token

def put_file(gateway_addr, token, filepath, chunk_size=CHUNK_SIZE_DEFAULT, replication=1):
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)

    meta_resp = stub.PutMeta(pb.PutMetaRequest(token=token, filename=filename, filesize=filesize, chunk_size=chunk_size, replication=replication))
    upload_id = meta_resp.upload_id
    nodes = meta_resp.nodes
    total_chunks = meta_resp.total_chunks
    print("Upload ID:", upload_id, "nodes:", [(n.node_id,n.ip,n.port) for n in nodes], "total_chunks:", total_chunks)

    # for demo: stream to first node
    first = nodes[0]
    node_addr = f"{first.ip}:{first.port}"
    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    def chunk_generator():
        with open(filepath, "rb") as f:
            chunk_id = 0
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                checksum = hashlib.sha256(data).hexdigest()
                yield pb.ChunkUpload(upload_id=upload_id, filename=filename, chunk_id=chunk_id, data=data, checksum=checksum)
                chunk_id += 1

    resp = node_stub.PutChunks(chunk_generator())
    print("Upload result:", resp.success, resp.message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="127.0.0.1:50051")
    parser.add_argument("action", choices=["login","put"])
    parser.add_argument("--user", default="demo")
    parser.add_argument("--passw", default="demo")
    parser.add_argument("--file", default=None)
    args = parser.parse_args()

    if args.action == "login":
        token = login(args.gateway, args.user, args.passw)
        print("token:", token)
    elif args.action == "put":
        if not args.file:
            print("missing --file")
            sys.exit(1)
        token = login(args.gateway, args.user, args.passw)
        put_file(args.gateway, token, args.file)
