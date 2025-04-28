import os
import redis
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from cluster_manager import ClusterManager
import hashlib
import json
import time

app = Flask(__name__)
cluster = ClusterManager('config/cluster.yaml')

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/kv/<key>', methods=['GET'])
def get_value(key):
    value = cluster.read_with_quorum(key)
    if value is None:
        return jsonify({'error': 'Key not found'}), 404
    return jsonify({'value': value})

@app.route('/api/kv/<key>', methods=['PUT'])
def set_value(key):
    value = request.json.get('value')
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    
    if cluster.write_with_quorum(key, value):
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Failed to write with quorum'}), 503

@app.route('/api/kv/<key>', methods=['DELETE'])
def delete_value(key):
    if cluster.write_with_quorum(key, None):
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Failed to delete with quorum'}), 503

@app.route('/api/cluster/status', methods=['GET'])
def get_cluster_status():
    cluster.check_node_health()
    return jsonify(cluster.get_cluster_status())

@app.route('/api/files', methods=['GET'])
def list_files():
    """List all available files in the cluster"""
    files = []
    for node_id, node_info in cluster.nodes.items():
        if node_info['status'] == 'active':
            try:
                # Get all keys that start with 'file:'
                keys = node_info['client'].keys('file:*:metadata')
                for key in keys:
                    file_id = key.split(':')[1]
                    if file_id not in files:
                        files.append(file_id)
            except redis.ConnectionError:
                continue
    return jsonify({'files': files})

@app.route('/api/files', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_id = hashlib.sha256(filename.encode()).hexdigest()
        
        # Store file metadata
        metadata = {
            'filename': filename,
            'size': 0,
            'chunks': 0,
            'upload_time': time.time()
        }
        
        if not cluster.write_with_quorum(f'file:{file_id}:metadata', json.dumps(metadata)):
            return jsonify({'error': 'Failed to store file metadata'}), 503
        
        # Process file in chunks
        chunk_size = cluster.config['settings']['chunk_size']
        chunk_index = 0
        total_size = 0
        
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            
            if not cluster.store_file_chunk(file_id, chunk_index, chunk):
                return jsonify({'error': f'Failed to store chunk {chunk_index}'}), 503
            
            chunk_index += 1
            total_size += len(chunk)
        
        # Update metadata with final size and chunk count
        metadata['size'] = total_size
        metadata['chunks'] = chunk_index
        
        if not cluster.write_with_quorum(f'file:{file_id}:metadata', json.dumps(metadata)):
            return jsonify({'error': 'Failed to update file metadata'}), 503
        
        return jsonify({
            'status': 'success',
            'file_id': file_id,
            'filename': filename,
            'size': total_size,
            'chunks': chunk_index
        })
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/files/<file_id>', methods=['GET'])
def download_file(file_id):
    # Get file metadata
    metadata_json = cluster.read_with_quorum(f'file:{file_id}:metadata')
    if not metadata_json:
        return jsonify({'error': 'File not found'}), 404
    
    metadata = json.loads(metadata_json)
    filename = metadata['filename']
    
    # Create a temporary file to store the reassembled data
    temp_path = os.path.join(UPLOAD_FOLDER, f'temp_{file_id}')
    
    try:
        with open(temp_path, 'wb') as f:
            for chunk_index in range(metadata['chunks']):
                chunk_data = cluster.get_file_chunk(file_id, chunk_index)
                if chunk_data is None:
                    return jsonify({'error': f'Failed to retrieve chunk {chunk_index}'}), 503
                f.write(chunk_data)
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=filename
        )
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/api/files/<file_id>/metadata', methods=['GET'])
def get_file_metadata(file_id):
    """Get detailed metadata for a specific file"""
    metadata_json = cluster.read_with_quorum(f'file:{file_id}:metadata')
    if not metadata_json:
        return jsonify({'error': 'File not found'}), 404
    
    metadata = json.loads(metadata_json)
    
    # Get nodes that have chunks for this file
    nodes_with_chunks = set()
    for node_id, node_info in cluster.nodes.items():
        if node_info['status'] == 'active':
            try:
                # Check if any chunk exists for this file
                keys = node_info['client'].keys(f'file:{file_id}:chunk:*')
                if keys:
                    nodes_with_chunks.add(node_id)
            except redis.ConnectionError:
                continue
    
    metadata['nodes'] = list(nodes_with_chunks)
    return jsonify(metadata)

