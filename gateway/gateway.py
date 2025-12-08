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

    # --- AUTHENTICATION ---
    
    def RequestOTP(self, request, context):
        print(f"[*] RequestOTP for {request.username}")
        
        # Check database for existing user
        user_row = self.db.get_user(request.username)
        target_contact = ""

        if user_row:
            # Existing User
            target_contact = user_row[1]
            print(f"   -> Existing user. Contact: {target_contact}")
        else:
            # New User Registration
            if not request.email_or_phone:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "New users must provide an email.")
            
            self.db.register_user(request.username, request.email_or_phone)
            target_contact = request.email_or_phone
            print(f"   -> New User Registered: {target_contact}")

        # Generate OTP
        otp_code = str(uuid.uuid4().int % 1000000).zfill(6)
        self.db.save_otp(request.username, otp_code)

        # Send Notification
        print(f"🔐 [BACKUP LOG] OTP: {otp_code}")
        
        if target_contact:
            send_notification(target_contact, otp_code)
            msg = f"OTP sent to {target_contact}"
        else:
            msg = "OTP generated (check logs)"

        return pb.RequestOTPResponse(ok=True, message=msg)

    def VerifyOTP(self, request, context):
        print(f"[*] VerifyOTP for {request.username}")
        ok, msg = self.db.verify_otp_db(request.username, request.otp_code)
        
        if not ok:
            return pb.VerifyOTPResponse(ok=False, message=msg)
        
        token = str(uuid.uuid4())
        self.db.save_token(request.username, token)
        print(f"✅ Login successful. Token saved.")
        return pb.VerifyOTPResponse(ok=True, token=token, message="Login successful")

    def ValidateToken(self, request, context):
        user = self.db.validate_token(request.token)
        if user:
            return pb.ValidateTokenResponse(valid=True, username=user)
        return pb.ValidateTokenResponse(valid=False)

    # --- FILE MANAGEMENT ---

    def RegisterNode(self, request, context):
        n = request.node
        self.db.register_node(n.node_id, n.ip, n.port, n.capacity_bytes, n.metadata)
        return pb.RegisterNodeResponse(ok=True, message="Node registered")

    def Heartbeat(self, request, context):
        cursor = self.db.conn.cursor()
        cursor.execute("UPDATE nodes SET last_seen=? WHERE node_id=?", (time.time(), request.node.node_id))
        self.db.conn.commit()
        return pb.HeartbeatResponse(ok=True, message="Pulse received")

    def PutMeta(self, request, context):
        print(f"[*] PutMeta request for {request.filename}")
        
        # 1. Validate Token
        username = self.db.validate_token(request.token)
        if not username:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")

        # 2. Filter Live Nodes
        all_nodes = self.db.list_nodes()
        live_nodes = []
        current_time = time.time()
        
        for row in all_nodes:
            # row: node_id, ip, port, capacity, last_seen, metadata
            if row[4] and (current_time - row[4] < 15):
                live_nodes.append(pb.NodeInfo(node_id=row[0], ip=row[1], port=row[2], capacity_bytes=row[3], metadata=row[5]))
        
        if len(live_nodes) < 1:
            context.abort(grpc.StatusCode.UNAVAILABLE, "No live nodes available!")

        # 3. Load Balance
        count = min(len(live_nodes), max(1, request.replication))
        selected_nodes = random.sample(live_nodes, count)
        print(f"[*] Assigning to {len(selected_nodes)} nodes.")

        # 4. Save Metadata
        upload_id = str(uuid.uuid4())
        total_chunks = (request.filesize + request.chunk_size - 1) // request.chunk_size
        node_ids = [n.node_id for n in selected_nodes]
        
        self.db.save_file_metadata(upload_id, request.filename, username, request.filesize, 
                                   request.chunk_size, total_chunks, node_ids)

        return pb.PutMetaResponse(
            upload_id=upload_id,
            nodes=selected_nodes,
            total_chunks=total_chunks,
            chunk_size=request.chunk_size,
            message="Upload initialized"
        )

    def GetMeta(self, request, context):
        username = self.db.validate_token(request.token)
        if not username: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        
        row = self.db.get_file_by_filename(request.filename)
        if not row: context.abort(grpc.StatusCode.NOT_FOUND, "File not found")
        
        # row: upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created
        all_nodes = self.db.list_nodes()
        target_nodes = []
        node_ids_in_file = row[5].split(",")
        
        for n_row in all_nodes:
            if n_row[0] in node_ids_in_file:
                target_nodes.append(pb.NodeInfo(node_id=n_row[0], ip=n_row[1], port=n_row[2], capacity_bytes=n_row[3], metadata=n_row[5]))

        return pb.GetMetaResponse(file=pb.FileLocation(
            upload_id=row[0], filename=row[1], filesize=row[2], chunk_size=row[3], 
            total_chunks=row[4], nodes=target_nodes, owner=username
        ))

    def ListFiles(self, request, context):
        username = self.db.validate_token(request.token)
        if not username: context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        
        rows = self.db.get_user_files(username)
        res = [pb.FileSummary(filename=r[0], upload_id=r[1], filesize=r[2], created_at=time.ctime(r[3])) for r in rows]
        return pb.ListFilesResponse(files=res, total=len(res))

# --- SERVER STARTUP (THIS WAS LIKELY MISSING) ---
def serve():
    print("--- Bluetap Gateway Starting ---")
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rpc.add_GatewayServicer_to_server(GatewayServicer(db), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Gateway running on [::]:50051")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)
        print("Gateway stopped.")

if __name__ == "__main__":
    serve()