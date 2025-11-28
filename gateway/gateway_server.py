import sqlite3
import os
import uuid
import time
import sys
from concurrent import futures
import grpc
import threading

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc
from gateway.db import MetadataDB

DB_PATH = "gateway_meta.db"

class MetadataDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()

    def _init(self):
        cur = self.conn.cursor()

        # ========== USERS TABLE ==========
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            email TEXT
        )
        """)

        # ========== NODES TABLE (FIXED) ==========
        cur.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            ip TEXT,
            port INTEGER,
            capacity_bytes INTEGER,
            metadata TEXT,
            last_seen REAL
        )
        """)

        # ========== FILES TABLE (FIXED) ==========
        # stores metadata returned by PutMeta
        cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            upload_id TEXT PRIMARY KEY,
            filename TEXT,
            owner TEXT,
            filesize INTEGER,
            chunk_size INTEGER,
            total_chunks INTEGER,
            nodes_json TEXT,   -- JSON encoded NodeInfo list
            created REAL
        )
        """)

        self.conn.commit()

    # user helpers
    def add_user(self, username, password, email=""):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO users(username,password,email) VALUES (?,?,?)", (username,password,email))
        self.conn.commit()

    # node registry
    def register_node(self, node_id, ip, port, capacity):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO nodes(node_id,ip,port,capacity,last_seen) VALUES (?,?,?,?,?)",
                    (node_id, ip, port, capacity, time.time()))
        self.conn.commit()

    def list_nodes(self):
        cur = self.conn.cursor()
        cur.execute("SELECT node_id,ip,port,capacity,last_seen FROM nodes")
        return cur.fetchall()

    def save_file_metadata(self, upload_id, filename, owner, filesize, chunk_size, total_chunks, nodes):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO files(upload_id,filename,owner,filesize,chunk_size,total_chunks,nodes,created) VALUES (?,?,?,?,?,?,?,?)",
                    (upload_id, filename, owner, filesize, chunk_size, total_chunks, ",".join(nodes), time.time()))
        self.conn.commit()

    def get_file(self, filename):
        cur = self.conn.cursor()
        cur.execute("SELECT upload_id,filename,filesize,chunk_size,total_chunks,nodes FROM files WHERE filename=?", (filename,))
        return cur.fetchone()

# --- Gateway Servicer ---
class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db
        # for demo, store ephemeral tokens in memory
        self.tokens = {}
        # simple OTP store (for extension)
        self.otps = {}

    def Login(self, request, context):
        # For demo: accept any username/password; create user if missing
        self.db.add_user(request.username, request.password, "")
        # generate ephemeral token (no JWT here for simplicity)
        token = str(uuid.uuid4())
        self.tokens[token] = {"user": request.username, "created": time.time()}
        return pb.AuthResponse(token=token, message="Logged in (demo token)")

    def PutMeta(self, request, context):
        # Very light validation
        token = request.token
        if token not in self.tokens:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
        upload_id = str(uuid.uuid4())
        total_chunks = (request.filesize + request.chunk_size - 1) // request.chunk_size
        # choose nodes: naive - all registered nodes, sorted by last_seen
        nodes_rows = self.db.list_nodes()
        if not nodes_rows:
            context.abort(grpc.StatusCode.UNAVAILABLE, "no nodes available")
        # select first N nodes
        selected = []
        for r in nodes_rows[: max(1, request.replication)]:
            node_id, ip, port, capacity, last_seen = r
            selected.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity))
        # persist file metadata (owner = username)
        owner = self.tokens[token]["user"]
        self.db.save_file_metadata(upload_id, request.filename, owner, request.filesize, request.chunk_size, total_chunks, [n.node_id for n in selected])
        resp = pb.PutMetaResponse(upload_id=upload_id, nodes=selected, total_chunks=total_chunks)
        return resp

    def RegisterNode(self, request, context):
        node = request.node
        self.db.register_node(node.node_id, node.ip, node.port, node.capacity_bytes)
        return pb.RegisterNodeResponse(ok=True, message="registered")

    def GetMeta(self, request, context):
        row = self.db.get_file(request.filename)
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "file not found")
        upload_id, filename, filesize, chunk_size, total_chunks, nodes_str = row
        nodes = []
        for nid in nodes_str.split(","):
            # naive node lookup
            cur = self.db.conn.cursor()
            cur.execute("SELECT node_id,ip,port,capacity,last_seen FROM nodes WHERE node_id=?", (nid,))
            res = cur.fetchone()
            if res:
                node_id, ip, port, capacity, last_seen = res
                nodes.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity))
        return pb.GetMetaResponse(filename=filename, filesize=filesize, chunk_size=chunk_size, total_chunks=total_chunks, nodes=nodes)

# --- serve ---
def serve(address="[::]:50051"):
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rpc.add_GatewayServicer_to_server(GatewayServicer(db), server)
    server.add_insecure_port(address)
    server.start()
    print("Gateway running on", address)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
