from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import json
import random
import string
from datetime import datetime, timedelta
import sqlalchemy
from sqlalchemy import text
from openlocationcode.openlocationcode import encode, decode   # ← correct import

# ------------------------------------------------------------------ #
#  Utility helpers
# ------------------------------------------------------------------ #
def generate_booking_id() -> str:
    """Generate alphanumeric booking ID in format: 5-XXXXXXXX"""
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"5-{random_chars}"

def lat_long_to_plus_code(latitude: float, longitude: float, code_length: int = 10) -> str:
    """Convert latitude/longitude → Plus Code (your ‘digipin’)."""
    return encode(latitude, longitude, code_length)

def plus_code_to_lat_long(plus_code: str) -> tuple[float, float]:
    """Convert Plus Code → latitude/longitude."""
    area = decode(plus_code)
    return area.latitudeCenter, area.longitudeCenter

# ------------------------------------------------------------------ #
#  Flask / SQLAlchemy setup
# ------------------------------------------------------------------ #
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///digipin_test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Handle “postgres://” → “postgresql://” for Render
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
        'postgres://', 'postgresql://', 1
    )

db = SQLAlchemy(app)

# ------------------------------------------------------------------ #
#  Database model
# ------------------------------------------------------------------ #
class TestDrive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(10), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    digipin = db.Column(db.String(20), nullable=False)      # still called “digipin” in DB
    address = db.Column(db.Text, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    test_drive_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='booked')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------------------------------------------------------ #
#  (Optional) DB migration to add booking_id on first run
# ------------------------------------------------------------------ #
def migrate_database():
    try:
        with app.app_context():
            engine = db.engine
            inspector = sqlalchemy.inspect(engine)

            columns = [c['name'] for c in inspector.get_columns('test_drive')]
            if 'booking_id' not in columns:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE test_drive ADD COLUMN booking_id VARCHAR(10)"))
                    conn.commit()

            # back-fill missing booking IDs
            for rec in TestDrive.query.filter(
                (TestDrive.booking_id == None) | (TestDrive.booking_id == '')
            ):
                rec.booking_id = generate_booking_id()
            db.session.commit()
    except Exception as exc:
        print(f"Migration error: {exc}")
        db.session.rollback()

# ------------------------------------------------------------------ #
#  Fake reverse-geocoder (unchanged)
# ------------------------------------------------------------------ #
def get_address_from_coordinates(latitude: float, longitude: float) -> str:
    # … (your simplified address generator remains unchanged) …
    return "Address not implemented in this snippet"

# ------------------------------------------------------------------ #
#  One-time DB init
# ------------------------------------------------------------------ #
_first_request = True
@app.before_request
def _before_first_request():
    global _first_request
    if _first_request:
        db.create_all()
        migrate_database()
        _first_request = False

# ------------------------------------------------------------------ #
#  Routes
# ------------------------------------------------------------------ #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/book-test-drive')
def book_test_drive():
    return render_template('book_test_drive.html')

# ---------- API: lat/lng → plus-code + address -------------------- #
@app.route('/api/get-address', methods=['POST'])
def api_get_address():
    try:
        data = request.get_json(force=True)
        lat, lng = float(data['latitude']), float(data['longitude'])

        plus_code = lat_long_to_plus_code(lat, lng)
        address   = get_address_from_coordinates(lat, lng)

        return jsonify({
            'digipin': plus_code,      # still exposing as “digipin”
            'address': address,
            'latitude': lat,
            'longitude': lng
        })
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

# ---------- API: lat/lng → plus-code only ------------------------- #
@app.route('/api/get-digipin', methods=['POST'])
def api_get_digipin():
    try:
        data = request.get_json(force=True)
        lat, lng = float(data['latitude']), float(data['longitude'])
        plus_code = lat_long_to_plus_code(lat, lng)
        return jsonify({'digipin': plus_code, 'latitude': lat, 'longitude': lng})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

# ---------- API: plus-code → lat/lng ------------------------------ #
@app.route('/api/get-location', methods=['POST'])
def api_get_location():
    try:
        plus_code = request.get_json(force=True)['digipin'].strip()
        lat, lng  = plus_code_to_lat_long(plus_code)
        address   = get_address_from_coordinates(lat, lng)
        return jsonify({'digipin': plus_code, 'latitude': lat, 'longitude': lng, 'address': address})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

# ---------- API: booking ------------------------------------------ #
@app.route('/api/book-test-drive', methods=['POST'])
def api_book_test_drive():
    try:
        data = request.get_json(force=True)
        required = ['name', 'email', 'phone', 'latitude', 'longitude',
                    'address', 'vehicle_type', 'test_drive_date']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({'error': f'Missing field(s): {", ".join(missing)}'}), 400

        lat, lng = float(data['latitude']), float(data['longitude'])
        plus_code = lat_long_to_plus_code(lat, lng)

        booking_id = generate_booking_id()
        while TestDrive.query.filter_by(booking_id=booking_id).first():
            booking_id = generate_booking_id()

        db.session.add(TestDrive(
            booking_id   = booking_id,
            name         = data['name'].strip(),
            email        = data['email'].strip().lower(),
            phone        = data['phone'].strip(),
            latitude     = lat,
            longitude    = lng,
            digipin      = plus_code,                     # stored under same column
            address      = data['address'].strip(),
            vehicle_type = data['vehicle_type'].strip(),
            test_drive_date = datetime.fromisoformat(data['test_drive_date']),
            status='booked'
        ))
        db.session.commit()

        return jsonify({'success': True, 'booking_id': booking_id,
                        'digipin': plus_code, 'message': 'Test drive booked!'})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 500

# ---------- Bookings listing -------------------------------------- #
@app.route('/bookings')
def view_bookings():
    bookings = TestDrive.query.order_by(TestDrive.created_at.desc()).all()
    return render_template('bookings.html', bookings=bookings)

@app.route('/api/bookings')
def api_bookings():
    return jsonify([{
        'id': b.id, 'booking_id': b.booking_id, 'name': b.name,
        'email': b.email, 'phone': b.phone, 'digipin': b.digipin,
        'address': b.address, 'vehicle_type': b.vehicle_type,
        'test_drive_date': b.test_drive_date.isoformat(), 'status': b.status,
        'created_at': b.created_at.isoformat()
    } for b in TestDrive.query.order_by(TestDrive.created_at.desc()).all()])

# ---------- Health check ------------------------------------------ #
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

# ------------------------------------------------------------------ #
#  Run
# ------------------------------------------------------------------ #
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
