import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc


def download_file(gateway_addr, token, filename):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)

    meta = stub.GetMeta(pb.GetMetaRequest(token=token, filename=filename))

    if not meta.file.nodes:
        print("ERROR: File not found.")
        return

    node = meta.file.nodes[0]
    node_addr = f"{node.ip}:{node.port}"

    print(f"Downloading from {node_addr} ...")

    node_channel = grpc.insecure_channel(node_addr)
    node_stub = rpc.NodeServiceStub(node_channel)

    stream = node_stub.GetChunks(pb.GetChunksRequest(
        upload_id=meta.file.upload_id,
        start_chunk=0,
        end_chunk=meta.file.total_chunks,
    ))

    with open(filename, "wb") as f:
        for chunk in stream:
            f.write(chunk.data)

    print("Download complete:", filename)
