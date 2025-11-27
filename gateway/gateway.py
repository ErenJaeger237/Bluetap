import os, time, uuid
from concurrent import futures
import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

DB_PATH = os.environ.get("BLUETAP_META_DB", "gateway_meta.db")
import sqlite3

class MetadataDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()
    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS nodes (node_id TEXT PRIMARY KEY, ip TEXT, port INTEGER, capacity INTEGER, last_seen REAL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS files (upload_id TEXT PRIMARY KEY, filename TEXT, owner TEXT, filesize INTEGER, chunk_size INTEGER, total_chunks INTEGER, nodes TEXT, created REAL)""")
        self.conn.commit()
    def register_node(self, node_id, ip, port, capacity):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO nodes(node_id,ip,port,capacity,last_seen) VALUES (?,?,?,?,?)",
                    (node_id, ip, port, capacity, time.time()))
        self.conn.commit()
    def list_nodes(self):
        cur = self.conn.cursor()
        cur.execute("SELECT node_id,ip,port,capacity,last_seen FROM nodes ORDER BY last_seen DESC")
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

class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db
        self.tokens = {}
    def PutMeta(self, request, context):
        token = request.token
        if token not in self.tokens:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
        upload_id = str(uuid.uuid4())
        total_chunks = (request.filesize + request.chunk_size - 1) // request.chunk_size
        nodes_rows = self.db.list_nodes()
        if not nodes_rows:
            context.abort(grpc.StatusCode.UNAVAILABLE, "no nodes available")
        selected = []
        for r in nodes_rows[: max(1, request.replication)]:
            node_id, ip, port, capacity, last_seen = r
            selected.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity))
        owner = self.tokens[token]["user"]
        self.db.save_file_metadata(upload_id, request.filename, owner, request.filesize, request.chunk_size, total_chunks, [n.node_id for n in selected])
        return pb.PutMetaResponse(upload_id=upload_id, nodes=selected, total_chunks=total_chunks, chunk_size=request.chunk_size, message="ok")
    def RegisterNode(self, request, context):
        node = request.node
        self.db.register_node(node.node_id, node.ip, node.port, node.capacity_bytes)
        return pb.RegisterNodeResponse(ok=True, message="registered")
    def Login(self, request, context):
        token = str(uuid.uuid4())
        self.tokens[token] = {"user": request.username, "created": time.time()}
        return pb.LoginResponse(next_action="TOKEN", message=token)

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
