import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

class VirtualDisk:
    """
    Safe, atomic chunk-based virtual disk.
    Storage layout:
      /storage_root/
        <upload_id>.meta.json
        <upload_id>.chunks/
           00000000.chunk
           00000001.chunk
    """

    def __init__(self, storage_root: str):
        self.root = Path(storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, upload_id: str) -> Path:
        return self.root / f"{upload_id}.meta.json"

    def _chunks_dir(self, upload_id: str) -> Path:
        d = self.root / f"{upload_id}.chunks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def prepare_for_file(self, upload_id: str, filename: str, total_chunks: int, filesize: int, chunk_size: int, uploader: str = ""):
        manifest = {
            "upload_id": upload_id,
            "filename": filename,
            "filesize": filesize,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "received": [False] * total_chunks,
            "checksums": [None] * total_chunks,
            "uploader": uploader
        }
        with open(self._manifest_path(upload_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    def _load_manifest(self, upload_id: str) -> Dict:
        p = self._manifest_path(upload_id)
        if not p.exists():
            raise FileNotFoundError("manifest not found")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_chunk(self, upload_id: str, chunk_id: int, data: bytes, checksum_hex: str) -> bool:
        # verify checksum
        h = hashlib.sha256(data).hexdigest()
        if h != checksum_hex:
            return False

        dirpath = self._chunks_dir(upload_id)
        tmp = dirpath / f".{chunk_id}.tmp"
        final = dirpath / f"{chunk_id:08d}.chunk"

        # write atomic: write tmp -> fsync -> rename
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, final)

        # update manifest (mark received)
        manifest = self._load_manifest(upload_id)
        if chunk_id >= manifest["total_chunks"]:
            raise IndexError("chunk_id out of range")
        manifest["received"][chunk_id] = True
        manifest["checksums"][chunk_id] = checksum_hex
        with open(self._manifest_path(upload_id), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        return True

    def get_chunk_count(self, upload_id: str) -> int:
        m = self._load_manifest(upload_id)
        return m["total_chunks"]

    def read_chunk(self, upload_id: str, chunk_id: int) -> Optional[bytes]:
        path = self._chunks_dir(upload_id) / f"{chunk_id:08d}.chunk"
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return f.read()

    def is_complete(self, upload_id: str) -> bool:
        m = self._load_manifest(upload_id)
        return all(bool(r) for r in m["received"])

    def assemble_file(self, upload_id: str, out_path: str) -> str:
        manifest = self._load_manifest(upload_id)
        chunks_dir = self._chunks_dir(upload_id)
        out = Path(out_path)
        with open(out, "wb") as f_out:
            for i in range(manifest["total_chunks"]):
                chunk_file = chunks_dir / f"{i:08d}.chunk"
                if not chunk_file.exists():
                    raise FileNotFoundError(f"missing chunk {i}")
                with open(chunk_file, "rb") as cf:
                    f_out.write(cf.read())
        return str(out)
