# gateway/gateway.py
import os, time, uuid, sqlite3, hashlib
from concurrent import futures
import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

from gateway.db import MetadataDB

DB_PATH = "gateway_meta.db"



    # ------------- USER CREATION -----------------
def create_user(self, username, password, email):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, NULL, NULL, NULL, NULL)",
                    (username, pw_hash, email))
        self.conn.commit()

    # ------------- PASSWORD CHECK -----------------
def verify_password(self, username, password):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        cur = self.conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            return False
        return row[0] == pw_hash

    # ------------- OTP ----------------------------
def save_otp(self, username, otp):
        expiry = time.time() + 300  # OTP valid for 5 minutes
        cur = self.conn.cursor()
        cur.execute("UPDATE users SET otp_code=?, otp_expiry=? WHERE username=?",
                    (otp, expiry, username))
        self.conn.commit()

def verify_otp(self, username, code):
        cur = self.conn.cursor()
        cur.execute("SELECT otp_code, otp_expiry FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            return False, "User not found"

        otp, expiry = row
        if otp != code:
            return False, "Invalid OTP"
        if time.time() > expiry:
            return False, "OTP expired"

        return True, "OK"

    # ------------- TOKEN MANAGEMENT ---------------
def save_token(self, username, token):
        expiry = time.time() + 3600  # 1 hour
        cur = self.conn.cursor()
        cur.execute("UPDATE users SET token=?, token_expiry=? WHERE username=?",
                    (token, expiry, username))
        self.conn.commit()

def validate_token(self, token):
        cur = self.conn.cursor()
        cur.execute("SELECT username, token_expiry FROM users WHERE token=?", (token,))
        row = cur.fetchone()
        if not row:
            return False, None
        user, expiry = row
        if time.time() > expiry:
            return False, None
        return True, user

class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db
        self.tokens = {}  # token -> {user, created}

    def _check_auth(self, context):
        try:
            metadata = dict(context.invocation_metadata())
            token = metadata.get('authorization', '').replace('Bearer ', '')
            if not token or token not in self.tokens:
                return False, "Invalid or missing token"
            return True, self.tokens[token]["user"]
        except Exception as e:
            return False, str(e)

    # Auth
    def Login(self, request, context):
        # Very simple: accept any username/password, return token in message
        token = str(uuid.uuid4())
        self.tokens[token] = {"user": request.username, "created": time.time()}
        return pb.LoginResponse(next_action="TOKEN", message=token)

    # Node registration
    def RegisterNode(self, request, context):
        node = request.node
        self.db.register_node(node.node_id, node.ip, node.port, node.capacity_bytes, node.metadata or "")
        return pb.RegisterNodeResponse(ok=True, message="registered")

    # Put meta: create upload record and choose nodes (coordinator reads DB directly)
    def PutMeta(self, request, context):
        # --- SECURITY CHECK ---
        is_valid, user_or_error = self._check_auth(context)
        if not is_valid:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, f"⛔ {user_or_error}")
        # ----------------------

        print(f"[*] Authenticated upload request from: {user_or_error}")
        print(f"[*] File: {request.filename}, Size: {request.size}")

        # ... (The rest of your existing logic for choosing nodes/upload_id) ...
        
        return pb.PutMetaResponse(
            ok=True,
            upload_id=str(uuid.uuid4()), # Example ID
            nodes=[] # Add your node logic here
        )

    def GetMeta(self, request, context):
        token = request.token
        if token not in self.tokens:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
        row = self.db.get_file_by_filename(request.filename)
        if not row:
            return pb.GetMetaResponse()  # empty

        upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created = row
        nodes = []
        for nid in nodes_csv.split(","):
            # lookup each node IP/port
            for r in self.db.list_nodes():
                if r[0] == nid:
                    node_id, ip, port, capacity, last_seen, metadata = r
                    nodes.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity, metadata=metadata))
                    break
        fileloc = pb.FileLocation(upload_id=upload_id, nodes=nodes, filesize=filesize, chunk_size=chunk_size, total_chunks=total_chunks, filename=filename, owner=self.tokens[token]["user"])
        return pb.GetMetaResponse(file=fileloc)
# C:\Users\NTS\Documents\bluetap\gateway\gateway.py
def serve(address="[::]:50051"):
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # KEEP THIS CORRECT LINE:
    rpc.add_GatewayServicer_to_server(GatewayServicer(db), server)
    
    server.add_insecure_port(address)
    # ... rest of function
    server.start()
    print("Gateway running on", address)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()