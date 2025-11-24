"""
Bluetap - A distributed system simulation framework for educational purposes.

This package provides the core components for simulating a distributed system
with virtual nodes, networks, and storage devices.
"""

__version__ = "0.1.0"

# Import key components for easier access
from .network.virtual_network import VirtualNetwork
from .nodes.virtual_node import VirtualNode
from .nodes.disks.virtual_disk import VirtualDisk, DiskType

__all__ = ['VirtualNetwork', 'VirtualNode', 'VirtualDisk', 'DiskType']
