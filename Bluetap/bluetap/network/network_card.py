import random
import ipaddress
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, Tuple, ClassVar
from enum import Enum, auto

class NetworkStatus(Enum):
    """Network interface status flags for better status reporting."""
    DOWN = auto()           # Interface is down
    UP = auto()             # Interface is up but not configured
    CONFIGURING = auto()    # Getting network configuration
    READY = auto()         # Configured and ready
    TRANSMITTING = auto()  # Actively sending/receiving
    ERROR = auto()         # Error state

class NetworkError(Exception):
    """Base exception for network-related errors."""
    pass

class IPConflictError(NetworkError):
    """Raised when an IP address conflict is detected."""
    pass

@dataclass
class NetworkCard:
    """
    Represents a virtual network interface card with IP and MAC addressing.
    IP address is assigned by the VirtualNetwork, not generated here.
    """
    # Instance variables with default values
    ip_address: Optional[str] = None
    mac_address: str = field(init=False)
    network_mask: str = "255.255.255.0"
    status: NetworkStatus = field(default=NetworkStatus.DOWN, init=False)
    
    def __post_init__(self):
        """Initialize the network card with a valid MAC address."""
        self.mac_address = self._generate_mac_address()
        self._status_lock = threading.Lock()
        self._ip_lock = threading.Lock()  # Add IP lock for thread safety
        self._network = None  # Will be set when connected to a network
        self._network_prefix = None  # Network prefix for IP assignment
        
    @classmethod
    def create(cls) -> 'NetworkCard':
        """Create a new network card with a random MAC address.
        
        Note: IP address will be assigned by the VirtualNetwork.
        """
        return cls()
        
    def _generate_mac_address(self) -> str:
        """Generate a locally administered, unicast MAC address."""
        # First byte: 0x02 for locally administered, unicast
        # Next 5 bytes: random
        mac = [0x02, 
              random.randint(0x00, 0x7f), 
              random.randint(0x00, 0xff),
              random.randint(0x00, 0xff),
              random.randint(0x00, 0xff),
              random.randint(0x00, 0xff)]
        return ':'.join(map(lambda x: "%02x" % x, mac))
    
    def set_network(self, network: 'VirtualNetwork') -> None:
        """Register this card with a network."""
        """Register this card with a network and request an IP address."""
        with self._status_lock:
            self._network = network
            self._network_prefix = network_prefix or "192.168.1.0/24"
            self.status = NetworkStatus.CONFIGURING
            
            try:
                # Request IP from network
                ip = self._request_ip_from_network()
                with self._ip_lock:
                    self.ip_address = ip
                self.status = NetworkStatus.READY
            except Exception as e:
                self.status = NetworkStatus.ERROR
                raise NetworkError(f"Failed to configure network: {e}") from e
    
    def _request_ip_from_network(self) -> str:
        """Request an IP address from the network."""
        if not self._network:
            raise NetworkError("Not connected to a network")
            
        # Get available IPs from network
        available_ips = self._network.get_available_ips(self._network_prefix)
        
        with NetworkCard._lock:
            # Find first available IP not in use
            for ip in available_ips:
                if ip not in NetworkCard._used_ips:
                    NetworkCard._used_ips.add(ip)
                    return ip
                    
        raise IPConflictError("No available IP addresses in the network")
    
    def release_ip(self) -> None:
        """Release the IP address back to the pool."""
        with self._ip_lock:
            if self.ip_address and self._network:
                with NetworkCard._lock:
                    NetworkCard._used_ips.discard(self.ip_address)
                    self.ip_address = None
                    self.status = NetworkStatus.DOWN
    
    def get_status(self) -> Dict[str, str]:
        """Get detailed status of the network interface."""
        return {
            "mac": self.mac_address,
            "ip": self.ip_address or "Not configured",
            "netmask": self.network_mask,
            "status": self.status.name,
            "network": self._network_prefix or "Not connected"
        }
    
    def is_connected(self) -> bool:
        """Check if the interface is connected and configured."""
        return self.status == NetworkStatus.READY and self.ip_address is not None
    
    def connect(self) -> None:
        """Mark the network card as connected."""
        with self._status_lock:
            self.status = NetworkStatus.UP
            if self._network:
                try:
                    self.ip_address = self._request_ip_from_network()
                    self.status = NetworkStatus.READY
                except Exception as e:
                    self.status = NetworkStatus.ERROR
                    raise NetworkError(f"Failed to connect: {e}") from e
    
    def disconnect(self) -> None:
        """Mark the network card as disconnected and release resources."""
        with self._status_lock:
            self.release_ip()
            self.status = NetworkStatus.DOWN
    
    def __str__(self) -> str:
        """String representation of the network card."""
        status = {
            NetworkStatus.DOWN: "disconnected",
            NetworkStatus.UP: "up",
            NetworkStatus.READY: "ready",
            NetworkStatus.TRANSMITTING: "transmitting",
            NetworkStatus.ERROR: "error",
            NetworkStatus.CONFIGURING: "configuring"
        }.get(self.status, "unknown")
        
        return (f"NetworkCard(ip={self.ip_address or 'None'}, "
                f"mac={self.mac_address}, status={status})")

    def __del__(self):
        """Clean up resources when the object is destroyed."""
        try:
            if hasattr(self, '_network') and self._network is not None:
                self.release_ip()
        except Exception as e:
            # Ignore errors during cleanup
            pass