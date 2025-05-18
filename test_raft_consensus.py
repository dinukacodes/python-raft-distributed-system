import redis
import time
import json
import threading
from raft_consensus import RaftConsensus

def create_test_config(num_nodes=3):
    """Create a test configuration for Raft nodes"""
    config = {
        'nodes': [
            {'id': f'node{i}', 'host': 'localhost', 'port': 5000 + i}
            for i in range(num_nodes)
        ],
        'settings': {
            'stability': {
                'min_election_interval': 1.0,  # 1 second for testing
                'heartbeat_interval': 0.1
            }
        }
    }
    return config

def run_node(node_id, config):
    """Run a single Raft node"""
    # Create Redis client for this node with retry
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            redis_client = redis.Redis(host='localhost', port=6379, db=0)
            redis_client.ping()  # Test connection
            print(f"Successfully connected to Redis for node {node_id}")
            break
        except redis.ConnectionError as e:
            if attempt == max_retries - 1:
                raise Exception(f"Failed to connect to Redis after {max_retries} attempts: {str(e)}")
            print(f"Redis connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    # Create and start Raft node
    node = RaftConsensus(node_id, redis_client, config)
    return node

def test_raft_consensus():
    """Test the Raft consensus implementation"""
    print("\n=== Starting Raft Consensus Test ===\n")
    
    try:
        # Create test configuration
        config = create_test_config(num_nodes=3)
        
        # Start nodes
        nodes = {}
        for node_config in config['nodes']:
            node_id = node_config['id']
            print(f"Starting node {node_id}...")
            nodes[node_id] = run_node(node_id, config)
        
        # Wait for initial election
        print("\nWaiting for initial election...")
        time.sleep(5)
        
        # Check cluster state
        print("\nChecking cluster state...")
        for node_id, node in nodes.items():
            state = node.get_cluster_state()
            print(f"\nNode {node_id} state:")
            print(f"  Term: {state['term']}")
            print(f"  State: {state['state']}")
            print(f"  Commit Index: {state['commit_index']}")
            print(f"  Log Size: {state['log_size']}")
        
        # Test command proposal
        print("\nTesting command proposal...")
        leader_node = None
        for node_id, node in nodes.items():
            if node.state.name == 'LEADER':
                leader_node = node
                break
        
        if leader_node:
            print(f"Found leader node: {leader_node.node_id}")
            # Propose a test command
            command = {'type': 'set', 'key': 'test_key', 'value': 'test_value'}
            success = leader_node.propose_command(command)
            print(f"Command proposal {'succeeded' if success else 'failed'}")
            
            # Wait for command to be committed
            time.sleep(2)
            
            # Verify command was replicated
            print("\nVerifying command replication...")
            for node_id, node in nodes.items():
                state = node.get_cluster_state()
                print(f"Node {node_id} commit index: {state['commit_index']}")
        else:
            print("No leader found!")
        
        # Test leader failure and re-election
        print("\nTesting leader failure and re-election...")
        if leader_node:
            # Simulate leader failure by stopping its Redis connection
            leader_node.redis.close()
            print(f"Simulated failure of leader node {leader_node.node_id}")
            
            # Wait for re-election
            time.sleep(5)
            
            # Check new leader
            new_leader = None
            for node_id, node in nodes.items():
                if node.state.name == 'LEADER':
                    new_leader = node
                    break
            
            if new_leader:
                print(f"New leader elected: {new_leader.node_id}")
            else:
                print("No new leader elected!")
        
        print("\n=== Raft Consensus Test Complete ===\n")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        raise
    finally:
        # Cleanup
        print("\nCleaning up...")
        for node in nodes.values():
            try:
                node.redis.close()
            except:
                pass

if __name__ == '__main__':
    test_raft_consensus() 