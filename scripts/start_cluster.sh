#!/bin/bash
# start gateway and one node in background (for demo)
python gateway/gateway.py &
python node/node_server.py --node-id nodeA --port 50061 --storage ./nodeA_storage --gateway 127.0.0.1:50051 &
echo "Started gateway and nodeA (check logs)"
