from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import json
import random
import string
from datetime import datetime

def generate_booking_id():
    """
    Generate alphanumeric booking ID in format: 5-XXXXXXXX
    Where X is a random alphanumeric character (A-Z, 0-9)
    """
    # Generate 8 random alphanumeric characters (uppercase letters and digits)
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"5-{random_chars}"

app = Flask(__name__)

# Database configuration - SECURITY FIXED
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///digipin_test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Handle PostgreSQL URL format issue on Render
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db = SQLAlchemy(app)

class TestDrive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(10), unique=True, nullable=False)  # Add this line
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    digipin = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    test_drive_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='booked')  # Changed default from 'pending' to 'booked'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# DIGIPIN Conversion Functions
def lat_long_to_digipin(latitude, longitude):
    """
    Convert latitude and longitude to DIGIPIN
    This is a simplified implementation - replace with actual DIGIPIN algorithm
    """
    try:
        # Validate coordinate ranges
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return None
            
        # Basic grid-based encoding (replace with actual DIGIPIN logic)
        lat_grid = int((latitude + 90) * 1000) % 10000
        lon_grid = int((longitude + 180) * 1000) % 10000
        
        # Generate 10-character DIGIPIN-like code
        digipin = f"{lat_grid:04d}{lon_grid:04d}"
        return f"{digipin[:3]}-{digipin[3:6]}-{digipin[6:]}"
    except Exception as e:
        print(f"Error in lat_long_to_digipin: {e}")  # For debugging
        return None

def digipin_to_lat_long(digipin):
    """
    Convert DIGIPIN back to latitude and longitude
    This is a simplified implementation - replace with actual DIGIPIN algorithm
    """
    try:
        # Remove hyphens and validate format
        clean_digipin = digipin.replace('-', '')
        if len(clean_digipin) != 8 or not clean_digipin.isdigit():
            return None, None
            
        lat_grid = int(clean_digipin[:4])
        lon_grid = int(clean_digipin[4:8])
        
        latitude = (lat_grid / 1000.0) - 90
        longitude = (lon_grid / 1000.0) - 180
        
        return latitude, longitude
    except Exception as e:
        print(f"Error in digipin_to_lat_long: {e}")  # For debugging
        return None, None

# Initialize database - Fixed decorator issue
first_request = True

@app.before_request
def before_first_request():
    global first_request
    if first_request:
        with app.app_context():
            db.create_all()
        first_request = False

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/book-test-drive')
def book_test_drive():
    return render_template('book_test_drive.html')

@app.route('/api/book-test-drive', methods=['POST'])
def api_book_test_drive():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone', 'latitude', 'longitude', 'address', 'vehicle_type', 'test_drive_date']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate coordinate ranges
        try:
            lat = float(data['latitude'])
            lng = float(data['longitude'])
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return jsonify({'error': 'Invalid coordinate values'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid coordinate format'}), 400
        
        # Convert coordinates to DIGIPIN
        digipin = lat_long_to_digipin(lat, lng)
        if not digipin:
            return jsonify({'error': 'Invalid coordinates for DIGIPIN conversion'}), 400
        
        # Generate unique booking ID
        booking_id = generate_booking_id()
        
        # Ensure booking ID is unique (rare collision check)
        while TestDrive.query.filter_by(booking_id=booking_id).first():
            booking_id = generate_booking_id()
        
        # Create new test drive booking
        test_drive = TestDrive(
            booking_id=booking_id,  # Add this line
            name=data['name'].strip(),
            email=data['email'].strip().lower(),
            phone=data['phone'].strip(),
            latitude=lat,
            longitude=lng,
            digipin=digipin,
            address=data['address'].strip(),
            vehicle_type=data['vehicle_type'].strip(),
            test_drive_date=datetime.fromisoformat(data['test_drive_date']),
            status='booked'  # Changed from 'pending' to 'booked'
        )
        
        db.session.add(test_drive)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'booking_id': booking_id,  # Return the custom booking ID instead of database ID
            'digipin': digipin,
            'message': 'Test drive booked successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/get-digipin', methods=['POST'])
def api_get_digipin():
    try:
        data = request.get_json()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if latitude is None or longitude is None:
            return jsonify({'error': 'Latitude and longitude are required'}), 400
        
        try:
            lat = float(latitude)
            lng = float(longitude)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid coordinate format'}), 400
        
        digipin = lat_long_to_digipin(lat, lng)
        if not digipin:
            return jsonify({'error': 'Invalid coordinates'}), 400
        
        return jsonify({
            'digipin': digipin,
            'latitude': lat,
            'longitude': lng
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-location', methods=['POST'])
def api_get_location():
    try:
        data = request.get_json()
        digipin = data.get('digipin')
        
        if not digipin:
            return jsonify({'error': 'DIGIPIN is required'}), 400
        
        latitude, longitude = digipin_to_lat_long(digipin.strip())
        if latitude is None or longitude is None:
            return jsonify({'error': 'Invalid DIGIPIN format'}), 400
        
        return jsonify({
            'latitude': latitude,
            'longitude': longitude,
            'digipin': digipin
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bookings')
def view_bookings():
    bookings = TestDrive.query.order_by(TestDrive.created_at.desc()).all()
    return render_template('bookings.html', bookings=bookings)

@app.route('/api/bookings')
def api_bookings():
    bookings = TestDrive.query.order_by(TestDrive.created_at.desc()).all()
    return jsonify([{
        'id': booking.id,
        'booking_id': booking.booking_id,  # Add this line
        'name': booking.name,
        'email': booking.email,
        'phone': booking.phone,
        'digipin': booking.digipin,
        'address': booking.address,
        'vehicle_type': booking.vehicle_type,
        'test_drive_date': booking.test_drive_date.isoformat(),
        'status': booking.status,
        'created_at': booking.created_at.isoformat()
    } for booking in bookings])

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
