import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc


def list_files(gateway_addr, token):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)

    resp = stub.ListFiles(pb.ListFilesRequest(token=token, limit=50, offset=0))

    print("Files:")
    for f in resp.files:
        print(f"- {f.filename} ({f.filesize} bytes)")

    print("Total:", resp.total)


def file_info(gateway_addr, token, filename):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.GatewayStub(channel)

    resp = stub.GetMeta(pb.GetMetaRequest(token=token, filename=filename))

    if not resp.file.filename:
        print("File not found.")
        return

    file = resp.file
    print("File Info:")
    print("Filename:", file.filename)
    print("Size:", file.filesize)
    print("Stored on nodes:")
    for n in file.nodes:
        print(f" - {n.node_id} @ {n.ip}:{n.port}")
