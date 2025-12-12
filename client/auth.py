import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc


def login(gateway_addr, username, password):
    channel = grpc.insecure_channel(gateway_addr)
    stub = rpc.AuthServiceStub(channel)
    resp = stub.Login(pb.LoginRequest(username=username, password=password))

    # old code returned resp.message as token — WRONG
    # new code handles next_action
    if resp.next_action == "OTP_REQUIRED":
        print("OTP required. Use: client.cli request-otp ... (to be added)")
        return None

    return resp.message  # assume message = token for now
