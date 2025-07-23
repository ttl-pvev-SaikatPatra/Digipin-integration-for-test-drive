from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# ✅ Load PostgreSQL connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://testdrive_db_user:3MwrW6T038nWmddw1BxfQGu4NsRLL6Wl@dpg-d20ahv15pdvs73caoo7g-a:5432/testdrive_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Initialize DB
db = SQLAlchemy(app)

# ✅ Define Bookings Model
class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ✅ Create DB tables
@app.before_first_request
def create_tables():
    db.create_all()

# ✅ Serve HTML Form
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# ✅ Handle Form Submission
@app.route('/submit', methods=['POST'])
def submit():
    try:
        data = request.form
        new_booking = Booking(
            first_name=data['first_name'],
            last_name=data['last_name'],
            mobile=data['mobile'],
            model=data['model'],
            address=data['address'],
            latitude=float(data.get('latitude', 0)),
            longitude=float(data.get('longitude', 0))
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect('/')
    except Exception as e:
        return f"An error occurred while saving booking: {str(e)}", 500

# ✅ Optional: View All Bookings
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
            "latitude": b.latitude,
            "longitude": b.longitude,
            "created_at": b.created_at.strftime('%Y-%m-%d %H:%M')
        }
        for b in bookings
    ]
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)  # For production, use app.run(host='0.0.0.0', port=5000)
