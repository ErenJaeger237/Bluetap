import os
import threading
import queue
import time
import random
import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Set, Tuple, Callable
from pathlib import Path

# Use relative imports
from ..network.network_card import NetworkCard, NetworkStatus
from ..network.virtual_network import VirtualNetwork
from .disks.virtual_disk import VirtualDisk, DiskType

class NodeStatus(Enum):
    BOOTING = "booting"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    OFFLINE = "offline"

class CommandType(Enum):
    LS = "ls"
    PUT = "put"
    GET = "get"
    RM = "rm"
    INFO = "info"
    HELP = "help"
    SHUTDOWN = "shutdown"

@dataclass
class FileTransfer:
    """Tracks the state of an ongoing file transfer."""
    filename: str
    total_chunks: int
    received_chunks: Set[int]
    chunks: Dict[int, bytes]
    dest_path: str
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    
    def is_complete(self) -> bool:
        return len(self.received_chunks) >= self.total_chunks
        
    def get_missing_chunks(self) -> List[int]:
        return [i for i in range(self.total_chunks) if i not in self.received_chunks]

@dataclass
class Command:
    """Represents a command to be executed by the node."""
    cmd_type: CommandType
    args: List[str] = field(default_factory=list)
    callback: Optional[Callable[[str], None]] = None
    source_ip: Optional[str] = None  # For remote commands

