from flask import Flask, request, jsonify
import psycopg2
import os

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    
@app.route("/")
def home():
    return jsonify({"message": "User Service is running"}), 200

@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json()
    name = data.get("name")
    info = data.get("info")

    if not name or not info:
        return jsonify({"error": "Name and info are required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (name, info) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING", (name, info))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": f"User '{name}' registered successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