@app.route('/api/files/<file_id>/chunks', methods=['GET'])
def get_file_chunks(file_id):
    """Get detailed information about file chunks"""
    metadata_json = cluster.read_with_quorum(f'file:{file_id}:metadata')
    if not metadata_json:
        return jsonify({'error': 'File not found'}), 404
    
    metadata = json.loads(metadata_json)
    chunks_info = []
    
    for chunk_index in range(metadata['chunks']):
        chunk_key = f'file:{file_id}:chunk:{chunk_index}'
        chunk_metadata_json = cluster.read_with_quorum(chunk_key)
        
        if chunk_metadata_json:
            chunk_metadata = json.loads(chunk_metadata_json)
            chunks_info.append({
                'chunk_index': chunk_index,
                'size': len(bytes.fromhex(chunk_metadata['data'])),
                'hash': chunk_metadata['hash'],
                'timestamp': chunk_metadata['timestamp'],
                'nodes': [node_id for node_id, node_info in cluster.nodes.items() 
                         if node_info['status'] == 'active' and 
                         node_info['client'].exists(chunk_key)]
            })
    
    return jsonify({
        'file_id': file_id,
        'total_chunks': metadata['chunks'],
        'chunks': chunks_info
    })

@app.route('/api/nodes/<node_id>/kill', methods=['POST'])
def kill_node(node_id):
    """Simulate killing a node by disconnecting it"""
    if node_id not in cluster.nodes:
        return jsonify({'error': 'Node not found'}), 404
    
    try:
        # Disconnect the node
        if cluster.nodes[node_id]['client']:
            cluster.nodes[node_id]['client'].close()
        cluster.nodes[node_id]['client'] = None
        cluster.nodes[node_id]['pubsub'] = None
        cluster.nodes[node_id]['status'] = 'inactive'
        return jsonify({'status': 'success', 'message': f'Node {node_id} killed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/nodes/<node_id>/start', methods=['POST'])
def start_node(node_id):
    """Start a node by reconnecting to it"""
    if node_id not in cluster.nodes:
        return jsonify({'error': 'Node not found'}), 404
    
    try:
        if cluster.reconnect_node(node_id):
            return jsonify({'status': 'success', 'message': f'Node {node_id} started'})
        return jsonify({'error': f'Failed to start node {node_id}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/nodes', methods=['POST'])
def add_node():
    """Add a new node to the cluster"""
    data = request.json
    if not data or 'id' not in data or 'host' not in data or 'port' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    node_id = data['id']
    if node_id in cluster.nodes:
        return jsonify({'error': 'Node already exists'}), 400
    
    try:
        # Add node to config
        cluster.config['nodes'].append({
            'id': node_id,
            'host': data['host'],
            'port': data['port'],
            'role': data.get('role', 'replica')
        })
        
        # Initialize the new node
        client = redis.Redis(
            host=data['host'],
            port=data['port'],
            decode_responses=True,
            socket_timeout=1,
            retry_on_timeout=True
        )
        
        # Test connection
        client.ping()
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe('heartbeat')
        
        cluster.nodes[node_id] = {
            'client': client,
            'role': data.get('role', 'replica'),
            'status': 'active',
            'last_heartbeat': time.time(),
            'pubsub': pubsub
        }
        
        return jsonify({
            'status': 'success',
            'message': f'Node {node_id} added successfully',
            'node': {
                'id': node_id,
                'host': data['host'],
                'port': data['port'],
                'role': data.get('role', 'replica'),
                'status': 'active'
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 