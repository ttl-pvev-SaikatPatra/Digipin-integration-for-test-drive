from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

print("🚀 Starting Flask app...", flush=True)

# 🔹 Basic route to confirm deployment works
@app.route('/')
def home():
    return '🟢 Flask app is live!'

# 🔹 Health check endpoint
@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

# 🔹 Sample test route (can be replaced with your logic)
@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'Test API working fine'}), 200

# 🔹 You can add your Digipin logic here later
# @app.route('/your-endpoint', methods=['POST'])
# def your_function():
#     data = request.get_json()
#     # process data
#     return jsonify({'result': 'success'})

# 🔹 Ensure the app keeps running on Render
if __name__ == '__main__':
    print("🔌 Listening on 0.0.0.0:10000", flush=True)
    app.run(host='0.0.0.0', port=10000)

