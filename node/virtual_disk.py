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

    def _load_manifest(self, upload_id):
        p = self._manifest_path(upload_id)
        if not p.exists():
            raise FileNotFoundError("manifest not found")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Handle corrupted JSON gracefully
            return {"upload_id": upload_id, "total_chunks": 0, "received": [], "checksums": []}

    def _save_manifest_safely(self, upload_id, manifest):
        """Writes JSON to a temp file first, then renames it to avoid locking errors."""
        p = self._manifest_path(upload_id)
        temp_p = p.with_suffix(".tmp")
        try:
            with open(temp_p, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            # Atomic replacement (safer on Windows)
            if os.path.exists(p): os.remove(p)
            os.rename(temp_p, p)
        except Exception as e:
            print(f"⚠️ Warning: Failed to save manifest: {e}")

    def _load_or_create_manifest(self, upload_id):
        p = self._manifest_path(upload_id)
        if not p.exists():
            manifest = {
                "upload_id": upload_id, 
                "filename": "unknown", 
                "filesize": 0, 
                "chunk_size": 0, 
                "total_chunks": 0, 
                "received": [], 
                "checksums": []
            }
            self._save_manifest_safely(upload_id, manifest)
            return manifest
        return self._load_manifest(upload_id)

    def write_chunk(self, upload_id, chunk_id, data, checksum_hex):
        # 1. Verify checksum
        h = hashlib.sha256(data).hexdigest()
        if h != checksum_hex:
            print(f"❌ Checksum mismatch! Recv: {h} vs Exp: {checksum_hex}")
            return False

        # 2. Write data to disk
        dirpath = self._chunks_dir(upload_id)
        final = dirpath / f"{chunk_id:08d}.chunk"
        with open(final, "wb") as f:
            f.write(data)

        # 3. Update Manifest safely
        m = self._load_or_create_manifest(upload_id)
        
        required_len = chunk_id + 1
        current_len = len(m["received"])
        
        if required_len > current_len:
            extension_count = required_len - current_len
            m["received"].extend([False] * extension_count)
            m["checksums"].extend([None] * extension_count)
            
            if required_len > m["total_chunks"]:
                m["total_chunks"] = required_len

        m["received"][chunk_id] = True
        m["checksums"][chunk_id] = checksum_hex
        
        self._save_manifest_safely(upload_id, m)
        return True

    def is_complete(self, upload_id):
        try:
            m = self._load_manifest(upload_id)
            if m["total_chunks"] == 0: return False
            if len(m["received"]) < m["total_chunks"]: return False
            return all(m["received"])
        except FileNotFoundError:
            return False

    def get_chunk_count(self, upload_id):
        try:
            return self._load_manifest(upload_id)["total_chunks"]
        except FileNotFoundError:
            return 0

    def read_chunk(self, upload_id, chunk_id):
        path = self._chunks_dir(upload_id) / f"{chunk_id:08d}.chunk"
        if not path.exists(): return None
        with open(path, "rb") as f: return f.read()