from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# ✅ Load PostgreSQL connection from environment variable
app.config['SQLALCHEMY_DATABASE_URI'] ='postgresql://testdrive_db_user:3MwrW6T038nWmddw1BxfQGu4NsRLL6Wl@dpg-d20ahv15pdvs73caoo7g-a:5432/testdrive_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Initialize SQLAlchemy
db = SQLAlchemy(app)

# ✅ Define the Bookings Table
class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float)       # ✅ New
    longitude = db.Column(db.Float)      # ✅ New
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ✅ Create tables before first request
@app.before_first_request
def create_tables():
    db.create_all()

# ✅ HTML Form Endpoint
@app.route('/', methods=['GET'])
def home():
    return render_template('form.html')

# ✅ NEW ROUTE: serve the index.html page
@app.route('/')
def index():
    return render_template('index.html')
    
# ✅ API to Submit Booking
@app.route('/submit', methods=['POST'])
def submit():
    try:
        data = request.form
        new_booking = Booking(
            first_name=data['first_name'],
            last_name=data['last_name'],
            mobile=data['mobile'],
            model=data['model'],
            address=data['address']
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect('/')
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# ✅ Optional: API to fetch all bookings (for testing)
@app.route('/bookings', methods=['GET'])
def list_bookings():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    results = [
        {
            "first_name": b.first_name,
            "last_name": b.last_name,
            "mobile": b.mobile,
            "model": b.model,
            "address": b.address,
            "created_at": b.created_at.strftime('%Y-%m-%d %H:%M')
        }
        for b in bookings
    ]
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