class VirtualNode:
    """
    Represents a virtual node in the distributed system with its own
    network interface, storage, and processing capabilities.
    """
    
    def __init__(
        self,
        node_id: str,
        cpu_cores: int = 2,
        memory_mb: int = 2048,
        disk_size_gb: int = 100,
        disk_type: DiskType = DiskType.HDD,
        network: Optional[VirtualNetwork] = None,
        network_prefix: str = "192.168.1.0/24"
    ):
        self.node_id = node_id
        self.cpu_cores = cpu_cores
        self.memory_mb = memory_mb
        self.status = NodeStatus.BOOTING
        self.network_prefix = network_prefix
        
        # Initialize network interface
        self.network_card = NetworkCard.create()
        
        # Initialize storage
        self.disk = VirtualDisk(
            disk_id=f"disk_{node_id}",
            capacity=disk_size_gb * 1024 * 1024 * 1024,  # Convert GB to bytes
            disk_type=disk_type
        )
        
        # Command processing
        self.command_queue = queue.Queue()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        # Network reference (will be set when added to a network)
        self.network = network
        
        # Node metadata
        self.start_time = time.time()
        
        # Message handling
        self.inbox = queue.Queue()  # For incoming messages
        self.os_version = "1.0.0"
        self.node_type = "generic"
        
        # File transfer state
        self.active_transfers: Dict[str, FileTransfer] = {}
        self.transfer_lock = threading.RLock()
        
        # Command handlers
        self.command_handlers = {
            CommandType.LS: self._handle_ls,
            CommandType.PUT: self._handle_put,
            CommandType.GET: self._handle_get,
            CommandType.RM: self._handle_rm,
            CommandType.INFO: self._handle_info,
            CommandType.HELP: self._handle_help,
            CommandType.SHUTDOWN: self._handle_shutdown,
        }
    
    def start(self) -> None:
        """Start the node's main processing loop in a separate thread."""
        with self.lock:
            if self.thread and self.thread.is_alive():
                print(f"Node {self.node_id} is already running")
                return
                
            # Register with network if available
            if self.network:
                try:
                    self.network.register_node(self.network_card, self.network_prefix)
                    print(f"[{self.node_id}] Network configured: {self.network_card.ip_address}")
                except Exception as e:
                    self.status = NodeStatus.ERROR
                    raise RuntimeError(f"Failed to configure network: {e}")
            
            self.running = True
            self.status = NodeStatus.RUNNING
            self.thread = threading.Thread(
                target=self._run,
                name=f"Node-{self.node_id}",
                daemon=True
            )
            self.thread.start()
            print(f"Node {self.node_id} started successfully with IP {self.network_card.ip_address}")
    
    def stop(self) -> None:
        """Gracefully shut down the node."""
        with self.lock:
            if not self.running:
                return
                
            self.status = NodeStatus.SHUTTING_DOWN
            self.command_queue.put(Command(CommandType.SHUTDOWN))
            
            # Unregister from network
            if self.network and hasattr(self.network_card, 'mac_address'):
                self.network.unregister_node(self.network_card.mac_address)
            
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5.0)
                
            self.status = NodeStatus.OFFLINE
            self.running = False
            print(f"Node {self.node_id} has been shut down")
    
    def execute_command(self, command: str, callback: Optional[Callable[[str], None]] = None) -> None:
        """Queue a command for execution by the node."""
        if not self.running:
            if callback:
                callback("Error: Node is not running")
            return
            
        parts = command.strip().split()
        if not parts:
            return
            
        cmd_str = parts[0].lower()
        args = parts[1:]
        
        try:
            cmd_type = CommandType(cmd_str)
            self.command_queue.put(Command(cmd_type, args, callback))
        except ValueError:
            if callback:
                callback(f"Error: Unknown command '{cmd_str}'. Type 'help' for available commands.")
    
    def _run(self) -> None:
        """Main processing loop for the node."""
        self.status = NodeStatus.RUNNING
        print(f"[{self.node_id}] Node started")
        
        while self.running:
            try:
                # Process incoming messages
                try:
                    message = self.inbox.get(timeout=1.0)
                    if message and 'payload' in message:
                        payload = message['payload']
                        if 'command' in payload:
                            self._handle_remote_command(payload)
                        elif payload.get('type') == 'chunk':
                            self._handle_file_chunk(payload)
                        elif payload.get('type') == 'chunk_meta':
                            self._handle_chunk_meta(payload)
                        elif payload.get('type') == 'chunk_ack':
                            self._handle_chunk_ack(payload)
                        elif payload.get('type') == 'chunk_request':
                            self._handle_chunk_request(payload)
                except queue.Empty:
                    pass
                
                # Process commands from queue
                if not self.command_queue.empty():
                    command = self.command_queue.get()
                    self._process_command(command)
                    self.command_queue.task_done()
                
                # Clean up stale transfers periodically
                if time.time() % 30 < 0.1:  # Every ~30 seconds
                    self._cleanup_stale_transfers()
                    
            except Exception as e:
                print(f"[{self.node_id}] Error in main loop: {e}")
                time.sleep(1)  # Prevent tight loop on errors
    
    def _process_command(self, command: Command) -> None:
        """Process a single command from the queue."""
        handler = self.command_handlers.get(command.cmd_type)
        if not handler:
            self._send_response(f"Error: No handler for command {command.cmd_type}", command.callback)
            return
            
        try:
            # For remote commands, include source IP
            if command.source_ip and command.cmd_type in [CommandType.PUT, CommandType.GET]:
                result = handler(command.args, command.source_ip)
            else:
                result = handler(command.args)
                
            if result is not None:
                self._send_response(result, command.callback)
        except Exception as e:
            error_msg = f"Error executing command {command.cmd_type}: {e}"
            print(f"[{self.node_id}] {error_msg}")
            self._send_response(error_msg, command.callback)
    
    def _cleanup_stale_transfers(self) -> None:
        """Clean up any transfers that have been inactive for too long."""
        if not hasattr(self, 'active_transfers'):
            return
            
        current_time = time.time()
        stale_transfers = []
        
        with self.transfer_lock:
            for transfer_id, transfer in list(self.active_transfers.items()):
                # If transfer is older than 5 minutes and no activity in 1 minute
                if (current_time - transfer.start_time > 300 or 
                    (current_time - transfer.last_activity > 60 and 
                     not transfer.is_complete())):
                    stale_transfers.append(transfer_id)
                    
            # Remove stale transfers
            for transfer_id in stale_transfers:
                del self.active_transfers[transfer_id]
                print(f"[{self.node_id}] Cleaned up stale transfer: {transfer_id}")
                
    def _send_response(self, message: str, callback: Optional[Callable[[str], None]] = None) -> None:
        """Send a response back to the command issuer."""
        if callback:
            callback(str(message))
        else:
            print(f"{self.node_id} > {message}")
    
    def send_packet(self, dest_ip: str, payload: Dict[str, Any]) -> bool:
        """Send a packet to another node through the network.
        
        Args:
            dest_ip: Destination IP address
            payload: The payload to send
            
        Returns:
            bool: True if the packet was sent successfully, False otherwise
        """
        if not self.running or not self.network or not self.network_card.ip_address:
            return False
            
        try:
            # Ensure source information is included
            packet = {
                'src_mac': self.network_card.mac_address,
                'src_ip': self.network_card.ip_address,
                'dest_ip': dest_ip,
                'payload': payload
            }
            
            # Include source info in payload for response routing
            payload['_src_ip'] = self.network_card.ip_address
            payload['_src_mac'] = self.network_card.mac_address
            
            self.network.send_packet(packet)
            return True
            
        except Exception as e:
            print(f"[{self.node_id}] Error sending packet to {dest_ip}: {e}")
            return False
    
    # Command Handlers
    def _handle_ls(self, args: List[str]) -> str:
        """List files on the node's disk."""
        files = self.disk.list_files()
        if not files:
            return "No files found."
            
        result = ["Files on disk:", "-" * 40]
        for file in files:
            size_mb = file['size'] / (1024 * 1024)
            result.append(f"{file['name']} - {size_mb:.2f} MB (checksum: {file['checksum']})")
        
        return "\n".join(result)
    
    def _handle_put(self, args: List[str], source_ip: Optional[str] = None) -> str:
        """Handle file upload request.
        
        Args:
            args: Command arguments [localfile, remotefile, dest_ip]
            source_ip: IP of the node that sent the command (if remote)
            
        Returns:
            Status message
        """
        if len(args) < 3 and not source_ip:
            return "Usage: put <localfile> <remotefile> <destination_ip>"
            
        local_file = args[0]
        remote_file = args[1]
        dest_ip = source_ip or args[2]  # Use source_ip if command is from remote
        
        try:
            # Read file in chunks
            chunk_size = 1024 * 1024  # 1MB chunks
            chunks = []
            
            with open(local_file, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
            
            # Generate a unique transfer ID
            transfer_id = hashlib.md5(f"{remote_file}_{time.time()}".encode()).hexdigest()
            
            # Store transfer info
            with self.transfer_lock:
                self.active_transfers[transfer_id] = FileTransfer(
                    filename=remote_file,
                    total_chunks=len(chunks),
                    received_chunks=set(),
                    chunks={i: chunk for i, chunk in enumerate(chunks)},
                    dest_path=remote_file,
                    start_time=time.time(),
                    last_activity=time.time()
                )
            
            # Send metadata first
            self.send_packet(dest_ip, {
                'type': 'chunk_meta',
                'transfer_id': transfer_id,
                'filename': remote_file,
                'total_chunks': len(chunks),
                'file_size': os.path.getsize(local_file)
            })
            
            return f"Started transfer of '{local_file}' to {dest_ip} as '{remote_file}'"
            
        except Exception as e:
            return f"Error preparing file transfer: {e}"
    
    def _handle_get(self, args: List[str], source_ip: Optional[str] = None) -> str:
        """Handle file download request.
        
        Args:
            args: Command arguments [remotefile, localfile, source_ip]
            source_ip: IP of the node that sent the command (if remote)
            
        Returns:
            Status message
        """
        if len(args) < 3 and not source_ip:
            return "Usage: get <remotefile> <localfile> <source_ip>"
            
        remote_file = args[0]
        local_file = args[1]
        source_ip = source_ip or args[2]  # Use source_ip if command is from remote
        
        # Generate a unique transfer ID
        transfer_id = hashlib.md5(f"{remote_file}_{time.time()}".encode()).hexdigest()
        
        # Store transfer info
        with self.transfer_lock:
            self.active_transfers[transfer_id] = FileTransfer(
                filename=remote_file,
                total_chunks=0,  # Will be set when we receive metadata
                received_chunks=set(),
                chunks={},
                dest_path=local_file,
                start_time=time.time(),
                last_activity=time.time()
            )
        
        # Request file metadata
        self.send_packet(source_ip, {
            'type': 'chunk_request',
            'transfer_id': transfer_id,
            'chunk_id': -1,  # Special value for metadata request
            'filename': remote_file
        })
        
        return f"Requested file '{remote_file}' from {source_ip}"
    
    def _handle_rm(self, args: List[str]) -> str:
        """Remove a file from the node's disk."""
        if not args:
            return "Usage: rm <filename>"
            
        filename = args[0]
        if self.disk.delete_file(filename):
            return f"File '{filename}' deleted successfully"
        else:
            return f"Error: File '{filename}' not found or could not be deleted"
            
    def _handle_chunk_meta(self, payload: Dict[str, Any]) -> None:
        """Handle incoming chunk metadata."""
        transfer_id = payload.get('transfer_id')
        filename = payload.get('filename')
        total_chunks = payload.get('total_chunks')
        
        if not all([transfer_id, filename, total_chunks is not None]):
            print(f"[{self.node_id}] Invalid chunk metadata received")
            return
            
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                # New transfer
                self.active_transfers[transfer_id] = FileTransfer(
                    filename=filename,
                    total_chunks=total_chunks,
                    received_chunks=set(),
                    chunks={},
                    dest_path=filename,
                    start_time=time.time(),
                    last_activity=time.time()
                )
            else:
                # Update existing transfer
                transfer = self.active_transfers[transfer_id]
                transfer.total_chunks = total_chunks
                transfer.last_activity = time.time()
            
            # Request first chunk
            self.send_packet(payload['_src_ip'], {
                'type': 'chunk_request',
                'transfer_id': transfer_id,
                'chunk_id': 0,
                'filename': filename
            })
    
    def _handle_chunk_request(self, payload: Dict[str, Any]) -> None:
        """Handle a request for a specific chunk."""
        transfer_id = payload.get('transfer_id')
        chunk_id = payload.get('chunk_id')
        
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                print(f"[{self.node_id}] Received chunk request for unknown transfer: {transfer_id}")
                return
                
            transfer = self.active_transfers[transfer_id]
            transfer.last_activity = time.time()
            
            if chunk_id == -1:
                # Request for metadata
                self.send_packet(payload['_src_ip'], {
                    'type': 'chunk_meta',
                    'transfer_id': transfer_id,
                    'filename': transfer.filename,
                    'total_chunks': transfer.total_chunks,
                    'file_size': sum(len(chunk) for chunk in transfer.chunks.values())
                })
            elif 0 <= chunk_id < transfer.total_chunks:
                # Request for chunk data
                chunk_data = transfer.chunks.get(chunk_id)
                if chunk_data:
                    self.send_packet(payload['_src_ip'], {
                        'type': 'chunk',
                        'transfer_id': transfer_id,
                        'chunk_id': chunk_id,
                        'chunk_data': chunk_data,
                        'total_chunks': transfer.total_chunks
                    })
    
    def _handle_chunk_ack(self, payload: Dict[str, Any]) -> None:
        """Handle acknowledgment of a received chunk."""
        transfer_id = payload.get('transfer_id')
        chunk_id = payload.get('chunk_id')
        status = payload.get('status', 'received')
        
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                return
                
            transfer = self.active_transfers[transfer_id]
            transfer.last_activity = time.time()
            
            if status == 'received':
                # Mark chunk as received
                transfer.received_chunks.add(chunk_id)
                
                # If we're the sender, request next chunk
                if chunk_id + 1 < transfer.total_chunks:
                    self.send_packet(payload['_src_ip'], {
                        'type': 'chunk_request',
                        'transfer_id': transfer_id,
                        'chunk_id': chunk_id + 1,
                        'filename': transfer.filename
                    })
                elif transfer.is_complete():
                    # Transfer complete
                    print(f"[{self.node_id}] Transfer {transfer_id} completed successfully")
                    del self.active_transfers[transfer_id]
            
            elif status == 'error':
                # Handle error - could retry or abort
                print(f"[{self.node_id}] Error receiving chunk {chunk_id} for transfer {transfer_id}")
    
    def _handle_file_chunk(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming file chunk."""
        transfer_id = payload.get('transfer_id')
        chunk_id = payload.get('chunk_id')
        chunk_data = payload.get('chunk_data')
        total_chunks = payload.get('total_chunks')
        
        if not all([transfer_id, chunk_id is not None, chunk_data is not None, total_chunks is not None]):
            print(f"[{self.node_id}] Invalid file chunk received")
            return
            
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                # Initialize new transfer if we don't have this one yet
                self.active_transfers[transfer_id] = FileTransfer(
                    filename=f"received_file_{int(time.time())}",
                    total_chunks=total_chunks,
                    received_chunks=set(),
                    chunks={},
                    dest_path=f"received_file_{int(time.time())}",
                    start_time=time.time(),
                    last_activity=time.time()
                )
                
            transfer = self.active_transfers[transfer_id]
            transfer.last_activity = time.time()
            
            # Store the chunk
            transfer.chunks[chunk_id] = chunk_data
            transfer.received_chunks.add(chunk_id)
            
            # Send acknowledgment
            self.send_packet(payload['_src_ip'], {
                'type': 'chunk_ack',
                'transfer_id': transfer_id,
                'chunk_id': chunk_id,
                'status': 'received'
            })
            
            # Check if transfer is complete
            if transfer.is_complete():
                print(f"[{self.node_id}] All chunks received for transfer: {transfer_id}")
                
                # Reassemble file
                file_data = b''.join(transfer.chunks[i] for i in range(transfer.total_chunks))
                
                # Save the file
                try:
                    with open(transfer.dest_path, 'wb') as f:
                        f.write(file_data)
                    print(f"[{self.node_id}] File saved: {transfer.dest_path}")
                except Exception as e:
                    print(f"[{self.node_id}] Error saving file: {e}")
                
                # Clean up
                del self.active_transfers[transfer_id]
    
    def _handle_info(self, args: List[str]) -> str:
        """Display node information."""
        disk_usage = self.disk.get_usage()
        uptime = time.time() - self.start_time
        
        info = [
            f"Node ID: {self.node_id}",
            f"Status: {self.status.value}",
            f"OS Version: {self.os_version}",
            f"Type: {self.node_type}",
            f"Uptime: {uptime:.1f} seconds",
            "",
            "Hardware:",
            f"  CPU Cores: {self.cpu_cores}",
            f"  Memory: {self.memory_mb} MB",
            f"  Disk: {self.disk.disk_type.value} {disk_usage['total'] / (1024**3):.1f} GB",
            "",
            "Network:",
            f"  IP: {self.network_card.ip_address}",
            f"  MAC: {self.network_card.mac_address}",
            f"  Status: {'Connected' if self.network_card.is_connected else 'Disconnected'}",
            "",
            "Disk Usage:",
            f"  Used: {disk_usage['used'] / (1024**3):.2f} GB",
            f"  Free: {disk_usage['free'] / (1024**3):.2f} GB",
            f"  Utilization: {disk_usage['utilization']:.1f}%"
        ]
        
        return "\n".join(info)
    
    def _handle_help(self, args: List[str]) -> str:
        """Display help information."""
        help_text = [
            "Available commands:",
            "  ls                     - List files on the node",
            "  put <local> <remote>   - Upload a file to the node",
            "  get <remote> <local>   - Download a file from the node",
            "  rm <file>              - Delete a file from the node",
            "  info                   - Show node information",
            "  help                   - Show this help message",
            "  shutdown               - Shut down the node"
        ]
        return "\n".join(help_text)
    
    def _handle_shutdown(self, args: List[str]) -> None:
        """Shut down the node."""
        self.running = False
        self.status = NodeStatus.OFFLINE
    
    def _handle_file_chunk(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming file chunk.
        
        Args:
            payload: The packet payload containing the chunk data and metadata
        """
        transfer_id = payload.get('transfer_id')
        chunk_index = payload.get('chunk_index')
        chunk_data = payload.get('chunk_data')
        
        if not all([transfer_id, chunk_index, chunk_data]):
            print(f"[{self.node_id}] Invalid file chunk received: missing required fields")
            return
            
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                print(f"[{self.node_id}] Received chunk for unknown transfer: {transfer_id}")
                return
                
            transfer = self.active_transfers[transfer_id]
            transfer.last_activity = time.time()
            
            # Store the chunk
            transfer.chunks[chunk_index] = chunk_data
            transfer.received_chunks.add(chunk_index)
            
            # Send acknowledgment
            self.send_packet(payload['src_ip'], {
                'type': 'chunk_ack',
                'transfer_id': transfer_id,
                'chunk_index': chunk_index
            })
            
            # Check if transfer is complete
            if transfer.is_complete():
                print(f"[{self.node_id}] All chunks received for transfer: {transfer_id}")
                
                # Reassemble file
                file_data = b''.join(transfer.chunks[i] for i in range(transfer.total_chunks))
                
                # Save the file
                try:
                    with open(transfer.dest_path, 'wb') as f:
                        f.write(file_data)
                    print(f"[{self.node_id}] File saved: {transfer.dest_path}")
                except Exception as e:
                    print(f"[{self.node_id}] Error saving file: {e}")
                
                # Clean up
                del self.active_transfers[transfer_id]
                
    def _handle_remote_command(self, payload: Dict[str, Any]) -> None:
        """Handle a remote command execution request."""
        command_str = payload.get('command', '')
        if not command_str:
            return
            
        # Parse the command
        parts = command_str.strip().split()
        if not parts:
            return
            
        cmd_str = parts[0].lower()
        args = parts[1:]
        
        try:
            cmd_type = CommandType(cmd_str)
            
            # Create a command with source IP for proper routing of responses
            cmd = Command(
                cmd_type=cmd_type,
                args=args,
                source_ip=payload.get('_src_ip')
            )
            
            # Put the command in the queue for processing
            self.command_queue.put(cmd)
            
        except ValueError:
            # Unknown command
            error_msg = f"Unknown command: {cmd_str}"
            self.send_packet(payload['_src_ip'], {
                'type': 'command_response',
                'command': command_str,
                'result': error_msg,
                'error': True
            })
    
    def _handle_file_chunk(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming file chunk.
        
        Args:
            payload: The packet payload containing the chunk data and metadata
        """
        transfer_id = payload.get('transfer_id')
        chunk_id = payload.get('chunk_id')
        data = payload.get('data')
        
        if None in (transfer_id, chunk_id, data):
            print(f"[{self.node_id}] Invalid file chunk received")
            return
            
        with self.transfer_lock:
            if transfer_id not in self.active_transfers:
                print(f"[{self.node_id}] Received chunk for unknown transfer: {transfer_id}")
                return
                
            transfer = self.active_transfers[transfer_id]
            transfer.last_activity = time.time()
            
            # Store the chunk
            transfer.chunks[chunk_id] = data
            transfer.received_chunks.add(chunk_id)
            
            # Write chunk to disk
            try:
                self.disk.write_chunk(transfer.filename, chunk_id, data)
                
                # Send acknowledgment
                self.send_packet(payload['_src_ip'], {
                    'type': 'chunk_ack',
                    'transfer_id': transfer_id,
                    'chunk_id': chunk_id,
                    'status': 'received'
                })
                
                # Check if transfer is complete
                if len(transfer.received_chunks) >= transfer.total_chunks:
                    self._finalize_transfer(transfer_id)
                    
            except Exception as e:
                print(f"[{self.node_id}] Error writing chunk {chunk_id}: {e}")
                # Request retransmission
                self.send_packet(payload['_src_ip'], {
                    'type': 'chunk_ack',
                    'transfer_id': transfer_id,
                    'chunk_id': chunk_id,
                    'status': 'error',
                    'error': str(e)
                })

    def _send_next_chunk(self, transfer_id: str) -> None:
        """Send the next chunk for a transfer."""
        with self.transfer_lock:
            transfer = self.active_transfers.get(transfer_id)
            if not transfer:
                return
            
            missing_chunks = transfer.get_missing_chunks()
            if not missing_chunks:
                # Transfer is complete
                del self.active_transfers[transfer_id]
                return
            
            next_chunk_id = missing_chunks[0]
            chunk = transfer.chunks.get(next_chunk_id)
            if not chunk:
                print(f"[{self.node_id}] Error: Chunk {next_chunk_id} not found for transfer {transfer_id}")
                return
            
            # Send the chunk
            self.send_packet(transfer.dest_ip, {
                'type': 'chunk',
                'transfer_id': transfer_id,
                'chunk_id': next_chunk_id,
                'chunk': chunk
            })
    def __str__(self) -> str:
        return (
            f"Node(id={self.node_id}, status={self.status.value}, "
            f"ip={self.network_card.ip_address}, disk_usage={self.disk.get_usage()['utilization']:.1f}%)"
        )
