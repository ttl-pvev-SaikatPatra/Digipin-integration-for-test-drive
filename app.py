from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import os

app = Flask(__name__)
CORS(app)

# MongoDB configuration
# MONGO_URI = os.environ.get("MONGO_URI")  # Set this in Render as an environment variable
client = MongoClient(mongodb+srv://saikatpatra64:Saikatpatra64@cluster0.qjespmw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0)
db = client["digipin"]
collection = db["bookings"]

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit_booking():
    data = request.json
    
# ✅ Basic manual validation (example)
    required_fields = ["customer_name", "mobile", "pincode", "car_model", "dealer_code"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"{field} is required"}), 400

    # ✅ Insert into MongoDB
    result = collection.insert_one(data)
    return jsonify({"message": "Booking saved", "id": str(result.inserted_id)}),
    data = request.json
    if not data:
        return jsonify({"status": "fail", "message": "No data received"}), 400

    try:
        collection.insert_one(data)
        return jsonify({"status": "success", "message": "Booking submitted successfully"})
    except Exception as e:
        return jsonify({"status": "fail", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
