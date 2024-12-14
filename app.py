from flask import Flask, jsonify, request
from flask_httpauth import HTTPBasicAuth
import mysql.connector
import json
import jwt
from werkzeug.security import check_password_hash, generate_password_hash, check_password_hash
from functools import wraps
import datetime
import logging


app = Flask(__name__)
app.config['SECRET_KEY'] = "keinth123"

auth = HTTPBasicAuth()
USER_DATA_FILE = "users.json"

# Database Connection Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'elective'
}

def get_db_connection():
    """Create and return a database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        return None

def execute_query(query, params=None, fetch=False):
    """Execute a database query with optional parameters"""
    connection = get_db_connection()
    if not connection:
        return None

    try:
        cursor = connection.cursor(dictionary=True)
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch:
            result = cursor.fetchall()
        else:
            connection.commit()
            result = cursor.rowcount
        
        cursor.close()
        connection.close()
        return result
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        if connection:
            connection.close()
        return None
    

def load_users():
    """Load users from JSON file"""
    try:
        with open(USER_DATA_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_users(users):
    """Save users to JSON file"""
    with open(USER_DATA_FILE, "w") as file:
        json.dump(users, file)

users = load_users()


@auth.verify_password
def verify_password(username, password):
    """Verify user password"""
    if username in users and check_password_hash(users[username]['password'], password):
        return username

def token_required(f):
    """Decorator to require JWT token for route access"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")
        
        if not token:
            logging.warning("Token is missing")
            return jsonify({"error": "Token is missing"}), 401

        # Extract the token from the "Bearer" prefix
        token = token.split(" ")[1] if " " in token else token

        try:
            decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            request.username = decoded_token["username"]
            logging.debug(f"Decoded token: {decoded_token}")
        except jwt.ExpiredSignatureError:
            logging.warning("Token has expired")
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            logging.error(f"Invalid token: {e}")
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return wrapper

def role_required(required_roles):
    """Decorator for role-based access control"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            username = getattr(request, "username", None)
            user_role = users.get(username, {}).get("role")
            if not user_role or user_role not in required_roles:
                return jsonify({"error": "Access forbidden: insufficient permissions"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Register Route
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "admin")

    if username in users:
        return jsonify({"error": "User already exists"}), 400

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    # Hash the password and save the user
    hashed_password = generate_password_hash(password)
    users[username] = {"password": hashed_password, "role": role}
    save_users(users)

    return jsonify({"message": "User registered successfully"}), 201

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Login Route
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if username not in users or not check_password_hash(users[username]['password'], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Generate or retrieve existing token
    token_payload = {
        "username": username,
        "role": users[username]['role'],
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    }
    token = jwt.encode(token_payload, app.config["SECRET_KEY"], algorithm="HS256")

    # Log the token and its payload
    logging.debug(f"Generated token: {token}")
    logging.debug(f"Token payload: {token_payload}")

    return jsonify({"token": token})