# RedisCluster Testing Guide

This document provides a comprehensive guide for testing the functionality and fault tolerance of the RedisCluster distributed system.

## Prerequisites

1. Ensure all Redis nodes are running:
```bash
redis-server --port 6379 --daemonize yes  # Primary node
redis-server --port 6380 --daemonize yes  # Replica 1
redis-server --port 6381 --daemonize yes  # Replica 2
```

2. Start the Flask application:
```bash
python app.py
```

## Basic Functionality Testing

### 1. Key-Value Operations

#### Write Operation
```bash
curl -X PUT -H "Content-Type: application/json" -d '{"value":"test_value"}' http://localhost:5000/api/kv/test_key
```
Expected: `{"status": "success"}`

#### Read Operation
```bash
curl http://localhost:5000/api/kv/test_key
```
Expected: `{"value": "test_value"}`

#### Delete Operation
```bash
curl -X DELETE http://localhost:5000/api/kv/test_key
```
Expected: `{"status": "success"}`

### 2. File Operations

#### Upload File
```bash
echo "This is a test file" > test.txt
curl -X POST -F "file=@test.txt" http://localhost:5000/api/files
```
Expected: JSON response with file_id, filename, and size

#### List Files
```bash
curl http://localhost:5000/api/files
```
Expected: List of available files with their IDs

#### Download File
```bash
curl http://localhost:5000/api/files/{file_id} -o downloaded.txt
```
Expected: File downloaded successfully

## Fault Tolerance Testing

### 1. Node Failure Scenarios

#### Single Node Failure
1. Stop one replica node:
```bash
redis-cli -p 6381 shutdown
```

2. Verify cluster status:
```bash
curl http://localhost:5000/api/cluster/status
```
Expected: Two nodes active, one inactive, quorum status "healthy"

3. Test write operation:
```bash
curl -X PUT -H "Content-Type: application/json" -d '{"value":"fault_test"}' http://localhost:5000/api/kv/fault_key
```
Expected: Success (W=2, R=2 quorum maintained)

4. Test read operation:
```bash
curl http://localhost:5000/api/kv/fault_key
```
Expected: Value retrieved successfully

#### Multiple Node Failure
1. Stop two nodes:
```bash
redis-cli -p 6380 shutdown
redis-cli -p 6381 shutdown
```

2. Verify cluster status:
```bash
curl http://localhost:5000/api/cluster/status
```
Expected: One node active, two inactive, quorum status "degraded"

3. Test write operation:
```bash
curl -X PUT -H "Content-Type: application/json" -d '{"value":"multi_fault_test"}' http://localhost:5000/api/kv/multi_fault_key
```
Expected: Error (quorum not maintained)

### 2. Recovery Testing

#### Node Recovery
1. Restart failed nodes:
```bash
redis-server --port 6380 --daemonize yes
redis-server --port 6381 --daemonize yes
```

2. Verify cluster status:
```bash
curl http://localhost:5000/api/cluster/status
```
Expected: All nodes active, quorum status "healthy"

3. Test data consistency:
```bash
curl http://localhost:5000/api/kv/fault_key
```
Expected: Value still available and consistent

### 3. File Operations During Faults

#### Upload During Node Failure
1. Stop one node
2. Upload a file:
```bash
curl -X POST -F "file=@test.txt" http://localhost:5000/api/files
```
Expected: Success (if quorum maintained)

#### Download During Node Failure
1. Stop one node
2. Download a file:
```bash
curl http://localhost:5000/api/files/{file_id} -o recovered.txt
```
Expected: Success (if quorum maintained)

## Performance Testing

### 1. Concurrent Operations
```bash
# Test concurrent writes
for i in {1..10}; do
    curl -X PUT -H "Content-Type: application/json" -d "{\"value\":\"test_$i\"}" http://localhost:5000/api/kv/key_$i &
done

# Test concurrent reads
for i in {1..10}; do
    curl http://localhost:5000/api/kv/key_$i &
done
```

### 2. Large File Handling
```bash
# Create a large file (10MB)
dd if=/dev/zero of=large_file.txt bs=1M count=10

# Upload large file
curl -X POST -F "file=@large_file.txt" http://localhost:5000/api/files
```

## Monitoring and Verification

### 1. Cluster Health
```bash
# Check cluster status
curl http://localhost:5000/api/cluster/status

# Check node health
redis-cli -p 6379 ping
redis-cli -p 6380 ping
redis-cli -p 6381 ping
```

### 2. Data Consistency
```bash
# Verify data on all nodes
redis-cli -p 6379 get test_key
redis-cli -p 6380 get test_key
redis-cli -p 6381 get test_key
```

## Troubleshooting

1. If a node fails to start:
   - Check if port is already in use
   - Verify Redis configuration
   - Check system logs

2. If quorum is not maintained:
   - Verify minimum number of active nodes
   - Check network connectivity
   - Verify node roles

3. If data inconsistency is detected:
   - Check replication status
   - Verify quorum configuration
   - Check node health

## Notes

- Always maintain at least W nodes active for writes
- Always maintain at least R nodes active for reads
- Monitor system logs for errors and warnings
- Keep track of quorum status during operations
- Verify data consistency after recovery 