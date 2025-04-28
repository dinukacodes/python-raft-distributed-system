import redis
import time
import random
import json
from typing import Dict, List, Optional
from prometheus_client import Gauge

# Create Prometheus metrics at module level to avoid duplication
raft_term_metric = Gauge('raft_term', 'Current Raft term', ['node_id'])
raft_state_metric = Gauge('raft_state', 'Current Raft state (0=follower, 1=candidate, 2=leader)', ['node_id'])
raft_commit_index_metric = Gauge('raft_commit_index', 'Current commit index', ['node_id'])

class RaftManager:
    def __init__(self, node_id: str, redis_client: redis.Redis):
        self.node_id = node_id
        self.redis = redis_client
        self.current_term = 0
        self.voted_for = None
        self.state = 'follower'  # follower, candidate, leader
        self.election_timeout = random.uniform(150, 300) / 1000  # 150-300ms
        self.last_heartbeat = time.time()
        self.commit_index = 0
        self.last_applied = 0
        self.next_index = {}
        self.match_index = {}
        
        # Initialize Raft state in Redis
        self.initialize_raft_state()
        
        # Update metrics
        self.update_metrics()
    
    def initialize_raft_state(self):
        """Initialize Raft state in Redis"""
        if not self.redis.exists('raft:term'):
            self.redis.set('raft:term', 0)
        if not self.redis.exists('raft:commit_index'):
            self.redis.set('raft:commit_index', 0)
    
    def update_metrics(self):
        """Update Prometheus metrics"""
        # Map state to numeric value for the gauge
        state_value = 0
        if self.state == 'candidate':
            state_value = 1
        elif self.state == 'leader':
            state_value = 2
            
        raft_term_metric.labels(node_id=self.node_id).set(self.current_term)
        raft_state_metric.labels(node_id=self.node_id).set(state_value)
        raft_commit_index_metric.labels(node_id=self.node_id).set(self.commit_index)
    
    def start_election(self):
        """Start a new election"""
        self.current_term = int(self.redis.incr('raft:term'))
        self.state = 'candidate'
        self.voted_for = self.node_id
        
        # Update metrics
        self.update_metrics()
        
        # Request votes from other nodes
        self.request_votes()
    
    def request_votes(self):
        """Request votes from other nodes"""
        # In a real implementation, this would send RPCs to other nodes
        # For this demo, we'll simulate it with Redis
        self.redis.publish('raft:election', json.dumps({
            'term': self.current_term,
            'candidate_id': self.node_id,
            'last_log_index': self.last_applied,
            'last_log_term': self.current_term
        }))
    
    def handle_vote_request(self, vote_request: Dict):
        """Handle a vote request from another node"""
        if vote_request['term'] > self.current_term:
            self.current_term = vote_request['term']
            self.state = 'follower'
            self.voted_for = None
            self.update_metrics()
        
        # Grant vote if:
        # 1. Haven't voted in this term
        # 2. Candidate's log is at least as up-to-date as ours
        if (self.voted_for is None or self.voted_for == vote_request['candidate_id']) and \
           vote_request['last_log_term'] >= self.current_term:
            self.voted_for = vote_request['candidate_id']
            return True
        return False
    
    def become_leader(self):
        """Transition to leader state"""
        self.state = 'leader'
        self.next_index = {node: self.last_applied + 1 for node in self.get_cluster_nodes()}
        self.match_index = {node: 0 for node in self.get_cluster_nodes()}
        
        # Update metrics
        self.update_metrics()
        
        # Start sending heartbeats
        self.send_heartbeat()
    
    def send_heartbeat(self):
        """Send heartbeat to all followers"""
        self.redis.publish('raft:heartbeat', json.dumps({
            'term': self.current_term,
            'leader_id': self.node_id,
            'prev_log_index': self.last_applied,
            'prev_log_term': self.current_term,
            'entries': [],  # Empty entries for heartbeat
            'leader_commit': self.commit_index
        }))
    
    def handle_heartbeat(self, heartbeat: Dict):
        """Handle heartbeat from leader"""
        if heartbeat['term'] >= self.current_term:
            self.current_term = heartbeat['term']
            self.state = 'follower'
            self.voted_for = None
            self.last_heartbeat = time.time()
            
            # Update commit index
            if heartbeat['leader_commit'] > self.commit_index:
                self.commit_index = min(heartbeat['leader_commit'], self.last_applied)
            
            # Update metrics
            self.update_metrics()
    
    def get_cluster_nodes(self) -> List[str]:
        """Get list of all nodes in the cluster"""
        return [node.decode() for node in self.redis.smembers('cluster:nodes')]
    
    def run(self):
        """Main Raft loop"""
        while True:
            if self.state == 'follower':
                # Check if election timeout has passed
                if time.time() - self.last_heartbeat > self.election_timeout:
                    self.start_election()
            
            elif self.state == 'candidate':
                # Check if we've received enough votes
                votes = self.redis.scard(f'raft:votes:{self.current_term}')
                if votes > len(self.get_cluster_nodes()) / 2:
                    self.become_leader()
            
            elif self.state == 'leader':
                # Send periodic heartbeats
                if time.time() - self.last_heartbeat > 0.1:  # 100ms heartbeat interval
                    self.send_heartbeat()
                    self.last_heartbeat = time.time()
            
            time.sleep(0.01)  # 10ms sleep to prevent CPU hogging 