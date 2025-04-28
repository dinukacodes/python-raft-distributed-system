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

### Milestone 3: Efficient Fault Tolerance
- Lightweight heartbeat system (configurable intervals)
- Minimal quorum implementation (configurable)
- Selective recovery procedures
- Basic Redis Insight connectivity
- Resource usage monitoring

### Milestone 4: Resource-Aware Features
- On-demand time synchronization
- Simple conflict resolution strategies
- Lightweight consensus algorithm
- Prometheus with reduced metrics collection
- Basic web-based node management

### Milestone 5: Complete System with Efficiency
- Fully functional but lightweight admin interface
- Efficient file handling with progressive loading
- Dynamic cluster management with resource limits
- Demo scenarios with minimal resource impact
- Optimized monitoring with selective metrics
- Tunable consistency vs. performance trade-offs

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