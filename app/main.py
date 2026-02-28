import os
import psutil
import platform
from flask import Flask, jsonify, request
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

# Prometheus metrics — exposes /metrics endpoint automatically
metrics = PrometheusMetrics(app)
metrics.info('app_info', 'Application info',
             version=os.getenv('APP_VERSION', 'v1'),
             environment=os.getenv('APP_ENV', 'production'))

APP_VERSION = os.getenv('APP_VERSION', 'v1')
APP_ENV     = os.getenv('APP_ENV', 'production')
APP_NAME    = os.getenv('APP_NAME', 'python-app')


# ── Routes ────────────────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({
        'app':       APP_NAME,
        'version':   APP_VERSION,
        'env':       APP_ENV,
        'message':   'Hello from Python Flask on EKS!',
        'hostname':  platform.node()
    })


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200


@app.route('/ready')
def ready():
    return jsonify({'status': 'ready'}), 200


@app.route('/info')
def info():
    return jsonify({
        'cpu_percent':    psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent':   psutil.disk_usage('/').percent,
        'python_version': platform.python_version(),
        'platform':       platform.system()
    })


@app.route('/items', methods=['GET'])
def get_items():
    items = [
        {'id': 1, 'name': 'Item One',   'price': 10.99},
        {'id': 2, 'name': 'Item Two',   'price': 20.99},
        {'id': 3, 'name': 'Item Three', 'price': 30.99},
    ]
    return jsonify({'items': items, 'count': len(items)})


@app.route('/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    if item_id < 1 or item_id > 3:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify({'id': item_id, 'name': f'Item {item_id}', 'price': item_id * 10.99})


@app.route('/echo', methods=['POST'])
def echo():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400
    return jsonify({'echo': data})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)