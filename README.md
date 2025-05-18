# RedisCluster - Milestone 1

A lightweight distributed storage system demo with Redis and Flask.
## Team Members

| Name | Email | Student ID |
|------|--------|------------|
| D.T.Jayakody | it23286382@my.sliit.lk | it23286382 |
| Salah I | it23195752@my.sliit.lk | it23195752 |
| Samarajeewa B D G M M | it23279070@my.sliit.lk | it23279070 |
| Apiram R | it23444782@my.sliit.lk | it23444782 |

## Features

- Single Redis instance with memory optimization
- Basic key-value operations (GET, SET, DELETE)
- Static HTML interface for operations
- File storage with configurable chunk size (1MB chunks)
- Minimal logging

## Prerequisites

- Python 3.6+
- Redis 5.0+

## Installation

1. Clone this repository
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start Redis server with the optimized configuration:
   ```bash
   redis-server config/redis.conf
   ```

## Running the Application

1. Start the Flask application:
   ```bash
   python app.py
   ```
2. Access the web interface at `http://localhost:5000`

## API Endpoints

### Key-Value Operations

- `GET /api/kv/<key>` - Get value for a key
- `PUT /api/kv/<key>` - Set value for a key
- `DELETE /api/kv/<key>` - Delete a key-value pair

### File Operations

- `POST /api/files` - Upload a file
- `GET /api/files/<filename>` - Download a file

## File Storage

- Files are stored in the `uploads` directory
- Each file is split into 1MB chunks
- File metadata is stored in Redis
- Supported file types: txt, pdf, png, jpg, jpeg, gif

## Memory Optimization

- Redis is configured with a 256MB memory limit
- Uses LRU (Least Recently Used) eviction policy
- Compressed RDB persistence
- Minimal logging configuration 