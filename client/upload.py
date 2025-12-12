import grpc, hashlib, os
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc


def upload_file(gateway_addr, token, filepath, chunk_size, replication):
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    # STEP 1 → Ask gateway for metadata
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)

    meta = stub.PutMeta(pb.PutMetaRequest(
        token=token,
        filename=filename,
        filesize=filesize,
        chunk_size=chunk_size,
        replication=replication,
    ))

    upload_id = meta.upload_id
    nodes = meta.nodes

    if not nodes:
        print("ERROR: Gateway returned no nodes.")
        return

    # upload to the first node
    node = nodes[0]
    node_addr = f"{node.ip}:{node.port}"

    print(f"Uploading to node {node_addr} ...")

    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    def chunk_stream():
        with open(filepath, "rb") as f:
            chunk_id = 0
            while True:
                data = f.read(chunk_size)
                if not data:
                    break

                checksum = hashlib.sha256(data).hexdigest()

                yield pb.ChunkUpload(
                    upload_id=upload_id,
                    filename=filename,
                    chunk_id=chunk_id,
                    data=data,
                    checksum=checksum,
                    last_chunk=False,
                )

                chunk_id += 1

    resp = node_stub.PutChunks(chunk_stream())
    print("Upload result:", resp.message)
