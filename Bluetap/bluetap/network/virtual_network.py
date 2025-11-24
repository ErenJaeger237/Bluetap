import ipaddress
import threading
import time
from typing import Dict, Set, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import random
from .network_card import NetworkCard, NetworkStatus, NetworkError, IPConflictError

class NetworkEventType(Enum):
    NODE_JOINED = "node_joined"
    NODE_LEFT = "node_left"
    IP_ASSIGNED = "ip_assigned"
    NETWORK_ERROR = "network_error"

@dataclass
class NetworkEvent:
    """Represents an event in the virtual network."""
    event_type: NetworkEventType
    source_mac: str
    details: dict
    timestamp: float = field(default_factory=time.time)

class VirtualNetwork:
    """
    Manages a virtual network of nodes, handling IP assignment, routing,
    and network events in a thread-safe manner.
    """
    
    def __init__(self, name: str = "default"):
        self.name = name
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._ip_pools: Dict[str, Set[str]] = {}  # network_prefix -> set of used IPs
        self._nodes: Dict[str, NetworkCard] = {}  # mac -> NetworkCard
        self._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
        self._running = False
        self._network_thread = None
        self._event_queue = []
        self._event_cv = threading.Condition()
        self._assigned_ips: Set[str] = set()  # Track all assigned IPs across all networks
        
    def start(self) -> None:
        """Start the network service."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._network_thread = threading.Thread(
                target=self._network_loop,
                name=f"Network-{self.name}",
                daemon=True
            )
            self._network_thread.start()
            
    def stop(self) -> None:
        """Stop the network service and release all resources."""
        with self._lock:
            if not self._running:
                return
                
            self._running = False
            with self._event_cv:
                self._event_cv.notify_all()
                
            if self._network_thread and self._network_thread.is_alive():
                self._network_thread.join(timeout=5.0)
                
            # Release all IPs
            for node in list(self._nodes.values()):
                self._release_ip(node.ip_address, node.network_mask)
                self._assigned_ips.discard(node.ip_address)
                
    def register_node(self, node: NetworkCard, network_prefix: str) -> str:
        """Register a node with the network and assign it an IP address.
        
        Args:
            node: The NetworkCard to register
            network_prefix: Network prefix (e.g., '192.168.1.0/24')
            
        Returns:
            The assigned IP address
            
        Raises:
            NetworkError: If registration fails
            IPConflictError: If no IP is available
        """
        with self._lock:
            # Check if node is already registered
            if node.mac_address in self._nodes:
                raise NetworkError(f"Node {node.mac_address} is already registered")
                
            # Initialize IP pool for this network if it doesn't exist
            if network_prefix not in self._ip_pools:
                self._initialize_ip_pool(network_prefix)
                
            # Find an available IP
            ip = self._get_available_ip(network_prefix)
            if not ip:
                raise IPConflictError(f"No available IPs in network {network_prefix}")
                
            # Assign IP to node
            node.ip_address = ip
            node.network_mask = str(ipaddress.IPv4Network(network_prefix, strict=False).netmask)
            
            # Register node
            self._nodes[node.mac_address] = node
            self._assigned_ips.add(ip)
            
            # Log the registration
            self._log_event(f"Node {node.mac_address} registered with IP {ip}")
            
            # Notify event handlers
            self._notify_event_handlers({
                'type': 'node_registered',
                'mac': node.mac_address,
                'ip': ip,
                'network': network_prefix
            })
            
            return ip
            
    def unregister_node(self, mac_address: str) -> None:
        """Unregister a node and release its IP address."""
        with self._lock:
            if mac_address not in self._nodes:
                return
                
            node = self._nodes[mac_address]
            if node.ip_address:
                self._release_ip(node.ip_address, node.network_mask)
                self._assigned_ips.discard(node.ip_address)
                
            del self._nodes[mac_address]
            
            self._log_event(f"Node {mac_address} unregistered")
            self._notify_event_handlers({
                'type': 'node_unregistered',
                'mac': mac_address
            })
            
    def _initialize_ip_pool(self, network_prefix: str) -> None:
        """Initialize the IP pool for a network."""
        try:
            network = ipaddress.IPv4Network(network_prefix, strict=False)
            # Exclude network and broadcast addresses
            available_ips = {str(host) for host in network.hosts()}
            self._ip_pools[network_prefix] = available_ips - self._assigned_ips
        except ValueError as e:
            raise NetworkError(f"Invalid network prefix {network_prefix}: {e}")
            
    def _get_available_ip(self, network_prefix: str) -> Optional[str]:
        """Get an available IP from the specified network."""
        if network_prefix not in self._ip_pools or not self._ip_pools[network_prefix]:
            return None
            
        # Get and remove an IP from the available pool
        ip = self._ip_pools[network_prefix].pop()
        return ip if ip not in self._assigned_ips else self._get_available_ip(network_prefix)
        
    def _release_ip(self, ip: str, network_prefix: str) -> None:
        """Release an IP back to the available pool."""
        if network_prefix in self._ip_pools:
            self._ip_pools[network_prefix].add(ip)
            
    def _notify_event_handlers(self, event: Dict[str, Any]) -> None:
        """Notify all registered event handlers."""
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                self._log_error(f"Error in event handler: {e}")
                
    def _log_event(self, message: str) -> None:
        """Log a network event."""
        print(f"[Network {self.name}] {message}")
        
    def _log_error(self, message: str) -> None:
        """Log a network error."""
        print(f"[Network {self.name} ERROR] {message}")
        
    def _network_loop(self):
        """Main network processing loop."""
        while self._running or self._event_queue:
            with self._event_cv:
                while not self._event_queue and self._running:
                    self._event_cv.wait(0.1)
                
                if not self._event_queue:
                    continue
                    
                event = self._event_queue.pop(0)
            
            # Process the event
            try:
                self._process_event(event)
            except Exception as e:
                self._log_error(f"Error processing event {event}: {e}")
                
    def _process_event(self, event: NetworkEvent) -> None:
        """Process a network event."""
        try:
            # In a real implementation, this would handle routing, etc.
            # For now, just log the event
            print(f"[Network] {event.timestamp}: {event.event_type.value} - {event.details}")
            
        except Exception as e:
            error_event = NetworkEvent(
                NetworkEventType.NETWORK_ERROR,
                event.source_mac,
                {"error": str(e), "original_event": event.event_type.value}
            )
            print(f"[Network Error] {error_event.details}")
            
    def get_network_stats(self) -> dict:
        """Get statistics about the network."""
        with self._lock:
            return {
                "name": self.name,
                "status": "running" if self._running else "stopped",
                "nodes_connected": len(self._nodes),
                "ip_pools": {
                    prefix: {
                        "total_ips": len(list(ipaddress.ip_network(prefix).hosts())),
                        "used_ips": len(ips),
                        "available_ips": len(list(ipaddress.ip_network(prefix).hosts())) - len(ips)
                    }
                    for prefix, ips in self._ip_pools.items()
                }
            }
            
    def send_packet(self, packet: Dict[str, Any]) -> bool:
        """
        Send a packet to its destination through the network.
        
        Args:
            packet: Dictionary containing packet data with 'dest_ip' and 'payload' keys
            
        Returns:
            bool: True if the packet was sent successfully, False otherwise
        """
        if not self._running:
            return False
            
        dest_ip = packet.get('dest_ip')
        if not dest_ip:
            return False
            
        # Find the destination node by IP
        dest_node = None
        with self._lock:
            for node in self._nodes.values():
                if node.ip_address == dest_ip:
                    dest_node = node
                    break
                    
        if not dest_node or not hasattr(dest_node, 'inbox'):
            return False
            
        try:
            # Put the packet in the destination node's inbox
            dest_node.inbox.put(packet)
            return True
        except Exception as e:
            print(f"[Network {self.name}] Error sending packet to {dest_ip}: {e}")
            return False
    
    def __del__(self):
        """Clean up resources."""
        self.stop()