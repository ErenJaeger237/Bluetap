import os
import time
import hashlib
import sys
from pathlib import Path

# Add the project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Use relative imports since we're in the same package
from ..network.virtual_network import VirtualNetwork
from .virtual_node import VirtualNode

def create_test_file(filename, size_mb=1):
    """Create a test file with random content."""
    chunk = os.urandom(1024)  # 1KB chunks
    with open(filename, 'wb') as f:
        for _ in range(size_mb * 1024):  # size_mb MB file
            f.write(chunk)
    print(f"Created test file: {filename} ({size_mb}MB)")

def verify_file_integrity(original, received):
    """Verify if two files are identical using MD5 hash."""
    def hash_file(filename):
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    return hash_file(original) == hash_file(received)

def main():
    # Create test file
    test_file = "test_data.bin"
    create_test_file(test_file, size_mb=5)  # 5MB test file
    
    # Create network and nodes
    network = VirtualNetwork()
    
    # Node 1 (sender)
    node1 = VirtualNode("node1")
    node1.network = network
    node1.start()
    
    # Node 2 (receiver)
    node2 = VirtualNode("node2")
    node2.network = network
    node2.start()
    
    try:
        print(f"Node1 IP: {node1.network_card.ip_address}")
        print(f"Node2 IP: {node2.network_card.ip_address}")
        
        # Wait for nodes to initialize
        time.sleep(1)
        
        # List files on both nodes (should be empty)
        print("\n=== Initial Node Status ===")
        print("Node1 files:", node1.execute_command("ls"))
        print("Node2 files:", node2.execute_command("ls"))
        
        # Start file transfer
        print(f"\n=== Starting file transfer ===")
        print(f"Transferring {test_file} from Node1 to Node2...")
        
        # Start the transfer (async)
        node1.execute_command(f"put {test_file} received_file.bin {node2.network_card.ip_address}")
        
        # Monitor transfer progress
        print("\nTransfer in progress... (Press Ctrl+C to stop)")
        start_time = time.time()
        last_status = time.time()
        
        while True:
            time.sleep(1)
            
            # Show progress every 2 seconds
            if time.time() - last_status > 2:
                # Get transfer status from both nodes
                node1_status = node1.execute_command("info")
                node2_status = node2.execute_command("info")
                
                print("\n=== Transfer Status ===")
                print(f"Elapsed: {time.time() - start_time:.1f}s")
                print(f"Node1 status: {node1_status}")
                print(f"Node2 status: {node2_status}")
                
                # Check if file exists on Node2
                files = node2.execute_command("ls")
                if files is None:
                    files = ""
                if "received_file.bin" in str(files):
                    print("\n=== Transfer Complete ===")
                    print("File received on Node2!")
                    
                    # Verify file integrity
                    print("\nVerifying file integrity...")
                    if verify_file_integrity(test_file, "node2_disk/received_file.bin"):
                        print(" File integrity verified - transfer successful!")
                    else:
                        print(" File integrity check failed - transfer corrupted!")
                    
                    break
                    
                last_status = time.time()
                
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        print("\n=== Cleaning up ===")
        node1.stop()
        node2.stop()
        
        # Clean up test files
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"Removed test file: {test_file}")

if __name__ == "__main__":
    main()