from storage_virtual_node import StorageVirtualNode
from storage_virtual_network import StorageVirtualNetwork
import time

# Disable delays for demonstration purposes
def fast_sleep(seconds):
    pass

time.sleep = fast_sleep

def setup_network():
    """Create and connect 3 regional nodes for the Bluetap demo"""
    network = StorageVirtualNetwork()

    # Create 3 regional Bluetap nodes
    yaounde = StorageVirtualNode("yaounde", cpu_capacity=2, memory_capacity=4, storage_capacity=4, bandwidth=40)
    douala  = StorageVirtualNode("douala",  cpu_capacity=3, memory_capacity=6, storage_capacity=6, bandwidth=60)
    buea    = StorageVirtualNode("buea",    cpu_capacity=2, memory_capacity=4, storage_capacity=3, bandwidth=25)

    # Add nodes to the distributed network
    network.add_node(yaounde)
    network.add_node(douala)
    network.add_node(buea)

    # Connect nodes with simulated bandwidths (Mbps)
    network.connect_nodes("yaounde", "douala", 50)
    network.connect_nodes("douala", "buea", 20)
    network.connect_nodes("yaounde", "buea", 10)

    return network


def simple_demo():
    """Run a simple Bluetap distributed file-sync demonstration"""
    print("\n===== BLUETAP DISTRIBUTED SYSTEM DEMO =====\n")

    # Create network
    network = setup_network()

    print("Nodes in network:")
    for node_id in network.nodes:
        print(f" - {node_id}")

    print("\nNetwork successfully initialized.\n")


    # Step 1: Initiate a simple file transfer (simulating a water-point photo upload)
    print("STEP 1: User in Yaoundé uploads a water-point photo (5 MB) to Douala server...\n")

    file_name = "waterpoint_photo.jpg"
    file_size = 5 * 1024 * 1024  # 5 MB

    transfer = network.initiate_file_transfer(
        source_node_id="yaounde",
        target_node_id="douala",
        file_name=file_name,
        file_size=file_size
    )

    if not transfer:
        print("❌ Transfer could not start.")
        return
    else:
        print("✔ Transfer initiated successfully.")
        print(f"File ID: {transfer.file_id}")
        print(f"Total chunks: {len(transfer.chunks)}\n")


        # Step 2: Process transfer step-by-step
    print("STEP 2: Processing chunks...\n")
    finished = False

    while not finished:
        chunks_done, finished_flag = network.process_file_transfer(
            source_node_id="yaounde",
            target_node_id="douala",
            file_id=transfer.file_id,
            chunks_per_step=3
        )

        print(f"Transferred {chunks_done} chunks...")

        # MANUAL COMPLETION CHECK (fix)
        # When all chunks are completed, mark transfer as completed.
        if all(chunk.status.name == "COMPLETED" for chunk in transfer.chunks):
            finished = True
            print("\n✔ All chunks received. Marking transfer as COMPLETED.\n")



    # Step 3: Show final network statistics
    print("STEP 3: Final network stats:\n")
    stats = network.get_network_stats()

    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\n===== DEMO COMPLETE =====\n")


if __name__ == "__main__":
    simple_demo()
