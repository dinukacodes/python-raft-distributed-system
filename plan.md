# RedisCluster - Lightweight Distributed Storage System Demo

A resource-efficient distributed storage system built with Redis, featuring interactive node management, file storage, and comprehensive monitoring.

## Overview

RedisCluster is an educational distributed storage system that demonstrates key concepts of distributed systems including consensus, replication, fault tolerance, and time synchronization. The system provides an interactive GUI for managing nodes and files, with integration to Redis Insight for data visualization and Prometheus/Grafana for monitoring.

## Requirements

### Hardware (Minimized)
- Minimum 3 nodes (can run as containers on a single machine)
- Each node: 1 CPU core, 512MB RAM minimum
- Any network connection between nodes

### Software
- Any Linux distribution or Windows/macOS
- Python 3.6+
- Redis 5.0+ (lightweight configuration)
- Docker (recommended for easy deployment)

### Network
- Open ports for Redis (6379), API (5000), and monitoring (9090, 3000)
- Will work even with high-latency connections

## Tech Stack

### Backend
- **Redis**: Persistent storage (configurable to minimize memory usage)
- **Python**: Core system logic and API
- **Flask**: Lightweight RESTful API
- **ntplib**: Time synchronization
- **prometheus-client**: Metrics collection (configurable sampling rate)

### Frontend
- **Basic HTML/JavaScript**: Minimal admin interface
- **SVG**: Data visualization (hash ring, data placement)
- **WebSockets**: Efficient real-time updates

### Monitoring
- **Prometheus**: Metrics collection with reduced cardinality
- **Grafana**: Lightweight dashboards
- **Redis Insight**: Data structure visualization

## Milestones

### Milestone 1: Minimal Viable Cluster
- Single Redis instance with memory optimization
- Basic key-value operations (GET, SET, DELETE)
- Static HTML interface for operations
- File storage with configurable chunk size
- Minimal logging (no metrics)

### Milestone 2: Low-Resource Multi-Node
- Multiple Redis instances with memory limits
- Simple hash-based distribution (no virtual nodes)
- Basic replication of critical data only
- Command-line node status monitoring
- Basic file operations

Milestone 3: Fault Detection and Basic Replication

Heartbeat System:

Socket-based heartbeat mechanism (socket library)
Redis PubSub for status broadcasts (redis.pubsub)
Configurable check intervals (10-30 seconds default)
Status tracking in Redis (HSET node:{id}:status)


Quorum Implementation:

N=3, W=2, R=2 configuration stored in Redis
Write coordination using Redis transactions (pipeline.multi())
Read verification with timestamp comparison


File Chunking:

Fixed-size chunk system (configurable 1-5MB)
Chunk metadata in Redis Hashes (HSET file:{id}:metadata)
SHA256 checksums for integrity verification (hashlib.sha256)


Redis Insight Connection:

Connection profiles for each node
Read-only credentials for demonstration
Custom key patterns for easy browsing



Milestone 4: Consensus and Time Synchronization

Simplified Raft Implementation:

Leader election with term numbers (INCR cluster:term)
Election timeout with randomization (150-300ms)
Log replication using Redis Lists (RPUSH node:{id}:log)
Commit index tracking (SET cluster:commit_index)


Time Synchronization:

NTP client integration (ntplib.NTPClient())
Logical clock fallback (Lamport clocks)
Time drift detection and compensation
Clock drift metrics (GAUGE time_drift_ms)


Metrics Collection:

Prometheus client with custom collectors
Custom metrics for operations, latency, replication lag
Tagged metrics for node identification
Flask endpoint for scraping (/metrics)


Basic Web Management:

Flask-based admin interface
WebSocket for real-time updates (flask_socketio)
SVG visualization of cluster state
Node management API endpoints



Milestone 5: Complete Interactive System

Interactive Admin UI:

Complete node management (start/stop/restart)
File upload/download with progress tracking
Data placement visualization with D3.js
Configurable consistency settings
Real-time event stream


Failure Simulation:

Controlled node failure injection
Network partition simulation
Latency injection between nodes
Recovery monitoring tools


Monitoring Dashboard:

Grafana dashboards for system metrics
Operation latency histograms
Replication lag tracking
Consistency level indicators
Resource utilization panels


Cluster Management API:

RESTful API for all operations
Authentication with API keys
Rate limiting for stability
Cluster configuration endpoints
File management endpoints
## Getting Started

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure Redis with minimal memory settings
4. Update the configuration in `config/cluster.yaml`
5. Start the system: `python main.py --config config/cluster.yaml --low-resource`
6. Access the admin interface: `http://localhost:5000`

## Resource Optimization

- **Memory Usage**: Configurable Redis settings to minimize memory footprint
- **CPU Usage**: Background tasks operate on timed intervals rather than continuously
- **Network Traffic**: Configurable heartbeat intervals and selective replication
- **Storage**: Variable chunk sizes based on available disk space
- **Container Deployment**: Docker Compose file with resource limits

## Demo Scenarios

1. **Normal Operation**: Upload and retrieve files, observe data distribution
2. **Node Failure**: Stop a node via GUI, observe automatic failover
3. **Scaling**: Add a new node, watch data redistribution
4. **Resource Monitoring**: View real-time resource utilization across nodes
5. **Performance vs. Resource Trade-offs**: Configure system for different workloads

## Architecture

The system follows a resource-efficient architecture with the following components:

- **Storage Nodes**: Lightweight Redis instances with memory limits
- **Node Service**: Python daemon with configurable resource usage
- **Cluster Coordinator**: Minimal coordination with tunable consistency
- **Admin API**: RESTful interface with basic authentication
- **Admin UI**: Lightweight web interface for essential controls
- **Monitoring**: Configurable metrics collection with adjustable granularity

## License

MIT