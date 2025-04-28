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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 