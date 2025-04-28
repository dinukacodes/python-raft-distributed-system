import yaml
import redis
import hashlib
import time
import threading
import json
from typing import Dict, List, Optional
from datetime import datetime

class ClusterManager:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.nodes = {}
        self.heartbeat_thread = None
        self.quorum_config = {
            'N': 3,  # Total nodes
            'W': 2,  # Write quorum
            'R': 2   # Read quorum
        }
        self.initialize_nodes()
        self.start_heartbeat_system()
        
    def initialize_nodes(self):
        """Initialize Redis connections for all nodes"""
        for node in self.config['nodes']:
            try:
                client = redis.Redis(
                    host=node['host'],
                    port=node['port'],
                    decode_responses=True,
                    socket_timeout=1,
                    retry_on_timeout=True
                )
                # Test connection
                client.ping()
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe('heartbeat')
                
                self.nodes[node['id']] = {
                    'client': client,
                    'role': node['role'],
                    'status': 'active',
                    'last_heartbeat': time.time(),
                    'pubsub': pubsub
                }
                print(f"Successfully connected to {node['id']} at port {node['port']}")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                print(f"Warning: Could not connect to {node['id']} at port {node['port']}: {str(e)}")
                self.nodes[node['id']] = {
                    'client': None,
                    'role': node['role'],
                    'status': 'inactive',
                    'last_heartbeat': 0,
                    'pubsub': None
                }
    
    def reconnect_node(self, node_id):
        """Attempt to reconnect to a node"""
        node_config = next(n for n in self.config['nodes'] if n['id'] == node_id)
        try:
            client = redis.Redis(
                host=node_config['host'],
                port=node_config['port'],
                decode_responses=True,
                socket_timeout=1,
                retry_on_timeout=True
            )
            # Test connection
            client.ping()
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe('heartbeat')
            
            self.nodes[node_id]['client'] = client
            self.nodes[node_id]['pubsub'] = pubsub
            self.nodes[node_id]['status'] = 'active'
            self.nodes[node_id]['last_heartbeat'] = time.time()
            print(f"Successfully reconnected to {node_id}")
            return True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            print(f"Failed to reconnect to {node_id}: {str(e)}")
            return False
    
    def start_heartbeat_system(self):
        """Start the heartbeat system using Redis PubSub"""
        def heartbeat_loop():
            while True:
                current_time = time.time()
                for node_id, node_info in self.nodes.items():
                    if node_info['status'] == 'inactive':
                        if self.reconnect_node(node_id):
                            continue
                    
                    if node_info['client'] is not None:
                        try:
                            # Publish heartbeat
                            node_info['client'].publish('heartbeat', json.dumps({
                                'node_id': node_id,
                                'timestamp': current_time,
                                'status': 'alive'
                            }))
                            
                            # Process received heartbeats
                            if node_info['pubsub'] is not None:
                                message = node_info['pubsub'].get_message()
                                if message and message['type'] == 'message':
                                    data = json.loads(message['data'])
                                    if data['node_id'] != node_id:
                                        self.nodes[data['node_id']]['last_heartbeat'] = data['timestamp']
                                        self.nodes[data['node_id']]['status'] = 'active'
                        except (redis.ConnectionError, redis.TimeoutError) as e:
                            print(f"Lost connection to {node_id}: {str(e)}")
                            node_info['status'] = 'inactive'
                            node_info['client'] = None
                            node_info['pubsub'] = None
                
                time.sleep(self.config['settings']['heartbeat_interval'])
        
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
    
    def get_active_nodes(self):
        """Get list of currently active nodes"""
        return [node_id for node_id, info in self.nodes.items() if info['status'] == 'active']
    
    def get_node_for_key(self, key: str) -> str:
        """Simple hash-based distribution of keys across nodes"""
        active_nodes = self.get_active_nodes()
        if not active_nodes:
            raise redis.ConnectionError("No active nodes available")
        
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        node_index = hash_value % len(active_nodes)
        return active_nodes[node_index]
    
    def write_with_quorum(self, key: str, value: str) -> bool:
        """Write data with quorum consistency"""
        successful_writes = 0
        active_nodes = self.get_active_nodes()
        
        if len(active_nodes) < self.quorum_config['W']:
            print(f"Not enough active nodes for write quorum. Active: {len(active_nodes)}, Required: {self.quorum_config['W']}")
            return False
        
        for node_id in active_nodes:
            try:
                self.nodes[node_id]['client'].set(key, value)
                successful_writes += 1
                if successful_writes >= self.quorum_config['W']:
                    return True
            except (redis.ConnectionError, redis.TimeoutError) as e:
                print(f"Write failed for node {node_id}: {str(e)}")
                self.nodes[node_id]['status'] = 'inactive'
                continue
        
        return False
    
    def read_with_quorum(self, key: str) -> Optional[str]:
        """Read data with quorum consistency"""
        successful_reads = 0
        values = {}
        active_nodes = self.get_active_nodes()
        
        if len(active_nodes) < self.quorum_config['R']:
            print(f"Not enough active nodes for read quorum. Active: {len(active_nodes)}, Required: {self.quorum_config['R']}")
            return None
        
        for node_id in active_nodes:
            try:
                value = self.nodes[node_id]['client'].get(key)
                if value is not None:
                    values[value] = values.get(value, 0) + 1
                    successful_reads += 1
                    if successful_reads >= self.quorum_config['R']:
                        return max(values.items(), key=lambda x: x[1])[0]
            except (redis.ConnectionError, redis.TimeoutError) as e:
                print(f"Read failed for node {node_id}: {str(e)}")
                self.nodes[node_id]['status'] = 'inactive'
                continue
        
        return None
    
    def store_file_chunk(self, file_id: str, chunk_index: int, chunk_data: bytes) -> bool:
        """Store a file chunk with integrity verification"""
        chunk_key = f'file:{file_id}:chunk:{chunk_index}'
        chunk_hash = hashlib.sha256(chunk_data).hexdigest()
        
        # Store chunk with metadata
        metadata = {
            'data': chunk_data.hex(),
            'hash': chunk_hash,
            'timestamp': time.time()
        }
        
        return self.write_with_quorum(chunk_key, json.dumps(metadata))
    
    def get_file_chunk(self, file_id: str, chunk_index: int) -> Optional[bytes]:
        """Retrieve a file chunk with integrity verification"""
        chunk_key = f'file:{file_id}:chunk:{chunk_index}'
        metadata_json = self.read_with_quorum(chunk_key)
        
        if not metadata_json:
            return None
        
        metadata = json.loads(metadata_json)
        chunk_data = bytes.fromhex(metadata['data'])
        
        # Verify integrity
        if hashlib.sha256(chunk_data).hexdigest() != metadata['hash']:
            return None
        
        return chunk_data
    
    def check_node_health(self):
        """Check health of all nodes"""
        current_time = time.time()
        for node_id, node_info in self.nodes.items():
            if current_time - node_info['last_heartbeat'] > self.config['settings']['heartbeat_interval'] * 3:
                if node_info['status'] == 'active':
                    print(f"Node {node_id} is now inactive")
                node_info['status'] = 'inactive'
    
    def get_cluster_status(self) -> Dict:
        """Get current status of all nodes"""
        self.check_node_health()
        active_nodes = len(self.get_active_nodes())
        quorum_status = 'healthy' if active_nodes >= max(self.quorum_config['W'], self.quorum_config['R']) else 'degraded'
        
        return {
            node_id: {
                'role': node_info['role'],
                'status': node_info['status'],
                'last_heartbeat': node_info['last_heartbeat'],
                'quorum_status': quorum_status
            }
            for node_id, node_info in self.nodes.items()
        }
    
    def check_quorum_health(self) -> bool:
        """Check if cluster can maintain quorum"""
        active_nodes = len(self.get_active_nodes())
        return active_nodes >= max(self.quorum_config['W'], self.quorum_config['R']) 