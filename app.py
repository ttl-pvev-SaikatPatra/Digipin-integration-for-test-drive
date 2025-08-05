from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os, requests, random, string
from datetime import datetime
import sqlalchemy
from sqlalchemy import text

# ──────────────────────────  Helpers ────────────────────────── #

def generate_booking_id() -> str:
    """Return an ID like 5-8AL4M2KQ."""
    return f"5-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"

# ---------- DigiPIN encoding & decoding (India Post) ----------- #
DIGIPIN_API = "https://api.digipin.in/api/digipin"        # encode / decode base URL

def lat_long_to_digipin(lat: float, lng: float) -> str:
    """Official India-Post DigiPIN for a coordinate, with fallback."""
    try:
        r = requests.get(f"{DIGIPIN_API}/encode",
                         params={"latitude": lat, "longitude": lng},
                         timeout=10)
        if r.ok:
            return r.json().get("digipin", "")
        print(f"[encode] HTTP {r.status_code}")
    except Exception as exc:
        print(f"[encode] {exc}")
    return lat_long_to_digipin_fallback(lat, lng)

def digipin_to_lat_long(digipin: str) -> tuple[float, float]:
    """Decode DigiPIN back to (lat, lng), with fallback."""
    try:
        r = requests.get(f"{DIGIPIN_API}/decode",
                         params={"digipin": digipin.strip()},
                         timeout=10)
        if r.ok:
            j = r.json()
            return float(j.get("latitude", 0)), float(j.get("longitude", 0))
        print(f"[decode] HTTP {r.status_code}")
    except Exception as exc:
        print(f"[decode] {exc}")
    return digipin_to_lat_long_fallback(digipin)

# ---------- Simple fallback generator -------------------------- #
def lat_long_to_digipin_fallback(lat: float, lng: float) -> str:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return ""
    lg = int((lat + 90) * 1000) % 10000
    ln = int((lng + 180) * 1000) % 10000
    code = f"{lg:04d}{ln:04d}"
    return f"{code[:3]}-{code[3:6]}-{code[6:]}"

def digipin_to_lat_long_fallback(digipin: str) -> tuple[float, float]:
    c = digipin.replace("-", "")
    if len(c) != 8 or not c.isdigit():
        return None, None
    lat = (int(c[:4]) / 1000) - 90
    lng = (int(c[4:]) / 1000) - 180
    return lat, lng

# ---------- Quick synthetic reverse-geocoder -------------------- #
def get_address_from_coordinates(lat: float, lng: float) -> str:
    """Very-rough address builder (replace with real API when ready)."""
    try:
        if 18.5 <= lat <= 20.5 and 72.5 <= lng <= 73.5:
            area, base = "Mumbai, Maharashtra", 400001
        elif 28.0 <= lat <= 29.0 and 76.5 <= lng <= 77.5:
            area, base = "New Delhi, Delhi",    110001
        else:
            area, base = "India", 560001
        pin = base + abs(int((lat + lng) * 1000)) % 99
        return f"{area}, PIN-{pin:06d}, India"
    except Exception:
        return "Address unavailable"

# ──────────────────────────  Flask / DB ──────────────────────── #
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']  = os.getenv("DATABASE_URL", "sqlite:///digipin_test.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", os.urandom(24).hex())
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace(
        "postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

class TestDrive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(10), unique=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    digipin = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    test_drive_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def migrate_database():
    with app.app_context():
        engine = db.engine
        insp   = sqlalchemy.inspect(engine)
        cols   = [c["name"] for c in insp.get_columns("test_drive")]
        if "booking_id" not in cols:
            with engine.connect() as c:
                c.execute(text("ALTER TABLE test_drive ADD COLUMN booking_id VARCHAR(10)"))
                c.commit()
        for rec in TestDrive.query.filter((TestDrive.booking_id == None) | (TestDrive.booking_id == "")):
            rec.booking_id = generate_booking_id()
        db.session.commit()

_first = True
@app.before_request
def _init():
    global _first
    if _first:
        db.create_all()
        migrate_database()
        _first = False

# ───────────────────────────  Routes  ────────────────────────── #
@app.route('/')
def index(): return render_template("index.html")

@app.route('/book-test-drive')
def book_test_drive():
    return render_template('book_test_drive.html')

@app.route('/api/get-address', methods=['POST'])
def api_get_address():
    try:
        d   = request.get_json(force=True)
        lat = float(d["latitude"]); lng = float(d["longitude"])
        pin = lat_long_to_digipin(lat, lng)
        addr= get_address_from_coordinates(lat, lng)
        return jsonify({"digipin": pin, "address": addr, "latitude": lat, "longitude": lng})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-digipin', methods=['POST'])
def api_get_digipin():
    try:
        d   = request.get_json(force=True)
        lat = float(d["latitude"]); lng = float(d["longitude"])
        return jsonify({"digipin": lat_long_to_digipin(lat, lng), "latitude": lat, "longitude": lng})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-location', methods=['POST'])
def api_get_location():
    try:
        pin = request.get_json(force=True)["digipin"].strip()
        lat, lng = digipin_to_lat_long(pin)
        addr = get_address_from_coordinates(lat, lng)
        return jsonify({"digipin": pin, "latitude": lat, "longitude": lng, "address": addr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/book-test-drive', methods=['POST'])
def api_book_test_drive():
    try:
        d = request.get_json(force=True)
        need = ['name','email','phone','latitude','longitude','address','vehicle_type','test_drive_date']
        missing = [f for f in need if not d.get(f)]
        if missing:
            return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

        lat,lng = float(d["latitude"]), float(d["longitude"])
        pin     = lat_long_to_digipin(lat, lng)
        bid     = generate_booking_id()
        while TestDrive.query.filter_by(booking_id=bid).first():
            bid = generate_booking_id()

        db.session.add(TestDrive(
            booking_id=bid, name=d["name"].strip(), email=d["email"].lower().strip(),
            phone=d["phone"].strip(), latitude=lat, longitude=lng, digipin=pin,
            address=d["address"].strip(), vehicle_type=d["vehicle_type"].strip(),
            test_drive_date=datetime.fromisoformat(d["test_drive_date"]), status="booked"
        )); db.session.commit()
        return jsonify({"success": True, "booking_id": bid, "digipin": pin,
                        "message": "Test drive booked!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings')
def api_bookings():
    return jsonify([{
        "id": b.id, "booking_id": b.booking_id, "name": b.name, "email": b.email,
        "phone": b.phone, "digipin": b.digipin, "address": b.address,
        "vehicle_type": b.vehicle_type, "test_drive_date": b.test_drive_date.isoformat(),
        "status": b.status, "created_at": b.created_at.isoformat()
    } for b in TestDrive.query.order_by(TestDrive.created_at.desc()).all()])

@app.route('/bookings')
def view_bookings():
    bookings = TestDrive.query.order_by(TestDrive.created_at.desc()).all()
    return render_template('bookings.html', bookings=bookings)

@app.route('/health')
def health(): return jsonify({"status":"healthy","ts":datetime.utcnow().isoformat()})

# ───────────────────────────  Run  ───────────────────────────── #
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), debug=False)
