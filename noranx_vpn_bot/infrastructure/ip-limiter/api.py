from flask import Flask, request, jsonify
import json
import os
from datetime import datetime, timedelta, UTC
from jose import JWTError, jwt
from functools import wraps

CONFIG_FILE = 'config.json'
LOG_FILE = 'cronjob_log.log'
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

app = Flask(__name__)


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
        token = token.split(" ")[1]
        username = verify_token(token)
        if not username:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(username, *args, **kwargs)
    return decorated


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if username == API_USERNAME and password == API_PASSWORD:
        token = create_access_token(username)
        return jsonify({"access_token": token, "token_type": "bearer"})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/special_limit', methods=['GET'])
@token_required
def get_special_limit(api_user):
    if api_user != API_USERNAME:
        return jsonify({"error": "Unauthorized"}), 403

    user = request.args.get('user')
    if not user:
        return jsonify({"error": "user required"}), 400

    config = load_config()
    special_limit = config.get('SPECIAL_LIMIT', [])
    for existing_user, existing_limit in special_limit:
        if existing_user == user:
            return jsonify({"user": user, "limit": int(existing_limit), "configured": True})
    return jsonify({
        "user": user,
        "limit": int(config.get("GENERAL_LIMIT", 1)),
        "configured": False,
    })


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
    special_limit = config.get('SPECIAL_LIMIT', [])
    for i, (existing_user, existing_limit) in enumerate(special_limit):
        if existing_user == user:
            special_limit[i] = [user, limit]
            config['SPECIAL_LIMIT'] = special_limit
            save_config(config)
            return jsonify({'status': 'updated'}), 200

    special_limit.append([user, limit])
    config['SPECIAL_LIMIT'] = special_limit
    save_config(config)
    return jsonify({'status': 'added'}), 201


@app.route('/remove_special_limit', methods=['POST'])
@token_required
def remove_special_limit(username):
    if username != API_USERNAME:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    user = data.get('user')
    if not user:
        return jsonify({'error': 'Invalid input'}), 400

    config = load_config()
    special_limit = config.get('SPECIAL_LIMIT', [])
    new_limits = [[u, l] for u, l in special_limit if u != user]
    if len(new_limits) == len(special_limit):
        return jsonify({'status': 'not_found'}), 404
    config['SPECIAL_LIMIT'] = new_limits
    save_config(config)
    return jsonify({'status': 'removed'}), 200


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 6284)))
