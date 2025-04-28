import os
import redis
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename

app = Flask(__name__)
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Configuration
UPLOAD_FOLDER = 'uploads'
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
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
    value = redis_client.get(key)
    if value is None:
        return jsonify({'error': 'Key not found'}), 404
    return jsonify({'value': value})

@app.route('/api/kv/<key>', methods=['PUT'])
def set_value(key):
    value = request.json.get('value')
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    redis_client.set(key, value)
    return jsonify({'status': 'success'})

@app.route('/api/kv/<key>', methods=['DELETE'])
def delete_value(key):
    if not redis_client.exists(key):
        return jsonify({'error': 'Key not found'}), 404
    redis_client.delete(key)
    return jsonify({'status': 'success'})

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
                chunk = file.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
        
        # Store file metadata in Redis
        file_key = f'file:{filename}'
        redis_client.hset(file_key, mapping={
            'path': filepath,
            'size': os.path.getsize(filepath),
            'chunks': os.path.getsize(filepath) // CHUNK_SIZE + 1
        })
        
        return jsonify({'status': 'success', 'filename': filename})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/files/<filename>', methods=['GET'])
def download_file(filename):
    file_key = f'file:{filename}'
    if not redis_client.exists(file_key):
        return jsonify({'error': 'File not found'}), 404
    
    filepath = redis_client.hget(file_key, 'path')
    return send_file(filepath, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 