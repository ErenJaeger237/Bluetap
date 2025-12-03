import os
import time
import uuid
import sys
import random
from concurrent import futures
import grpc

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from gateway.db import MetadataDB
from gateway.notifications import send_notification

class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db

    def RequestOTP(self, request, context):
        username = request.username
        provided_contact = request.email_or_phone
        
        print(f"[*] Login Request: {username}")

        # 1. Check if user exists in DB
        user_row = self.db.get_user(username)
        
        target_contact = ""

        if user_row:
            # === EXISTING USER ===
            # user_row = (username, email)
            target_contact = user_row[1]
            print(f"   -> Found existing user. Sending OTP to stored contact: {target_contact}")
        else:
            # === NEW USER (REGISTRATION) ===
            if not provided_contact:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "User not found. Please provide email/phone to register.")
            
            # Register them
            self.db.register_user(username, provided_contact)
            target_contact = provided_contact
            print(f"   -> New User! Registered {username} with {target_contact}")

        # 2. Generate OTP
        otp_code = str(uuid.uuid4().int % 1000000).zfill(6)
        self.db.save_otp(username, otp_code)

        # 3. Send Notification (Email/SMS)
        # We also print to terminal as a backup for the demo
        print(f"🔐 [BACKUP LOG] OTP for {username}: {otp_code}")
        
        if target_contact:
            send_notification(target_contact, otp_code)
            msg = f"OTP sent to {target_contact}"
        else:
            msg = "OTP generated (check logs)"

        return pb.RequestOTPResponse(ok=True, message=msg)

    def VerifyOTP(self, request, context):
        ok, msg = self.db.verify_otp_db(request.username, request.otp_code)
        if not ok:
            return pb.VerifyOTPResponse(ok=False, message=msg)
        
        token = str(uuid.uuid4())
        self.db.save_token(request.username, token)
        return pb.VerifyOTPResponse(ok=True, token=token, message="Login successful")

    def ValidateToken(self, request, context):
        user = self.db.validate_token(request.token)
        if user: return pb.ValidateTokenResponse(valid=True, username=user)
        return pb.ValidateTokenResponse(valid=False)

    # --- FILE LOGIC (Standard) ---
    
    def RegisterNode(self, request, context):
        n = request.node
        self.db.register_node(n.node_id, n.ip, n.port, n.capacity_bytes, n.metadata)
        return pb.RegisterNodeResponse(ok=True, message="Node registered")

    def Heartbeat(self, request, context):
        # Update last_seen
        cursor = self.db.conn.cursor()
        cursor.execute("UPDATE nodes SET last_seen=? WHERE node_id=?", (time.time(), request.node.node_id))
        self.db.conn.commit()
        return pb.HeartbeatResponse(ok=True, message="Pulse")

    def PutMeta(self, request, context):
        user = self.db.validate_token(request.token)
        if not user: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")

        # Live node check
        all_nodes = self.db.list_nodes()
        live = []
        now = time.time()
        for r in all_nodes:
            if r[4] and (now - r[4] < 15): 
                live.append(pb.NodeInfo(node_id=r[0], ip=r[1], port=r[2], capacity_bytes=r[3], metadata=r[5]))
        
        if not live: context.abort(grpc.StatusCode.UNAVAILABLE, "No live nodes")

        count = min(len(live), max(1, request.replication))
        selected = random.sample(live, count)
        
        upid = str(uuid.uuid4())
        total_chunks = (request.filesize + request.chunk_size - 1) // request.chunk_size
        nids = [n.node_id for n in selected]
        
        self.db.save_file_metadata(upid, request.filename, user, request.filesize, request.chunk_size, total_chunks, nids)
        
        return pb.PutMetaResponse(upload_id=upid, nodes=selected, total_chunks=total_chunks, chunk_size=request.chunk_size)

    def GetMeta(self, request, context):
        user = self.db.validate_token(request.token)
        if not user: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        
        row = self.db.get_file_by_filename(request.filename)
        if not row: context.abort(grpc.StatusCode.NOT_FOUND, "File not found")
        
        # row: upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created
        # Reconstruct nodes
        all_nodes = self.db.list_nodes()
        target_nodes = []
        nids = row[5].split(",")
        for r in all_nodes:
            if r[0] in nids:
                target_nodes.append(pb.NodeInfo(node_id=r[0], ip=r[1], port=r[2], capacity_bytes=r[3], metadata=r[5]))

        return pb.GetMetaResponse(file=pb.FileLocation(
            upload_id=row[0], filename=row[1], filesize=row[2], chunk_size=row[3], 
            total_chunks=row[4], nodes=target_nodes, owner=user
        ))

    def ListFiles(self, request, context):
        user = self.db.validate_token(request.token)
        if not user: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        
        # Only get THIS user's files
        rows = self.db.get_user_files(user)
        res = [pb.FileSummary(filename=r[0], upload_id=r[1], filesize=r[2], created_at=time.ctime(r[3])) for r in rows]
        return pb.ListFilesResponse(files=res, total=len(res))

def serve():
    print("--- Bluetap Gateway Starting ---")
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rpc.add_GatewayServicer_to_server(GatewayServicer(db), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Gateway running on [::]:50051")
    try:
        while True: time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()