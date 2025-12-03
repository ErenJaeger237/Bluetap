import os
import time
import uuid
import sys
from concurrent import futures
import grpc

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from gateway.db import MetadataDB

class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db
        # REMOVED: self.tokens = {} (No longer needed!)

    # --- AUTHENTICATION ---
    
    def RequestOTP(self, request, context):
        print(f"[*] RequestOTP for {request.username}")
        # Ensure user exists in DB
        self.db.add_user(request.username, "demo_pass", "")
        otp_code = str(uuid.uuid4().int % 1000000).zfill(6)
        print(f"🔐 [OTP GENERATED]: {otp_code}")
        return pb.RequestOTPResponse(ok=True, message="OTP generated")

    def VerifyOTP(self, request, context):
        print(f"[*] VerifyOTP for {request.username}")
        # Generate persistent token
        token = str(uuid.uuid4())
        
        # SAVE TO DB (Persistent!)
        self.db.save_token(request.username, token)
        
        print(f"✅ Login successful. Token saved to DB.")
        return pb.VerifyOTPResponse(ok=True, token=token, message="Login successful")

    def ValidateToken(self, request, context):
        # CHECK DB
        username = self.db.validate_token(request.token)
        if username:
            return pb.ValidateTokenResponse(valid=True, username=username)
        return pb.ValidateTokenResponse(valid=False)

    # --- FILE MANAGEMENT ---

    def RegisterNode(self, request, context):
        n = request.node
        self.db.register_node(n.node_id, n.ip, n.port, n.capacity_bytes, n.metadata)
        return pb.RegisterNodeResponse(ok=True, message="Node registered")

    def Heartbeat(self, request, context):
        # Update heartbeat via RegisterNode logic or direct DB update
        # For this version, we trust the DB update in RegisterNode or manual update here
        cursor = self.db.conn.cursor()
        cursor.execute("UPDATE nodes SET last_seen=? WHERE node_id=?", (time.time(), request.node.node_id))
        self.db.conn.commit()
        return pb.HeartbeatResponse(ok=True, message="Pulse received")

    def PutMeta(self, request, context):
        print(f"[*] PutMeta request for {request.filename}")
        
        # 1. Validate Token via DB
        username = self.db.validate_token(request.token)
        if not username:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or expired token")

        # 2. Filter LIVE nodes
        all_nodes = self.db.list_nodes()
        live_nodes = []
        current_time = time.time()
        
        for row in all_nodes:
            node_id, ip, port, capacity, last_seen, metadata = row
            if last_seen and (current_time - last_seen < 15):
                live_nodes.append(pb.NodeInfo(
                    node_id=node_id, ip=ip, port=port, 
                    capacity_bytes=capacity, metadata=metadata
                ))
            else:
                if last_seen:
                    print(f"⚠️ Node {node_id} is DEAD/OFFLINE (Last seen: {current_time - last_seen:.1f}s ago)")

        if len(live_nodes) < 1:
            context.abort(grpc.StatusCode.UNAVAILABLE, "No live nodes available!")

        # 3. Select Nodes (Replication)
        selected_nodes = live_nodes[:max(1, request.replication)]
        print(f"[*] Assigning upload to {len(selected_nodes)} live nodes.")

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
        print(f"[*] GetMeta request for {request.filename}")
        
        # Validate Token via DB
        username = self.db.validate_token(request.token)
        if not username:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or expired token")

        row = self.db.get_file_by_filename(request.filename)
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "File not found")

        upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created = row

        all_nodes = self.db.list_nodes()
        target_nodes = []
        node_ids_in_file = nodes_csv.split(",")
        
        for n_row in all_nodes:
            if n_row[0] in node_ids_in_file:
                target_nodes.append(pb.NodeInfo(
                    node_id=n_row[0], ip=n_row[1], port=n_row[2],
                    capacity_bytes=n_row[3], metadata=n_row[5]
                ))

        return pb.GetMetaResponse(file=pb.FileLocation(
            upload_id=upload_id, filename=filename, filesize=filesize,
            chunk_size=chunk_size, total_chunks=total_chunks, nodes=target_nodes,
            owner=username
        ))

    def ListFiles(self, request, context):
        return pb.ListFilesResponse(files=[], total=0)

def serve(address="[::]:50051"):
    print("--- Bluetap Gateway Starting ---")
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rpc.add_GatewayServicer_to_server(GatewayServicer(db), server)
    server.add_insecure_port(address)
    server.start()
    print(f"Gateway running on {address}")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)
        print("Gateway stopped.")

if __name__ == "__main__":
    serve()