import redis
import time
import random
import json
import threading
import logging
from typing import Dict, List, Optional, Tuple
from prometheus_client import Counter, Gauge, Histogram
from dataclasses import dataclass
from enum import Enum
import requests
import pickle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('raft_consensus.log')
    ]
)
logger = logging.getLogger('raft_consensus')

# Add color to log levels
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors"""
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Add colored formatter to handler
for handler in logger.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'))

# Prometheus metrics
raft_term_gauge = Gauge('raft_term', 'Current Raft term', ['node_id'])
raft_state_gauge = Gauge('raft_state', 'Current Raft state (0=follower, 1=candidate, 2=leader)', ['node_id'])
raft_commit_index_gauge = Gauge('raft_commit_index', 'Current commit index', ['node_id'])
raft_log_size_gauge = Gauge('raft_log_size', 'Number of entries in log', ['node_id'])
raft_election_counter = Counter('raft_elections_total', 'Number of elections started', ['node_id'])
raft_consensus_latency = Histogram('raft_consensus_latency_seconds', 'Time taken to reach consensus')

class NodeState(Enum):
    FOLLOWER = 0
    CANDIDATE = 1
    LEADER = 2

@dataclass
class LogEntry:
    term: int
    command: str
    timestamp: float

class RaftConsensus:
    def __init__(self, node_id: str, redis_client: redis.Redis, config: Dict):
        self.node_id = node_id
        self.redis = redis_client
        self.config = config
        logger.info(f"Initializing Raft node {node_id}")
        
        # Raft state
        self.current_term = 0
        self.voted_for = None
        self.state = NodeState.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0
        self.current_leader = None
        
        # Leader state
        self.next_index = {}  # For each node, index of next log entry to send
        self.match_index = {}  # For each node, index of highest log entry known to be replicated
        
        # Election state
        self.election_timeout = self._get_election_timeout()
        self.last_heartbeat = time.time()
        self.last_election_time = 0
        
        # Log state
        self.log = []  # [(term, command), ...]
        
        # Initialize state in Redis
        self._initialize_state()
        
        # Start background threads
        self._start_background_threads()
        
        # Update metrics
        self._update_metrics()
        logger.info(f"Node {node_id} initialized as {self.state.name}")
    
    def _initialize_state(self):
        """Initialize the node's state"""
        logger.info(f"Initializing Raft node {self.node_id}")
        
        if not self.redis:
            logger.error(f"Redis client is None for node {self.node_id}")
            return
            
        try:
            logger.info(f"Initializing Redis state for node {self.node_id}")
            with self.redis.pipeline() as pipe:
                # Initialize Raft state if not exists
                if not self.redis.exists('raft:term'):
                    pipe.multi()
                    pipe.set('raft:term', 0)
                    pipe.set('raft:voted_for', '')
                    pipe.set('raft:state', NodeState.FOLLOWER.name)
                    pipe.set('raft:commit_index', 0)
                    pipe.set('raft:last_applied', 0)
                    pipe.execute()
                
                # Load state from Redis with defaults
                self.current_term = int(self.redis.get('raft:term') or 0)
                self.voted_for = self.redis.get('raft:voted_for')
                state_str = self.redis.get('raft:state')
                self.state = NodeState[state_str.decode() if state_str else NodeState.FOLLOWER.name]
                self.commit_index = int(self.redis.get('raft:commit_index') or 0)
                self.last_applied = int(self.redis.get('raft:last_applied') or 0)
                
            logger.info(f"Redis state initialized for node {self.node_id}")
            
            # Initialize as follower
            self._become_follower(self.current_term)
            logger.info(f"Node {self.node_id} initialized as {self.state.name}")
            
            # Start background threads
            self._start_background_threads()
            
        except redis.ConnectionError as e:
            logger.error(f"Redis connection error for node {self.node_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error initializing state for node {self.node_id}: {str(e)}")
            raise
    
    def _update_metrics(self):
        """Update Prometheus metrics"""
        raft_term_gauge.labels(node_id=self.node_id).set(self.current_term)
        raft_state_gauge.labels(node_id=self.node_id).set(self.state.value)
        raft_commit_index_gauge.labels(node_id=self.node_id).set(self.commit_index)
        raft_log_size_gauge.labels(node_id=self.node_id).set(len(self.log))
    
    def _start_background_threads(self):
        """Start background threads for Raft operations"""
        # Election thread
        threading.Thread(target=self._election_loop, daemon=True).start()
        
        # Log replication thread (for leader)
        threading.Thread(target=self._replication_loop, daemon=True).start()
        
        # Commit thread
        threading.Thread(target=self._commit_loop, daemon=True).start()
        
        # Subscribe to Redis channels
        threading.Thread(target=self._subscribe_to_channels, daemon=True).start()
    
    def _get_election_timeout(self):
        """Get a randomized election timeout"""
        min_timeout = self.config['settings']['stability']['min_election_interval']
        return time.time() + random.uniform(min_timeout, min_timeout * 2)
    
    def _election_loop(self):
        """Main election loop"""
        while True:
            try:
                current_time = time.time()
                
                if not self._has_quorum():
                    # Step down if we don't have quorum
                    if self.state == NodeState.LEADER:
                        self._become_follower(self.current_term)
                    time.sleep(0.1)
                    continue

                if self.state == NodeState.FOLLOWER:
                    # Check for election timeout
                    if current_time > self.election_timeout:
                        self._start_election()
                
                elif self.state == NodeState.CANDIDATE:
                    # Check if we've won the election
                    votes = int(self.redis.scard(f'raft:votes:{self.current_term}') or 0)
                    active_nodes = self._check_node_health()
                    required_votes = (len(active_nodes) // 2) + 1
                    
                    if votes >= required_votes:
                        self._become_leader()
                    # Check for election timeout
                    elif current_time > self.election_timeout:
                        self._start_election()
                
                elif self.state == NodeState.LEADER:
                    # Send heartbeats to all nodes
                    if current_time - self.last_heartbeat > 0.1:  # 100ms heartbeat interval
                        self._send_heartbeat()
                        self.last_heartbeat = current_time
                
                time.sleep(0.01)  # 10ms sleep to prevent CPU hogging
                
            except redis.ConnectionError as e:
                logger.error(f"Election loop error for {self.node_id}: {str(e)}")
                self._handle_connection_error()
                time.sleep(0.1)  # Sleep before retry
    
    def _replication_loop(self):
        """Background thread for log replication (leader only)"""
        while True:
            try:
                if self.state == NodeState.LEADER and self._has_quorum():
                    self._send_append_entries()
                time.sleep(0.1)  # 100ms interval
            except redis.ConnectionError as e:
                print(f"Replication loop error for {self.node_id}: {str(e)}")
                self._handle_connection_error()
                time.sleep(0.1)  # Sleep before retry
    
    def _commit_loop(self):
        """Background loop to apply committed entries"""
        while True:
            try:
                # Check for new commits
                while self.last_applied < self.commit_index:
                    next_index = self.last_applied + 1
                    entry = self.log[next_index]
                    
                    # Apply command atomically
                    with self.redis.pipeline() as pipe:
                        pipe.watch('raft:last_applied')
                        
                        # Execute command
                        try:
                            command = entry.command
                            if isinstance(command, dict):
                                if command['type'] == 'set':
                                    pipe.multi()
                                    pipe.set(command['key'], command['value'])
                                    pipe.set('raft:last_applied', next_index)
                                    pipe.execute()
                                elif command['type'] == 'delete':
                                    pipe.multi()
                                    pipe.delete(command['key'])
                                    pipe.set('raft:last_applied', next_index)
                                    pipe.execute()
                            
                            self.last_applied = next_index
                            logger.debug(f"Node {self.node_id} applied command at index {next_index}")
                            
                        except Exception as e:
                            logger.error(f"Failed to apply command at index {next_index}: {str(e)}")
                            continue
                
                time.sleep(0.01)  # 10ms sleep to prevent CPU hogging
                
            except redis.ConnectionError as e:
                logger.error(f"Commit loop error for {self.node_id}: {str(e)}")
                self._handle_connection_error()
                time.sleep(0.1)  # Sleep before retry
    
    def _subscribe_to_channels(self):
        """Subscribe to Redis channels for Raft communication."""
        pubsub = self.redis.pubsub()
        pubsub.subscribe('raft_channel')
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    msg_type = data.get('type')
                    
                    if msg_type == 'vote_request':
                        self._handle_vote_request(data)
                    elif msg_type == 'vote_response':
                        self._handle_vote_response(data)
                    elif msg_type == 'heartbeat':
                        self._handle_heartbeat(data)
                    elif msg_type == 'append_entries':
                        self._handle_append_entries(data)
                    
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
    
    def _start_election(self):
        """Start a new election."""
        self.current_term += 1
        self.voted_for = self.node_id
        self.state = NodeState.CANDIDATE
        self.votes_received = {self.node_id}  # Vote for self
        logger.info(f"🔄 Node {self.node_id} starting election for term {self.current_term}")
        logger.info(f"📢 Node {self.node_id} is now a candidate for term {self.current_term}")

        # Publish vote request to all nodes
        vote_request = {
            'type': 'vote_request',
            'term': self.current_term,
            'candidate_id': self.node_id,
            'last_log_index': len(self.log),
            'last_log_term': self.log[-1]['term'] if self.log else 0
        }
        self.redis.publish('raft_channel', json.dumps(vote_request))

        # Wait for votes with timeout
        start_time = time.time()
        while time.time() - start_time < self.election_timeout:
            if len(self.votes_received) > len(self._get_cluster_nodes()) / 2:
                self._become_leader()
                return
            time.sleep(0.1)
    
    def _handle_vote_request(self, message):
        """Handle vote request from a candidate."""
        term = message['term']
        candidate_id = message['candidate_id']
        last_log_index = message['last_log_index']
        last_log_term = message['last_log_term']

        # Step down if term is higher
        if term > self.current_term:
            logger.info(f"Node {self.node_id} stepping down - received higher term {term} > current term {self.current_term}")
            self._become_follower(term)

        vote_granted = False
        if (term == self.current_term and 
            (self.voted_for is None or self.voted_for == candidate_id) and
            (last_log_term > self.get_last_log_term() or 
             (last_log_term == self.get_last_log_term() and last_log_index >= len(self.log)))):
            vote_granted = True
            self.voted_for = candidate_id
            self.last_heartbeat = time.time()  # Reset election timeout

        # Send vote response
        vote_response = {
            'type': 'vote_response',
            'term': self.current_term,
            'voter_id': self.node_id,
            'vote_granted': vote_granted
        }
        self.redis.publish('raft_channel', json.dumps(vote_response))
        logger.info(f"🗳️ Node {self.node_id} {'granted' if vote_granted else 'denied'} vote to {candidate_id} for term {term}")
    
    def _handle_vote_response(self, message):
        """Handle vote response from other nodes."""
        term = message['term']
        voter_id = message['voter_id']
        vote_granted = message['vote_granted']

        if term == self.current_term and self.state == NodeState.CANDIDATE:
            if vote_granted:
                self.votes_received.add(voter_id)
                logger.info(f"✅ Received vote from {voter_id} for term {term}")
                
                # Check if we have majority
                if len(self.votes_received) > len(self._get_cluster_nodes()) / 2:
                    self._become_leader()

    def _become_leader(self):
        """Transition to leader state."""
        if self.state != NodeState.CANDIDATE:
            return

        self.state = NodeState.LEADER
        self.leader_id = self.node_id
        self.next_index = {node_id: len(self.log) + 1 for node_id in self._get_cluster_nodes()}
        self.match_index = {node_id: 0 for node_id in self._get_cluster_nodes()}
        logger.info(f"👑 Node {self.node_id} became leader for term {self.current_term}")
        
        # Start sending heartbeats immediately
        self._send_heartbeat()
        
        # Schedule regular heartbeats
        if not hasattr(self, '_heartbeat_thread'):
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
            self._heartbeat_thread.daemon = True
            self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        """Send heartbeats periodically while leader."""
        while True:
            if self.state == NodeState.LEADER:
                self._send_heartbeat()
            time.sleep(self.heartbeat_interval)

    def _send_heartbeat(self):
        """Send heartbeat to all followers."""
        if self.state != NodeState.LEADER:
            return

        heartbeat = {
            'type': 'heartbeat',
            'term': self.current_term,
            'leader_id': self.node_id,
            'commit_index': self.commit_index
        }
        self.redis.publish('raft_channel', json.dumps(heartbeat))
        logger.info(f"💓 Leader {self.node_id} sent heartbeat for term {self.current_term}")

    def _handle_heartbeat(self, message):
        """Handle heartbeat from leader."""
        term = message['term']
        leader_id = message['leader_id']
        
        if term < self.current_term:
            return
        
        if term > self.current_term:
            self._become_follower(term)
        
        self.current_term = term
        self.leader_id = leader_id
        self.last_heartbeat = time.time()
        
        if self.state != NodeState.FOLLOWER:
            self._become_follower(term)
        
        logger.info(f"💓 Received heartbeat from leader {leader_id} for term {term}")

    def _send_append_entries(self):
        """Send AppendEntries RPC to all followers"""
        if self.state != NodeState.LEADER:
            return
        
        active_nodes = self._check_node_health()
        for node_id in active_nodes:
            if node_id == self.node_id:
                continue
            
            try:
                prev_log_index = self.next_index[node_id] - 1
                prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0
                entries = self.log[self.next_index[node_id]:]
                
                with self.redis.pipeline() as pipe:
                    pipe.publish('raft:append_entries', json.dumps({
                        'term': self.current_term,
                        'leader_id': self.node_id,
                        'prev_log_index': prev_log_index,
                        'prev_log_term': prev_log_term,
                        'entries': [(e.term, e.command, e.timestamp) for e in entries],
                        'leader_commit': self.commit_index
                    }))
                    pipe.execute()
                
            except (redis.ConnectionError, IndexError) as e:
                print(f"Failed to send append entries to {node_id}: {str(e)}")
                if isinstance(e, redis.ConnectionError):
                    self._handle_connection_error()
    
    def _handle_append_entries(self, leader_id: str, term: int, prev_log_index: int,
                             prev_log_term: int, entries: List[Dict], leader_commit: int) -> bool:
        """Handle AppendEntries RPC from leader"""
        logger.debug(f"Node {self.node_id} received AppendEntries from {leader_id}")
        
        try:
            # If leader's term is outdated, reject
            if term < self.current_term:
                logger.debug(f"Node {self.node_id} rejecting AppendEntries - term {term} < current term {self.current_term}")
                return False
            
            # If we get an AppendEntries RPC from a valid leader
            if term > self.current_term or self.state != NodeState.FOLLOWER:
                self._become_follower(term)
            
            # Reset election timeout
            self.last_heartbeat = time.time()
            self.election_timeout = self._get_election_timeout()
            
            # Reply false if log doesn't contain an entry at prev_log_index with prev_log_term
            if prev_log_index >= len(self.log):
                logger.debug(f"Node {self.node_id} rejecting AppendEntries - missing entry at index {prev_log_index}")
                return False
            if prev_log_index >= 0 and self.log[prev_log_index].term != prev_log_term:
                logger.debug(f"Node {self.node_id} rejecting AppendEntries - term mismatch at index {prev_log_index}")
                return False
            
            # Process entries atomically
            with self.redis.pipeline() as pipe:
                pipe.watch('raft:log')
                
                # Find conflicting entries
                new_index = prev_log_index + 1
                for i, entry in enumerate(entries):
                    if new_index + i < len(self.log):
                        if self.log[new_index + i].term != entry['term']:
                            # Delete conflicting entries and all that follow
                            self.log = self.log[:new_index + i]
                            pipe.multi()
                            pipe.ltrim('raft:log', 0, new_index + i - 1)
                            pipe.execute()
                            break
                    else:
                        break
                
                # Append new entries
                pipe.multi()
                for entry in entries:
                    log_entry = LogEntry(term=entry['term'], command=entry['command'])
                    self.log.append(log_entry)
                    pipe.rpush('raft:log', pickle.dumps(log_entry))
                pipe.execute()
            
            # Update commit index
            if leader_commit > self.commit_index:
                with self.redis.pipeline() as pipe:
                    pipe.watch('raft:commit_index')
                    new_commit_index = min(leader_commit, len(self.log) - 1)
                    
                    pipe.multi()
                    pipe.set('raft:commit_index', new_commit_index)
                    pipe.execute()
                    
                    self.commit_index = new_commit_index
                    logger.debug(f"Node {self.node_id} updated commit index to {new_commit_index}")
            
            return True
            
        except redis.ConnectionError as e:
            logger.error(f"AppendEntries handling failed for {self.node_id}: {str(e)}")
            self._handle_connection_error()
            return False
    
    def get_cluster_state(self) -> Dict:
        """Get current state of the cluster"""
        return {
            'node_id': self.node_id,
            'term': self.current_term,
            'state': self.state.name,
            'commit_index': self.commit_index,
            'last_applied': self.last_applied,
            'log_size': len(self.log)
        }

    def _handle_connection_error(self):
        """Handle Redis connection errors"""
        logger.error(f"Connection error on node {self.node_id}")
        if self.state == NodeState.LEADER:
            # Step down as leader if we can't maintain our Redis connection
            logger.warning(f"Node {self.node_id} stepping down as leader due to connection error")
            self._become_follower(self.current_term)
        
        # Try to reconnect
        try:
            if self.redis:
                self.redis.ping()
        except redis.ConnectionError:
            logger.error(f"Failed to reconnect to Redis for node {self.node_id}")

    def _check_node_health(self) -> List[str]:
        """Check which nodes are healthy and responding"""
        active_nodes = []
        try:
            # Use Redis pub/sub to check node health
            for node in self._get_cluster_nodes():
                # Publish a ping message
                self.redis.publish(f'raft:ping:{node}', json.dumps({
                    'from': self.node_id,
                    'timestamp': time.time()
                }))
                
                # Check if node has responded recently (within last 5 seconds)
                last_seen = self.redis.get(f'raft:last_seen:{node}')
                if last_seen and time.time() - float(last_seen.decode()) < 5:
                    active_nodes.append(node)
                elif node == self.node_id and self.redis.ping():
                    active_nodes.append(node)
                
        except redis.ConnectionError:
            logger.warning(f"Redis connection error while checking node health")
            if self.node_id not in active_nodes and self.redis.ping():
                active_nodes.append(self.node_id)
            
        return active_nodes

    def _has_quorum(self) -> bool:
        """Check if we have a quorum of active nodes"""
        active_nodes = self._check_node_health()
        return len(active_nodes) > len(self._get_cluster_nodes()) // 2 

    def _become_follower(self, term):
        """
        Transition the node to follower state.
        
        Args:
            term: The current term to set
        """
        self.current_term = term
        self.state = NodeState.FOLLOWER
        self.voted_for = None
        self.votes_received = set()
        self.leader_id = None
        self._reset_election_timer()
        self.logger.info(f"Node {self.node_id} becoming follower for term {term}") 