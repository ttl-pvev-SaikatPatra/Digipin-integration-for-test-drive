from flask import Flask, request, render_template_string, jsonify
from flask_cors import CORS
import psycopg2
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# PostgreSQL config from Render
DB_HOST = os.environ.get("DB_HOST", "your-db-hostname")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "your-db-name")
DB_USER = os.environ.get("DB_USER", "your-db-user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "your-db-password")

# DB connection function
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# HTML page as string
HTML_FORM = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Drive Booking</title>
    <style>
        body { font-family: Arial; padding: 20px; background: #f4f4f4; }
        form { background: white; padding: 20px; border-radius: 5px; max-width: 400px; margin: auto; }
        input, select { width: 100%; padding: 10px; margin: 8px 0; }
        button { background-color: #28a745; color: white; padding: 10px; border: none; cursor: pointer; }
        button:hover { background-color: #218838; }
    </style>
</head>
<body>
    <h2 style="text-align: center;">Book a Test Drive</h2>
    <form method="post" action="/api/book">
        <label>First Name:</label>
        <input type="text" name="first_name" required>
        
        <label>Last Name:</label>
        <input type="text" name="last_name" required>
        
        <label>Mobile:</label>
        <input type="text" name="mobile" required>
        
        <label>Model:</label>
        <select name="model" required>
            <option value="Punch">Punch</option>
            <option value="Nexon">Nexon</option>
            <option value="Harrier">Harrier</option>
        </select>
        
        <label>Address:</label>
        <input type="text" name="address" required>
        
        <button type="submit">Book Now</button>
    </form>
</body>
</html>
"""

# Route to show the HTML form
@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_FORM)

# Route to handle form submission
@app.route("/api/book", methods=["POST"])
def book_test_drive():
    try:
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        mobile = request.form.get("mobile")
        model = request.form.get("model")
        address = request.form.get("address")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO test_drive_bookings (first_name, last_name, mobile, model, address, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (first_name, last_name, mobile, model, address, datetime.now()))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Booking successful"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run the app (for local testing)
if __name__ == "__main__":
    app.run(debug=True)
