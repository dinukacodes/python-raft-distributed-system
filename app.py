import os
import redis
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from cluster_manager import ClusterManager

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
    node_id = cluster.get_node_for_key(key)
    try:
        value = cluster.nodes[node_id]['client'].get(key)
        if value is None:
            return jsonify({'error': 'Key not found'}), 404
        return jsonify({'value': value, 'node': node_id})
    except redis.ConnectionError:
        return jsonify({'error': f'Node {node_id} is unavailable'}), 503

@app.route('/api/kv/<key>', methods=['PUT'])
def set_value(key):
    value = request.json.get('value')
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    
    node_id = cluster.get_node_for_key(key)
    try:
        cluster.nodes[node_id]['client'].set(key, value)
        cluster.replicate_data(key, value, node_id)
        return jsonify({'status': 'success', 'node': node_id})
    except redis.ConnectionError:
        return jsonify({'error': f'Node {node_id} is unavailable'}), 503

@app.route('/api/kv/<key>', methods=['DELETE'])
def delete_value(key):
    node_id = cluster.get_node_for_key(key)
    try:
        if not cluster.nodes[node_id]['client'].exists(key):
            return jsonify({'error': 'Key not found'}), 404
        cluster.nodes[node_id]['client'].delete(key)
        cluster.replicate_data(key, None, node_id)  # Replicate deletion
        return jsonify({'status': 'success', 'node': node_id})
    except redis.ConnectionError:
        return jsonify({'error': f'Node {node_id} is unavailable'}), 503

@app.route('/api/cluster/status', methods=['GET'])
def get_cluster_status():
    cluster.check_node_health()
    return jsonify(cluster.get_cluster_status())

@app.route('/api/files', methods=['GET'])
def list_files():
    """List all available files in the cluster"""
    files = []
    for node_id, node_info in cluster.nodes.items():
        try:
            # Get all keys that start with 'file:'
            keys = node_info['client'].keys('file:*')
            for key in keys:
                filename = key.split(':', 1)[1]
                if filename not in files:
                    files.append(filename)
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
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save file in chunks
        with open(filepath, 'wb') as f:
            while True:
                chunk = file.read(cluster.config['settings']['chunk_size'])
                if not chunk:
                    break
                f.write(chunk)
        
        # Store file metadata in Redis cluster
        file_key = f'file:{filename}'
        node_id = cluster.get_node_for_key(file_key)
        try:
            cluster.nodes[node_id]['client'].hset(file_key, mapping={
                'path': filepath,
                'size': os.path.getsize(filepath),
                'chunks': os.path.getsize(filepath) // cluster.config['settings']['chunk_size'] + 1
            })
            cluster.replicate_data(file_key, str({
                'path': filepath,
                'size': os.path.getsize(filepath),
                'chunks': os.path.getsize(filepath) // cluster.config['settings']['chunk_size'] + 1
            }), node_id)
            
            return jsonify({'status': 'success', 'filename': filename, 'node': node_id})
        except redis.ConnectionError:
            return jsonify({'error': f'Node {node_id} is unavailable'}), 503
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/files/<filename>', methods=['GET'])
def download_file(filename):
    file_key = f'file:{filename}'
    node_id = cluster.get_node_for_key(file_key)
    try:
        if not cluster.nodes[node_id]['client'].exists(file_key):
            return jsonify({'error': 'File not found'}), 404
        
        filepath = cluster.nodes[node_id]['client'].hget(file_key, 'path')
        return send_file(filepath, as_attachment=True)
    except redis.ConnectionError:
        return jsonify({'error': f'Node {node_id} is unavailable'}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 