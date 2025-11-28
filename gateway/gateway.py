# gateway/gateway.py
import os, time, uuid, sqlite3
from concurrent import futures
import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

DB_PATH = os.environ.get("BLUETAP_META_DB", "gateway_meta.db")

class MetadataDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init()
    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY, ip TEXT, port INTEGER, capacity INTEGER, last_seen REAL, metadata TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS files (
            upload_id TEXT PRIMARY KEY, filename TEXT, owner TEXT, filesize INTEGER,
            chunk_size INTEGER, total_chunks INTEGER, nodes TEXT, created REAL)""")
        self.conn.commit()
    def register_node(self, node_id, ip, port, capacity, metadata=""):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO nodes(node_id,ip,port,capacity,last_seen,metadata) VALUES (?,?,?,?,?,?)",
                    (node_id, ip, port, capacity, time.time(), metadata))
        self.conn.commit()
    def list_nodes(self):
        cur = self.conn.cursor()
        cur.execute("SELECT node_id,ip,port,capacity,last_seen,metadata FROM nodes ORDER BY last_seen DESC")
        return cur.fetchall()
    def save_file_metadata(self, upload_id, filename, owner, filesize, chunk_size, total_chunks, nodes):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO files(upload_id,filename,owner,filesize,chunk_size,total_chunks,nodes,created) VALUES (?,?,?,?,?,?,?,?)",
                    (upload_id, filename, owner, filesize, chunk_size, total_chunks, ",".join(nodes), time.time()))
        self.conn.commit()
    def get_file_by_filename(self, filename):
        cur = self.conn.cursor()
        cur.execute("SELECT upload_id,filename,filesize,chunk_size,total_chunks,nodes,created FROM files WHERE filename=?", (filename,))
        return cur.fetchone()
    def list_files_for_user(self, owner, limit=50, offset=0):
        cur = self.conn.cursor()
        cur.execute("SELECT filename,upload_id,filesize,created FROM files WHERE owner=? LIMIT ? OFFSET ?", (owner, limit, offset))
        return cur.fetchall()

class GatewayServicer(rpc.GatewayServicer):
    def __init__(self, db: MetadataDB):
        self.db = db
        self.tokens = {}  # token -> {user, created}
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
        token = request.token
        if token not in self.tokens:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
        upload_id = str(uuid.uuid4())
        total_chunks = (request.filesize + request.chunk_size - 1) // request.chunk_size

        # Read nodes from DB and select top 'replication' by capacity
        nodes_rows = self.db.list_nodes()
        if not nodes_rows:
            context.abort(grpc.StatusCode.UNAVAILABLE, "no nodes available")

        # Simple selection: choose first `replication` nodes
        selected = []
        for r in nodes_rows[: max(1, request.replication)]:
            node_id, ip, port, capacity, last_seen, metadata = r
            selected.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity, metadata=metadata))

        owner = self.tokens[token]["user"]
        self.db.save_file_metadata(upload_id, request.filename, owner, request.filesize, request.chunk_size, total_chunks, [n.node_id for n in selected])

        return pb.PutMetaResponse(upload_id=upload_id, nodes=selected, total_chunks=total_chunks, chunk_size=request.chunk_size, message="ok")

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

    def ListFiles(self, request, context):
        token = request.token
        if token not in self.tokens:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid token")
        owner = self.tokens[token]["user"]
        rows = self.db.list_files_for_user(owner, limit=request.limit or 50, offset=request.offset or 0)
        summaries = []
        for filename, upload_id, filesize, created in rows:
            summaries.append(pb.FileSummary(filename=filename, upload_id=upload_id, filesize=filesize, created_at=str(created)))
        return pb.ListFilesResponse(files=summaries, total=len(summaries))

def serve(address="[::]:50052"):
    db = MetadataDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=12))
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

