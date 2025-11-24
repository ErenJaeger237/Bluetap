#!/usr/bin/env python3
"""
Test runner for Bluetap network simulation.
Run this from the Bluetap directory.
"""
import os
import sys
from pathlib import Path

# Add the current directory to Python path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Create node2_disk directory if it doesn't exist
os.makedirs("node2_disk", exist_ok=True)

# Import the test module
try:
    from nodes.test_network import main as run_test
    print("=== Test module imported successfully ===")
except ImportError as e:
    print(f"Error importing test module: {e}")
    print("Current Python path:", sys.path)
    raise

def main():
    print("=== Starting Bluetap Network Test ===")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    
    try:
        run_test()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nError during test execution: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
