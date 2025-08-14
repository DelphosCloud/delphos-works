from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/generate', methods=['POST'])
def generate_document():
    return jsonify({"message": "Document generation endpoint ready"})

@app.route('/api/download', methods=['GET'])
def download_file():
    return jsonify({"message": "Download endpoint ready"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)