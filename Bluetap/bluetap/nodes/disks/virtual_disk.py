import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Union, BinaryIO
from enum import Enum
import hashlib

class DiskType(Enum):
    HDD = "HDD"
    SSD = "SSD"
    USB = "USB"

@dataclass
class VirtualDisk:
    """
    Represents a virtual disk with configurable storage capacity and type.
    """
    disk_id: str
    capacity: int  # in bytes
    disk_type: DiskType = DiskType.HDD
    
    def __post_init__(self):
        self.used_space = 0
        self.files: Dict[str, dict] = {}  # filename -> {size, path, checksum}
        self.base_path = os.path.join("disks", self.disk_id)
        os.makedirs(self.base_path, exist_ok=True)
    
    def write_file(self, filename: str, data: bytes) -> bool:
        """
        Write data to a file on the virtual disk.
        Returns True if successful, False if not enough space.
        """
        file_size = len(data)
        if self.used_space + file_size > self.capacity:
            return False
        
        file_path = os.path.join(self.base_path, filename)
        
        try:
            with open(file_path, 'wb') as f:
                f.write(data)
            
            # Update metadata
            checksum = hashlib.md5(data).hexdigest()
            self.files[filename] = {
                'size': file_size,
                'path': file_path,
                'checksum': checksum
            }
            self.used_space += file_size
            return True
        except Exception as e:
            print(f"Error writing file {filename}: {e}")
            return False
    
    def read_file(self, filename: str) -> Optional[bytes]:
        """Read a file from the virtual disk."""
        if filename not in self.files:
            return None
            
        try:
            with open(self.files[filename]['path'], 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return None
    
    def delete_file(self, filename: str) -> bool:
        """Delete a file from the virtual disk."""
        if filename not in self.files:
            return False
            
        try:
            file_info = self.files[filename]
            os.remove(file_info['path'])
            self.used_space -= file_info['size']
            del self.files[filename]
            return True
        except Exception as e:
            print(f"Error deleting file {filename}: {e}")
            return False
    
    def list_files(self) -> List[dict]:
        """List all files on the virtual disk with their metadata."""
        return [
            {
                'name': name,
                'size': info['size'],
                'checksum': info['checksum']
            }
            for name, info in self.files.items()
        ]
    
    def get_usage(self) -> dict:
        """Get disk usage statistics."""
        return {
            'total': self.capacity,
            'used': self.used_space,
            'free': self.capacity - self.used_space,
            'utilization': (self.used_space / self.capacity) * 100 if self.capacity > 0 else 0
        }
    
    def format(self) -> bool:
        """Format the virtual disk, removing all files."""
        try:
            shutil.rmtree(self.base_path)
            os.makedirs(self.base_path, exist_ok=True)
            self.files = {}
            self.used_space = 0
            return True
        except Exception as e:
            print(f"Error formatting disk: {e}")
            return False
    
    def __str__(self) -> str:
        usage = self.get_usage()
        return (
            f"VirtualDisk(id={self.disk_id}, type={self.disk_type.value}, "
            f"capacity={self.capacity}, used={usage['used']}, "
            f"free={usage['free']}, utilization={usage['utilization']:.2f}%)"
        )
