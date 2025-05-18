#!/bin/bash

# Check if Redis is already running
if ! pgrep -x "redis-server" > /dev/null; then
    echo "Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
    echo "Redis server started"
else
    echo "Redis server is already running"
fi 