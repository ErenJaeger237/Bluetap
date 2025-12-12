# Bluetap Distributed Cloud Storage System

Bluetap is a scalable, fault-tolerant distributed object storage system designed for community infrastructure management. It implements a Master-Worker architecture similar to Google File System (GFS) or HDFS, featuring secure authentication, data replication, and liveness detection.

## Key Features

- **Distributed Architecture**: Separates metadata (Gateway) from physical storage (Nodes) for high scalability.
- **Fault Tolerance**: Implements RAID-1 style replication. Files are automatically mirrored across multiple active storage nodes.
- **Liveness Detection**: The Gateway monitors nodes via Heartbeats. If a node fails, traffic is automatically rerouted to healthy replicas.
- **Security**:
  - 2FA/OTP Authentication: Secure login via email-based One-Time Passwords.
  - Persistent Sessions: Token-based authentication using a local SQLite metadata store.
  - Multi-Tenancy: Complete isolation of user data.
- **High Performance**: Clients stream data directly to storage nodes via gRPC, preventing the Gateway from becoming a bottleneck.
- **Dual Interfaces**:
  - User Dashboard: A modern web interface for uploading/retrieving files.
  - Admin Control Plane: A supervisor dashboard to monitor node health and system telemetry in real-time.

## Prerequisites

Ensure you have Python 3.8+ installed.

### 1. Install Dependencies

Run the following command to install the required libraries:

```bash
pip install grpcio grpcio-tools streamlit pandas
```

### 2. Generate Protocol Buffers

Before running the system for the first time (or after changing `.proto` files), compile the gRPC definitions:

**Windows (PowerShell):**

```powershell
python -m grpc_tools.protoc -I=proto --python_out=generated --grpc_python_out=generated proto/bluetap.proto
```

**Linux/Mac:**

```bash
./generate_proto.sh
```

## How to Run the System

To see the full distributed system in action, you need to run multiple components in separate terminal windows.

### Step 1: Start the Gateway (The Metadata Server)

Open Terminal 1 and run:

```bash
python -m gateway.gateway
```

**Status**: Should print "Gateway running on [::]:50051".

### Step 2: Start Storage Nodes (The Storage Servers)

Open Terminal 2 (Node A):

```bash
python -m node.node_server --node-id nodeA --port 50061 --storage ./nodeA_storage --gateway 127.0.0.1:50051
```

Open Terminal 3 (Node B):

```bash
python -m node.node_server --node-id nodeB --port 50062 --storage ./nodeB_storage --gateway 127.0.0.1:50051
```

**Status**: Nodes should print "Register response: True" and start their Heartbeat service.

### Step 3: Launch the User Dashboard

Open Terminal 4 and run:

```bash
streamlit run dashboard.py
```

This will open the web interface in your browser (usually http://localhost:8501).

**Login/Register**: Enter any username (e.g., alice) and email. Check the Gateway terminal (Terminal 1) for the OTP Code if email is not configured.

### Step 4: Launch the Admin Control Plane (Optional)

Open Terminal 5 and run:

```bash
streamlit run admin.py
```

**Admin Credentials**:

- User: admin
- Password: admin123

Use this dashboard to monitor node health (Online/Offline status) and view system logs.

## Testing Fault Tolerance

1. Upload a file using the User Dashboard.
2. Check the Admin Dashboard to see the file recorded.
3. Kill Node A (Press Ctrl+C in Terminal 2).
4. Refresh the Admin Dashboard: Node A should turn OFFLINE.
5. Go back to the User Dashboard and click Retrieve.
6. The system will automatically failover and download the file from Node B.

## Project Structure

- `gateway/`: Contains the Metadata Server logic, Database (`db.py`), and Notification system.
- `node/`: Contains the Storage Server logic (`node_server.py`) and disk management (`virtual_disk.py`).
- `client/`: Contains the client-side library (`client_cli.py`) used by the dashboards.
- `proto/`: Protocol Buffer definitions (`bluetap.proto`).
- `generated/`: Compiled gRPC Python files.
- `dashboard.py`: Streamlit frontend for end-users.
- `admin.py`: Streamlit frontend for system administrators.