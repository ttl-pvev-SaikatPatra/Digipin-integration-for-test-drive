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

def generate_booking_id():
    """Generate alphanumeric booking ID in format: 5-XXXXXXXX"""
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"5-{random_chars}"

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///digipin_test.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Handle PostgreSQL URL format issue on Render
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db = SQLAlchemy(app)

# Cache for API responses to reduce calls
digipin_cache = {}

# Database Models
class TestDrive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(10), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    digipin = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    test_drive_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='booked')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Database Migration Function
def migrate_database():
    """Automatically migrate database schema and data"""
    try:
        with app.app_context():
            engine = db.engine
            inspector = sqlalchemy.inspect(engine)
            
            # Check if booking_id column exists
            columns = [col['name'] for col in inspector.get_columns('test_drive')]
            
            if 'booking_id' not in columns:
                print("Adding booking_id column...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE test_drive ADD COLUMN booking_id VARCHAR(10)"))
                    conn.commit()
                print("booking_id column added successfully")
            
            # Backfill existing records without booking_id
            existing_records = TestDrive.query.filter(
                (TestDrive.booking_id == None) | (TestDrive.booking_id == '')
            ).all()
            
            for record in existing_records:
                booking_id = generate_booking_id()
                while TestDrive.query.filter_by(booking_id=booking_id).first():
                    booking_id = generate_booking_id()
                
                record.booking_id = booking_id
                if record.status == 'pending':
                    record.status = 'booked'
            
            if existing_records:
                db.session.commit()
                print(f"Updated {len(existing_records)} existing records")
                
    except Exception as e:
        print(f"Migration error: {e}")
        db.session.rollback()

# =================== OPEN-SOURCE DIGIPIN INTEGRATION ===================

