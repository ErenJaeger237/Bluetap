import os, json, hashlib
from pathlib import Path

class VirtualDisk:
    def __init__(self, storage_root):
        self.root = Path(storage_root)
        self.root.mkdir(parents=True, exist_ok=True)
    def _manifest_path(self, upload_id):
        return self.root / f"{upload_id}.meta.json"
    def _chunks_dir(self, upload_id):
        d = self.root / f"{upload_id}.chunks"
        d.mkdir(parents=True, exist_ok=True)
        return d
    def prepare_for_file(self, upload_id, filename, total_chunks, filesize, chunk_size, uploader=""):
        manifest = { "upload_id": upload_id, "filename": filename, "filesize": filesize, "chunk_size": chunk_size, "total_chunks": total_chunks, "received":[False]*total_chunks, "checksums":[None]*total_chunks, "uploader":uploader }
        with open(self._manifest_path(upload_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
    def _load_manifest(self, upload_id):
        p = self._manifest_path(upload_id)
        if not p.exists():
            raise FileNotFoundError("manifest not found")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    def write_chunk(self, upload_id, chunk_id, data, checksum_hex):
        h = hashlib.sha256(data).hexdigest()
        if h != checksum_hex:
            return False
        dirpath = self._chunks_dir(upload_id)
        tmp = dirpath / f".{chunk_id}.tmp"
        final = dirpath / f"{chunk_id:08d}.chunk"
        with open(tmp, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, final)
        manifest = self._load_manifest(upload_id)
        manifest["received"][chunk_id] = True
        manifest["checksums"][chunk_id] = checksum_hex
        with open(self._manifest_path(upload_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        return True
    def is_complete(self, upload_id):
        m = self._load_manifest(upload_id)
        return all(bool(r) for r in m["received"])
    def get_chunk_count(self, upload_id):
        return self._load_manifest(upload_id)["total_chunks"]
    def read_chunk(self, upload_id, chunk_id):
        path = self._chunks_dir(upload_id) / f"{chunk_id:08d}.chunk"
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return f.read()
