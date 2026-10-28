import os

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    session
)
from werkzeug.security import check_password_hash

from database import (
    init_db,
    register_user,
    get_user_by_identifier,
    get_connection
)
from weather import get_weather


app = Flask(__name__)

# Security: configure these environment variables before starting the app.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing. Configure it before starting the app."
    )

# Only this user's Farmer ID can access the admin farmers list.
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "").strip().upper()

init_db()


# --------------------------------------------------
# HOME / REGISTRATION
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("register.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Invalid registration request."
        }), 400

    full_name = data.get("full_name", "")
    phone = data.get("phone", "")

    if not isinstance(full_name, str) or not isinstance(phone, str):
        return jsonify({
            "success": False,
            "message": "Invalid name or mobile number."
        }), 400

    full_name = full_name.strip()
    phone = phone.strip()

    if not full_name or len(full_name) > 100:
        return jsonify({
            "success": False,
            "message": "Please enter a valid full name."
        }), 400

    if (
        len(phone) != 10
        or not phone.isdigit()
        or phone[0] not in "6789"
    ):
        return jsonify({
            "success": False,
            "message": "Enter a valid 10-digit Indian mobile number."
        }), 400

    # Validate the GPS coordinates received from the frontend.
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))

        if not (-90 <= latitude <= 90):
            raise ValueError

        if not (-180 <= longitude <= 180):
            raise ValueError

        data["latitude"] = latitude
        data["longitude"] = longitude

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Please detect a valid GPS location first."
        }), 400

    # Save the registration details using database.py.
    success, message, user_id = register_user(data)

    if not success:
        return jsonify({
            "success": False,
            "message": message
        }), 400

    return jsonify({
        "success": True,
        "message": message,
        "user_id": user_id,
        "redirect": url_for("login")
    }), 201


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    identifier = request.form.get("identifier", "").strip()
    password = request.form.get("password", "")

    if not identifier or not password:
        return render_template(
            "login.html",
            error="Please enter your login ID and password."
        )

    user = get_user_by_identifier(identifier)

    if not user:
        return render_template(
            "login.html",
            error="Record not found. Please register first."
        )

    password_hash = user.get("password_hash")

    if (
        not password_hash
        or not check_password_hash(password_hash, password)
    ):
        return render_template(
            "login.html",
            error="Incorrect password. Please try again."
        )

    # Create a fresh session after successful authentication.
    session.clear()
    session["user_id"] = user["user_id"]
    session["full_name"] = user["full_name"]

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# FARMER DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        full_name=session.get("full_name"),
        user_id=session.get("user_id")
    )


# --------------------------------------------------
# ADMIN-ONLY FARMERS LIST
# --------------------------------------------------

@app.route("/admin/farmers")
def admin_farmers():
    # User must be logged in first.
    logged_in_user_id = session.get("user_id")

    if not logged_in_user_id:
        return redirect(url_for("login"))

    # Fail closed if admin access has not been configured.
    if not ADMIN_USER_ID:
        return "Admin access is not configured.", 403

    # Only the configured admin account can see registered farmers.
    if logged_in_user_id.strip().upper() != ADMIN_USER_ID:
        return "Access denied. Admin only.", 403

    search = request.args.get("search", "").strip()

    with get_connection() as conn:
        total_farmers = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        if search:
            pattern = f"%{search}%"

            farmers = conn.execute("""
                SELECT
                    user_id,
                    full_name,
                    phone,
                    email,
                    state,
                    district,
                    village,
                    pin_code,
                    farming_type,
                    farm_size,
                    crops,
                    latitude,
                    longitude,
                    created_at
                FROM users
                WHERE full_name LIKE ?
                   OR phone LIKE ?
                   OR email LIKE ?
                   OR user_id LIKE ?
                ORDER BY id DESC
            """, (pattern, pattern, pattern, pattern)).fetchall()

        else:
            farmers = conn.execute("""
                SELECT
                    user_id,
                    full_name,
                    phone,
                    email,
                    state,
                    district,
                    village,
                    pin_code,
                    farming_type,
                    farm_size,
                    crops,
                    latitude,
                    longitude,
                    created_at
                FROM users
                ORDER BY id DESC
            """).fetchall()

    return render_template(
        "admin_farmers.html",
        farmers=[dict(farmer) for farmer in farmers],
        total_farmers=total_farmers,
        search=search
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------
# WEATHER API
# --------------------------------------------------

@app.route("/weather")
def weather_page():
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))

        if not (-90 <= latitude <= 90):
            return jsonify({
                "error": "Invalid latitude"
            }), 400

        if not (-180 <= longitude <= 180):
            return jsonify({
                "error": "Invalid longitude"
            }), 400

    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid coordinates"
        }), 400

    weather_data = get_weather(latitude, longitude)

    if weather_data is None:
        return jsonify({
            "error": "Weather data could not be fetched"
        }), 502

    return jsonify(weather_data)


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    # Debug mode is disabled to reduce information exposure.
    app.run(debug=False)