def get_opensource_digipin_from_coordinates(latitude, longitude):
    """
    Get DIGIPIN from coordinates using open-source DIGIPIN API
    """
    try:
        # Check cache first
        cache_key = f"coord_{latitude:.6f}_{longitude:.6f}"
        if cache_key in digipin_cache:
            cached_data, timestamp = digipin_cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=1):
                return cached_data
        
        digipin_api_url = os.environ.get('DIGIPIN_API_URL', 'http://localhost:3000')
        
        # Call the open-source DIGIPIN encode endpoint
        response = requests.get(
            f"{digipin_api_url}/api/digipin/encode",
            params={
                'latitude': latitude,
                'longitude': longitude
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success') and data.get('digipin'):
                result = {
                    'success': True,
                    'digipin': data.get('digipin'),
                    'latitude': latitude,
                    'longitude': longitude,
                    'source': 'opensource_digipin',
                    'confidence': 0.95
                }
                
                # Cache the result
                digipin_cache[cache_key] = (result, datetime.now())
                return result
        
        print(f"Open-source DIGIPIN API error: {response.status_code} - {response.text}")
        return None
        
    except requests.exceptions.Timeout:
        print("Open-source DIGIPIN API timeout")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Open-source DIGIPIN API request error: {e}")
        return None
    except Exception as e:
        print(f"Open-source DIGIPIN API error: {e}")
        return None

def get_coordinates_from_opensource_digipin(digipin):
    """
    Get coordinates from DIGIPIN using open-source DIGIPIN API
    """
    try:
        # Check cache first
        cache_key = f"digipin_{digipin}"
        if cache_key in digipin_cache:
            cached_data, timestamp = digipin_cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=1):
                return cached_data
        
        digipin_api_url = os.environ.get('DIGIPIN_API_URL', 'http://localhost:3000')
        
        # Call the open-source DIGIPIN decode endpoint
        response = requests.get(
            f"{digipin_api_url}/api/digipin/decode",
            params={'digipin': digipin},
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success') and data.get('latitude') and data.get('longitude'):
                result = {
                    'success': True,
                    'latitude': float(data.get('latitude')),
                    'longitude': float(data.get('longitude')),
                    'digipin': digipin,
                    'source': 'opensource_digipin',
                    'confidence': 0.95
                }
                
                # Cache the result
                digipin_cache[cache_key] = (result, datetime.now())
                return result
        
        print(f"Open-source DIGIPIN decode error: {response.status_code} - {response.text}")
        return None
        
    except requests.exceptions.Timeout:
        print("Open-source DIGIPIN API timeout")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Open-source DIGIPIN API request error: {e}")
        return None
    except Exception as e:
        print(f"Open-source DIGIPIN decode error: {e}")
        return None

# =================== DIGIPIN FUNCTIONS WITH OPENSOURCE API ===================

def lat_long_to_digipin(latitude, longitude):
    """
    Convert latitude and longitude to DIGIPIN using open-source API
    Falls back to simplified algorithm if API is unavailable
    """
    try:
        # Try open-source DIGIPIN API first
        result = get_opensource_digipin_from_coordinates(latitude, longitude)
        if result and result.get('success') and result.get('digipin'):
            return result['digipin']
        
        # Fallback to simplified algorithm
        print("Open-source DIGIPIN API unavailable, using fallback")
        return lat_long_to_digipin_fallback(latitude, longitude)
        
    except Exception as e:
        print(f"Error in lat_long_to_digipin: {e}")
        return lat_long_to_digipin_fallback(latitude, longitude)

def digipin_to_lat_long(digipin):
    """
    Convert DIGIPIN to coordinates using open-source API
    Falls back to simplified algorithm if API is unavailable
    """
    try:
        # Try open-source DIGIPIN API first
        result = get_coordinates_from_opensource_digipin(digipin)
        if result and result.get('success'):
            return result.get('latitude'), result.get('longitude')
        
        # Fallback to simplified algorithm
        print("Open-source DIGIPIN API unavailable, using fallback")
        return digipin_to_lat_long_fallback(digipin)
        
    except Exception as e:
        print(f"Error in digipin_to_lat_long: {e}")
        return digipin_to_lat_long_fallback(digipin)

# =================== FALLBACK FUNCTIONS ===================

def lat_long_to_digipin_fallback(latitude, longitude):
    """Fallback DIGIPIN generation (simplified algorithm)"""
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
    """Fallback coordinate conversion (simplified algorithm)"""
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

def get_address_from_coordinates(latitude, longitude):
    """
    Get address from coordinates using simplified generation
    This can be enhanced with geocoding APIs like OpenCage, Google Maps, etc.
    """
    try:
        # Simplified address generation for Indian locations
        if 21.5 <= latitude <= 27.0 and 87.0 <= longitude <= 89.5:
            areas = ["Salt Lake", "Park Street", "Ballygunge", "Howrah", "Durgapur"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Kolkata, West Bengal"
        elif 28.0 <= latitude <= 29.0 and 76.5 <= longitude <= 77.5:
            areas = ["Connaught Place", "Karol Bagh", "Dwarka", "Rohini", "Lajpat Nagar"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, New Delhi, Delhi"
        elif 18.5 <= latitude <= 20.5 and 72.5 <= longitude <= 73.5:
            areas = ["Andheri", "Bandra", "Powai", "Thane", "Navi Mumbai"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Mumbai, Maharashtra"
        elif 12.5 <= latitude <= 13.5 and 77.0 <= longitude <= 78.0:
            areas = ["Koramangala", "Whitefield", "Electronic City", "Jayanagar", "Indiranagar"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Bangalore, Karnataka"
        elif 12.5 <= latitude <= 13.5 and 79.5 <= longitude <= 80.5:
            areas = ["T Nagar", "Anna Nagar", "Velachery", "Adyar", "Guindy"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Chennai, Tamil Nadu"
        else:
            # Generic address for other locations
            states = ["Karnataka", "Maharashtra", "Tamil Nadu", "Gujarat", "Rajasthan", "Punjab", "Haryana"]
            area_names = ["Green Colony", "Royal Enclave", "Sunrise Nagar", "Paradise Township", "Golden Heights"]
            
            state = states[abs(int(latitude * longitude)) % len(states)]
            area_name = area_names[abs(int(latitude * 100)) % len(area_names)]
            
            # Generate city name
            city_prefixes = ["New", "East", "West", "North", "South"]
            city_suffixes = ["pur", "bad", "nagar", "ganj"]
            city_prefix = city_prefixes[abs(int(latitude * 10)) % len(city_prefixes)]
            city_suffix = city_suffixes[abs(int(longitude * 10)) % len(city_suffixes)]
            city_name = f"{city_prefix}{city_suffix}"
            
            area = f"{area_name}, {city_name}, {state}"
        
        # Generate street number and PIN code
        street_num = abs(int((latitude + longitude) * 100)) % 999 + 1
        pin_code = abs(int((latitude * longitude) * 10000)) % 899999 + 100000
        
        return f"Street {street_num}, {area}, PIN-{pin_code}, India"
        
    except Exception as e:
        print(f"Error in address generation: {e}")
        return "Address could not be determined from location"

# Initialize database
first_request = True

@app.before_request
def before_first_request():
    global first_request
    if first_request:
        with app.app_context():
            db.create_all()
            migrate_database()
        first_request = False

# =================== API ROUTES ===================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/book-test-drive')
def book_test_drive():
    return render_template('book_test_drive.html')

@app.route('/api/get-address', methods=['POST'])
def api_get_address():
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
        
        # Get DIGIPIN using open-source API
        digipin = lat_long_to_digipin(lat, lng)
        if not digipin:
            return jsonify({'error': 'Invalid coordinates for DIGIPIN'}), 400
        
        # Get address from coordinates
        address = get_address_from_coordinates(lat, lng)
        
        # Determine source
        result = get_opensource_digipin_from_coordinates(lat, lng)
        source = result.get('source', 'fallback') if result else 'fallback'
        confidence = result.get('confidence', 0.5) if result else 0.5
        
        return jsonify({
            'digipin': digipin,
            'address': address,
            'latitude': lat,
            'longitude': lng,
            'source': source,
            'confidence': confidence
        })
        
    except Exception as e:
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
        
        # Use open-source DIGIPIN API
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
        
        # Use open-source DIGIPIN API
        latitude, longitude = digipin_to_lat_long(digipin.strip())
        if latitude is None or longitude is None:
            return jsonify({'error': 'Invalid DIGIPIN format'}), 400
        
        # Determine source
        result = get_coordinates_from_opensource_digipin(digipin.strip())
        source = result.get('source', 'fallback') if result else 'fallback'
        confidence = result.get('confidence', 0.5) if result else 0.5
        
        return jsonify({
            'latitude': latitude,
            'longitude': longitude,
            'digipin': digipin,
            'source': source,
            'confidence': confidence
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        
        # Convert coordinates to DIGIPIN using open-source API
        digipin = lat_long_to_digipin(lat, lng)
        if not digipin:
            return jsonify({'error': 'Invalid coordinates for DIGIPIN conversion'}), 400
        
        # Generate unique booking ID
        booking_id = generate_booking_id()
        while TestDrive.query.filter_by(booking_id=booking_id).first():
            booking_id = generate_booking_id()
        
        # Create new test drive booking
        test_drive = TestDrive(
            booking_id=booking_id,
            name=data['name'].strip(),
            email=data['email'].strip().lower(),
            phone=data['phone'].strip(),
            latitude=lat,
            longitude=lng,
            digipin=digipin,
            address=data['address'].strip(),
            vehicle_type=data['vehicle_type'].strip(),
            test_drive_date=datetime.fromisoformat(data['test_drive_date']),
            status='booked'
        )
        
        db.session.add(test_drive)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'booking_id': booking_id,
            'digipin': digipin,
            'message': 'Test drive booked successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
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
        'booking_id': booking.booking_id,
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
