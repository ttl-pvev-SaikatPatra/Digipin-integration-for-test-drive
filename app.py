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

# =================== OFFICIAL INDIA POST DIGIPIN INTEGRATION ===================

def get_india_post_digipin_from_coordinates(latitude, longitude):
    """
    Get official DIGIPIN from coordinates using India Post API
    """
    try:
        # Check cache first
        cache_key = f"coord_{latitude:.6f}_{longitude:.6f}"
        if cache_key in digipin_cache:
            cached_data, timestamp = digipin_cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=1):
                return cached_data
        
        api_key = os.environ.get('INDIA_POST_API_KEY')
        base_url = os.environ.get('INDIA_POST_API_URL', 'https://dak.indiapost.gov.in/api/v1')
        
        if not api_key:
            print("India Post API key not configured, using fallback")
            return None
        
        # API request payload for reverse geocoding
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "output_format": "json",
            "language": "en",
            "include_address": True
        }
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'DIGIPIN-TestDrive-App/1.0'
        }
        
        # Make API request
        response = requests.post(
            f"{base_url}/digipin/reverse",
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'success':
                result = {
                    'success': True,
                    'digipin': data.get('digipin'),
                    'formatted_address': format_india_post_address(data),
                    'components': {
                        'house_number': data.get('house_number'),
                        'street': data.get('street'),
                        'locality': data.get('locality'),
                        'sub_district': data.get('sub_district'),
                        'district': data.get('district'),
                        'state': data.get('state'),
                        'pin_code': data.get('pin_code'),
                        'country': 'India'
                    },
                    'confidence': data.get('confidence', 0.9),
                    'source': 'india_post_official'
                }
                
                # Cache the result
                digipin_cache[cache_key] = (result, datetime.now())
                return result
        
        print(f"India Post API error: {response.status_code} - {response.text}")
        return None
        
    except requests.exceptions.Timeout:
        print("India Post API timeout")
        return None
    except requests.exceptions.RequestException as e:
        print(f"India Post API request error: {e}")
        return None
    except Exception as e:
        print(f"India Post API error: {e}")
        return None

def get_coordinates_from_india_post_digipin(digipin):
    """
    Get coordinates and address from official DIGIPIN using India Post API
    """
    try:
        # Check cache first
        cache_key = f"digipin_{digipin}"
        if cache_key in digipin_cache:
            cached_data, timestamp = digipin_cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=1):
                return cached_data
        
        api_key = os.environ.get('INDIA_POST_API_KEY')
        base_url = os.environ.get('INDIA_POST_API_URL', 'https://dak.indiapost.gov.in/api/v1')
        
        if not api_key:
            print("India Post API key not configured, using fallback")
            return None
        
        # API request payload for forward geocoding
        payload = {
            "digipin": digipin,
            "output_format": "json",
            "language": "en",
            "include_coordinates": True
        }
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'DIGIPIN-TestDrive-App/1.0'
        }
        
        # Make API request
        response = requests.post(
            f"{base_url}/digipin/forward",
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'success':
                result = {
                    'success': True,
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'digipin': digipin,
                    'formatted_address': format_india_post_address(data),
                    'components': {
                        'house_number': data.get('house_number'),
                        'street': data.get('street'),
                        'locality': data.get('locality'),
                        'sub_district': data.get('sub_district'),
                        'district': data.get('district'),
                        'state': data.get('state'),
                        'pin_code': data.get('pin_code'),
                        'country': 'India'
                    },
                    'confidence': data.get('confidence', 0.9),
                    'source': 'india_post_official'
                }
                
                # Cache the result
                digipin_cache[cache_key] = (result, datetime.now())
                return result
        
        print(f"India Post DIGIPIN lookup error: {response.status_code} - {response.text}")
        return None
        
    except requests.exceptions.Timeout:
        print("India Post API timeout")
        return None
    except requests.exceptions.RequestException as e:
        print(f"India Post API request error: {e}")
        return None
    except Exception as e:
        print(f"India Post DIGIPIN lookup error: {e}")
        return None

def format_india_post_address(api_data):
    """Format India Post API response into readable address"""
    try:
        components = []
        
        # Building/House number
        if api_data.get('house_number'):
            components.append(api_data['house_number'])
        
        # Street
        if api_data.get('street'):
            components.append(api_data['street'])
        
        # Locality
        if api_data.get('locality'):
            components.append(api_data['locality'])
        
        # Sub-district
        if api_data.get('sub_district'):
            components.append(api_data['sub_district'])
        
        # District
        if api_data.get('district'):
            components.append(api_data['district'])
        
        # State
        if api_data.get('state'):
            components.append(api_data['state'])
        
        # PIN Code
        if api_data.get('pin_code'):
            components.append(f"PIN-{api_data['pin_code']}")
        
        # Country
        components.append('India')
        
        return ', '.join(filter(None, components))
        
    except Exception as e:
        print(f"Address formatting error: {e}")
        return "Address formatting failed"

# =================== ENHANCED DIGIPIN FUNCTIONS WITH OFFICIAL API ===================

def lat_long_to_digipin(latitude, longitude):
    """
    Convert latitude and longitude to DIGIPIN using official India Post API
    Falls back to simplified algorithm if API is unavailable
    """
    try:
        # Try official India Post API first
        result = get_india_post_digipin_from_coordinates(latitude, longitude)
        if result and result.get('success') and result.get('digipin'):
            return result['digipin']
        
        # Fallback to simplified algorithm
        print("Using fallback DIGIPIN generation")
        return lat_long_to_digipin_fallback(latitude, longitude)
        
    except Exception as e:
        print(f"Error in lat_long_to_digipin: {e}")
        return lat_long_to_digipin_fallback(latitude, longitude)

def lat_long_to_digipin_fallback(latitude, longitude):
    """Fallback DIGIPIN generation (simplified algorithm)"""
    try:
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return None
            
        # Basic grid-based encoding
        lat_grid = int((latitude + 90) * 1000) % 10000
        lon_grid = int((longitude + 180) * 1000) % 10000
        
        # Generate 10-character DIGIPIN-like code
        digipin = f"{lat_grid:04d}{lon_grid:04d}"
        return f"{digipin[:3]}-{digipin[3:6]}-{digipin[6:]}"
    except Exception as e:
        print(f"Error in fallback DIGIPIN generation: {e}")
        return None

def digipin_to_lat_long(digipin):
    """
    Convert DIGIPIN to coordinates using official India Post API
    Falls back to simplified algorithm if API is unavailable
    """
    try:
        # Try official India Post API first
        result = get_coordinates_from_india_post_digipin(digipin)
        if result and result.get('success'):
            return result.get('latitude'), result.get('longitude')
        
        # Fallback to simplified algorithm
        print("Using fallback coordinate conversion")
        return digipin_to_lat_long_fallback(digipin)
        
    except Exception as e:
        print(f"Error in digipin_to_lat_long: {e}")
        return digipin_to_lat_long_fallback(digipin)

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
    Get address from coordinates using official India Post API
    Falls back to simplified generation if API is unavailable
    """
    try:
        # Try official India Post API first
        result = get_india_post_digipin_from_coordinates(latitude, longitude)
        if result and result.get('success') and result.get('formatted_address'):
            return result['formatted_address']
        
        # Fallback to simplified address generation
        print("Using fallback address generation")
        return get_address_from_coordinates_fallback(latitude, longitude)
        
    except Exception as e:
        print(f"Error in get_address_from_coordinates: {e}")
        return get_address_from_coordinates_fallback(latitude, longitude)

def get_address_from_coordinates_fallback(latitude, longitude):
    """Fallback address generation (simplified algorithm)"""
    try:
        # Your existing fallback logic here
        if 21.5 <= latitude <= 27.0 and 87.0 <= longitude <= 89.5:
            areas = ["Salt Lake", "Park Street", "Ballygunge", "Howrah", "Durgapur"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, Kolkata, West Bengal"
        elif 28.0 <= latitude <= 29.0 and 76.5 <= longitude <= 77.5:
            areas = ["Connaught Place", "Karol Bagh", "Dwarka", "Rohini", "Lajpat Nagar"]
            area = f"{areas[abs(int(latitude*longitude)) % len(areas)]}, New Delhi, Delhi"
        else:
            states = ["Karnataka", "Maharashtra", "Tamil Nadu", "Gujarat", "Rajasthan"]
            area_names = ["Green Colony", "Royal Enclave", "Sunrise Nagar"]
            state = states[abs(int(latitude * longitude)) % len(states)]
            area_name = area_names[abs(int(latitude * 100)) % len(area_names)]
            area = f"{area_name}, {state}"
        
        street_num = abs(int((latitude + longitude) * 100)) % 999 + 1
        pin_code = abs(int((latitude * longitude) * 10000)) % 899999 + 100000
        
        return f"Street {street_num}, {area}, PIN-{pin_code}, India"
        
    except Exception as e:
        print(f"Error in fallback address generation: {e}")
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

# =================== UPDATED API ROUTES ===================

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
        
        # Get official DIGIPIN and address from India Post
        result = get_india_post_digipin_from_coordinates(lat, lng)
        
        if result and result.get('success'):
            return jsonify({
                'digipin': result['digipin'],
                'address': result['formatted_address'],
                'components': result.get('components', {}),
                'latitude': lat,
                'longitude': lng,
                'source': result['source'],
                'confidence': result.get('confidence', 0.9)
            })
        else:
            # Fallback response
            digipin = lat_long_to_digipin_fallback(lat, lng)
            address = get_address_from_coordinates_fallback(lat, lng)
            
            return jsonify({
                'digipin': digipin,
                'address': address,
                'latitude': lat,
                'longitude': lng,
                'source': 'fallback',
                'confidence': 0.5
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
        
        # Use official DIGIPIN API
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
        
        # Use official DIGIPIN API
        result = get_coordinates_from_india_post_digipin(digipin.strip())
        
        if result and result.get('success'):
            return jsonify({
                'latitude': result['latitude'],
                'longitude': result['longitude'],
                'digipin': digipin,
                'address': result.get('formatted_address'),
                'source': result['source'],
                'confidence': result.get('confidence', 0.9)
            })
        else:
            # Fallback to simplified algorithm
            latitude, longitude = digipin_to_lat_long_fallback(digipin.strip())
            if latitude is None or longitude is None:
                return jsonify({'error': 'Invalid DIGIPIN format'}), 400
            
            return jsonify({
                'latitude': latitude,
                'longitude': longitude,
                'digipin': digipin,
                'source': 'fallback',
                'confidence': 0.5
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
        
        # Convert coordinates to DIGIPIN using official API
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
