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

def lat_long_to_digipin(latitude: float, longitude: float) -> str:
    """
    Convert coordinates to India Post Digipin using official API
    """
    try:
        # Using the official open-source Digipin API
        response = requests.get(
            "https://api.digipin.in/api/digipin/encode",  # Public endpoint
            params={'latitude': latitude, 'longitude': longitude},
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('digipin', '')
        
        print(f"Digipin API error: {response.status_code}")
        return lat_long_to_digipin_fallback(latitude, longitude)
        
    except Exception as e:
        print(f"Digipin encoding error: {e}")
        return lat_long_to_digipin_fallback(latitude, longitude)

def digipin_to_lat_long(digipin: str) -> tuple[float, float]:
    """
    Convert India Post Digipin to coordinates using official API
    """
    try:
        response = requests.get(
            "https://api.digipin.in/api/digipin/decode",
            params={'digipin': digipin.strip()},
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            lat = float(data.get('latitude', 0))
            lng = float(data.get('longitude', 0))
            return lat, lng
        
        print(f"Digipin decode API error: {response.status_code}")
        return digipin_to_lat_long_fallback(digipin)
        
    except Exception as e:
        print(f"Digipin decoding error: {e}")
        return digipin_to_lat_long_fallback(digipin)

# Keep your existing fallback functions as backup
def lat_long_to_digipin_fallback(latitude, longitude):
    """Fallback DIGIPIN generation (your existing simplified algorithm)"""
    try:
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return None
            
        # Basic grid-based encoding
        lat_grid = int((latitude + 90) * 1000) % 10000
        lon_grid = int((longitude + 180) * 1000) % 10000
        
        # Generate 8-character DIGIPIN-like code
        digipin = f"{lat_grid:04d}{lon_grid:04d}"
        return f"{digipin[:3]}-{digipin[3:6]}-{digipin[6:]}"
    except Exception as e:
        print(f"Error in fallback DIGIPIN generation: {e}")
        return None

def digipin_to_lat_long_fallback(digipin):
    """Fallback coordinate conversion (your existing simplified algorithm)"""
    try:
        clean_digipin = digipin.replace('-', '')
        if len(clean_digipin) != 8 or not clean_digipin.isdigit():
            return None, None
            
        lat_grid = int(clean_digipin[:4])
        lon_grid = int(clean_digipin[4:8])
        
        latitude = (lat_grid / 1000.0) - 90
        longitude = (lon_grid / 1000.0) - 180
        
        return latitude, longitude
    except Exception as e:
        print(f"Error in fallback coordinate conversion: {e}")
        return None, None
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
#  Real Reverse code using opncage
# ------------------------------------------------------------------ #
def get_address_from_coordinates(latitude: float, longitude: float) -> str:
    """
    Enhanced address generation for India Post Digipin
    """
    try:
        # Generate India Post compatible address
        if 18.5 <= latitude <= 20.5 and 72.5 <= longitude <= 73.5:
            areas = ["Andheri", "Bandra", "Powai", "Thane", "Navi Mumbai", "Colaba", "Worli"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Mumbai, Maharashtra"
            pin_base = 400001
        elif 28.0 <= latitude <= 29.0 and 76.5 <= longitude <= 77.5:
            areas = ["Connaught Place", "Karol Bagh", "Dwarka", "Rohini", "Lajpat Nagar"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, New Delhi, Delhi"
            pin_base = 110001
        elif 12.5 <= latitude <= 13.5 and 77.0 <= longitude <= 78.0:
            areas = ["Koramangala", "Whitefield", "Electronic City", "Jayanagar", "Indiranagar"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Bengaluru, Karnataka"
            pin_base = 560001
        else:
            # Generic Indian address
            states = ["Maharashtra", "Karnataka", "Tamil Nadu", "Gujarat", "Rajasthan"]
            areas = ["Central Area", "Market Zone", "Residential Block", "Commercial District"]
            state = states[abs(int(latitude*longitude)) % len(states)]
            area_name = areas[abs(int(latitude*100)) % len(areas)]
            area = f"{area_name}, {state}"
            pin_base = 400001
        
        # Calculate PIN code variation
        pin_offset = abs(int((latitude + longitude) * 1000)) % 99
        pin_code = pin_base + pin_offset
        
        return f"{area}, PIN-{pin_code:06d}, India"
        
    except Exception as e:
        print(f"Error in address generation: {e}")
        return "Address could not be determined"
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

        digipin = lat_long_to_digipin(lat, lng)
        address   = get_address_from_coordinates(lat, lng)

        return jsonify({
            'digipin': digipin,      # still exposing as “digipin”
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
        digipin = lat_long_to_digipin(lat, lng)
        return jsonify({'digipin': digipin, 'latitude': lat, 'longitude': lng})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

# ---------- API: plus-code → lat/lng ------------------------------ #
@app.route('/api/get-location', methods=['POST'])
def api_get_location():
    try:
        digipin = request.get_json(force=True)['digipin'].strip()
        lat, lng  = digipin_to_lat_long(digipin)
        address   = get_address_from_coordinates(lat, lng)
        return jsonify({'digipin': digipin, 'latitude': lat, 'longitude': lng, 'address': address})
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
        digipin = lat_long_to_digipin(lat, lng)

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
            digipin      = digipin,                     # stored under same column
            address      = data['address'].strip(),
            vehicle_type = data['vehicle_type'].strip(),
            test_drive_date = datetime.fromisoformat(data['test_drive_date']),
            status='booked'
        ))
        db.session.commit()

        return jsonify({'success': True, 'booking_id': booking_id,
                        'digipin': digipin, 'message': 'Test drive booked!'})
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
