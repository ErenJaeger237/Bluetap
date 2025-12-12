# coordinator/coordinator.py
import os, time, sqlite3
from concurrent import futures
import grpc
from generated import bluetap_pb2 as pb
from generated import bluetap_pb2_grpc as rpc

DB_PATH = os.environ.get("BLUETAP_META_DB", "gateway_meta.db")

class CoordinatorDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
    def list_nodes(self):
        cur = self.conn.cursor()
        cur.execute("SELECT node_id,ip,port,capacity,last_seen,metadata FROM nodes ORDER BY capacity DESC")
        return cur.fetchall()
    def get_file(self, filename):
        cur = self.conn.cursor()
        cur.execute("SELECT upload_id,filename,filesize,chunk_size,total_chunks,nodes,created FROM files WHERE filename=?", (filename,))
        return cur.fetchone()

class CoordinatorServicer(rpc.CoordinatorServicer):
    def __init__(self, db: CoordinatorDB):
        self.db = db

    def SelectNodes(self, request, context):
        # Choose top-N nodes by capacity
        nodes = []
        rows = self.db.list_nodes()
        # simple heuristic: choose first `replication` nodes
        for r in rows[:max(1, request.replication)]:
            node_id, ip, port, capacity, last_seen, metadata = r
            nodes.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity, metadata=metadata))
        return pb.SelectNodesResponse(nodes=nodes)

    def ScheduleRepair(self, request, context):
        # In a simple demo, we just acknowledge
        return pb.ScheduleRepairResponse(ok=True, message="scheduled (demo)")

    def LookupFile(self, request, context):
        row = self.db.get_file(request.filename)
        if not row:
            return pb.LookupFileResponse()
        upload_id, filename, filesize, chunk_size, total_chunks, nodes_csv, created = row
        nodes = []
        for nid in nodes_csv.split(","):
            for r in self.db.list_nodes():
                if r[0] == nid:
                    node_id, ip, port, capacity, last_seen, metadata = r
                    nodes.append(pb.NodeInfo(node_id=node_id, ip=ip, port=port, capacity_bytes=capacity, metadata=metadata))
                    break
        fileloc = pb.FileLocation(upload_id=upload_id, nodes=nodes, filesize=filesize, chunk_size=chunk_size, total_chunks=total_chunks, filename=filename)
        return pb.LookupFileResponse(file=fileloc)

def serve(address="[::]:50053"):
    db = CoordinatorDB()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    rpc.add_CoordinatorServicer_to_server(CoordinatorServicer(db), server)
    server.add_insecure_port(address)
    server.start()
    print("Coordinator running on", address)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
