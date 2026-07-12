from flask import Flask, request, jsonify
import json
import os
from datetime import datetime, timedelta, UTC
from jose import JWTError, jwt
from functools import wraps

# Constants
CONFIG_FILE = 'config.json'
LOG_FILE = 'cronjob_log.log'
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

app = Flask(__name__)

# Helper Functions
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

SECRET_KEY = load_config()["SECRET_KEY"]
API_USERNAME = load_config()["API_USERNAME"]
API_PASSWORD = load_config()["API_PASSWORD"]

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def log(message):
    with open(LOG_FILE, 'a') as f:
        f.write(f"{message}\n")

# JWT Functions
def create_access_token(username):
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token is missing"}), 401
        token = token.split(" ")[1]  # Bearer token
        username = verify_token(token)
        if not username:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(username, *args, **kwargs)
    return decorated

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # Replace with actual authentication logic
    if username == API_USERNAME and password == API_PASSWORD:
        token = create_access_token(username)
        return jsonify({"access_token": token, "token_type": "bearer"})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/update_special_limit', methods=['POST'])
@token_required
def update_special_limit(username):
    if username != API_USERNAME:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    user = data.get('user')
    limit = data.get('limit')

    if not user or not isinstance(limit, int):
        return jsonify({'error': 'Invalid input'}), 400

    config = load_config()

    # Check if the user exists in SPECIAL_LIMIT
    special_limit = config.get('SPECIAL_LIMIT', [])
    for i, (existing_user, existing_limit) in enumerate(special_limit):
        if existing_user == user:
            special_limit[i] = [user, limit]
            config['SPECIAL_LIMIT'] = special_limit
            save_config(config)
            return jsonify({'status': 'updated'}), 200

    # If user does not exist, add to SPECIAL_LIMIT
    special_limit.append([user, limit])
    config['SPECIAL_LIMIT'] = special_limit
    save_config(config)
    return jsonify({'status': 'added'}), 201

if __name__ == '__main__':
    app.run(host="0.0.0.0" ,port=int(os.environ.get('PORT', 6284)))
