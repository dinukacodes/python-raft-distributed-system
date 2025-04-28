import yaml
import redis
import hashlib
import time
from typing import Dict, List, Optional

class ClusterManager:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.nodes = {}
        self.initialize_nodes()
        
    def initialize_nodes(self):
        """Initialize Redis connections for all nodes"""
        for node in self.config['nodes']:
            self.nodes[node['id']] = {
                'client': redis.Redis(
                    host=node['host'],
                    port=node['port'],
                    decode_responses=True
                ),
                'role': node['role'],
                'status': 'active',
                'last_heartbeat': time.time()
            }
    
    def get_node_for_key(self, key: str) -> str:
        """Simple hash-based distribution of keys across nodes"""
        node_count = len(self.config['nodes'])
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        node_index = hash_value % node_count
        return self.config['nodes'][node_index]['id']
    
    def replicate_data(self, key: str, value: str, primary_node: str):
        """Basic replication to other nodes"""
        replication_factor = self.config['settings']['replication_factor']
        nodes_to_replicate = []
        
        # Find nodes to replicate to
        for node_id, node_info in self.nodes.items():
            if node_id != primary_node and node_info['status'] == 'active':
                nodes_to_replicate.append(node_id)
                if len(nodes_to_replicate) >= replication_factor - 1:
                    break
        
        # Perform replication
        for node_id in nodes_to_replicate:
            try:
                self.nodes[node_id]['client'].set(key, value)
            except redis.ConnectionError:
                self.nodes[node_id]['status'] = 'inactive'
    
    def check_node_health(self):
        """Basic health check for nodes"""
        for node_id, node_info in self.nodes.items():
            try:
                node_info['client'].ping()
                node_info['status'] = 'active'
                node_info['last_heartbeat'] = time.time()
            except redis.ConnectionError:
                node_info['status'] = 'inactive'
    
    def get_cluster_status(self) -> Dict:
        """Get current status of all nodes"""
        return {
            node_id: {
                'role': node_info['role'],
                'status': node_info['status'],
                'last_heartbeat': node_info['last_heartbeat']
            }
            for node_id, node_info in self.nodes.items()
        } 