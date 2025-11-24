"""
Network module for Bluetap distributed system simulation.

This module provides network-related functionality including virtual network cards
and network management for the distributed system simulation.
"""
from .network_card import NetworkCard, NetworkStatus, NetworkError, IPConflictError
from .virtual_network import VirtualNetwork, NetworkEvent, NetworkEventType

__all__ = [
    'NetworkCard', 
    'VirtualNetwork', 
    'NetworkStatus',
    'NetworkError',
    'IPConflictError',
    'NetworkEvent',
    'NetworkEventType'
]
