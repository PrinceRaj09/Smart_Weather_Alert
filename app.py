import os
import hashlib
import hmac
import io
import secrets
import smtplib
import time
import uuid
import warnings
from email.message import EmailMessage

import requests
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    session,
    send_from_directory
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from database import (
    init_db,
    register_user,
    get_user_by_identifier,
    get_connection
)
from weather import get_weather


load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# Security: configure these environment variables before starting the app.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing. Configure it before starting the app."
    )

# Only this user's Farmer ID can access the admin farmers list.
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "").strip().upper()

init_db()


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "success": False,
        "message": "Uploaded data must be 5 MB or smaller."
    }), error.code

PASSWORD_RESET_MESSAGE = (
    "If the account exists and message delivery is available, codes were "
    "sent to its registered mobile number and email address."
)
PASSWORD_RESET_TTL_SECONDS = 10 * 60
PASSWORD_RESET_RESEND_SECONDS = 60
PASSWORD_RESET_MAX_ATTEMPTS = 5
PROFILE_PICTURE_FOLDER = os.path.join(
    app.instance_path, "profile_pictures"
)
PROFILE_PICTURE_MAX_PIXELS = 20_000_000


def _process_profile_picture(upload):
    if upload is None or not upload.filename:
        return None, None

    try:
        raw_data = upload.stream.read(app.config["MAX_CONTENT_LENGTH"] + 1)
        if len(raw_data) > app.config["MAX_CONTENT_LENGTH"]:
            return None, "Profile picture must be 5 MB or smaller."

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw_data))
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                return None, "Upload a JPG, PNG, or WEBP profile picture."
            if image.width * image.height > PROFILE_PICTURE_MAX_PIXELS:
                return None, "Profile picture dimensions are too large."

            image.load()
            image.thumbnail((512, 512))
            if image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            ):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")

            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue(), None

    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError
    ):
        return None, "The selected file is not a valid supported image."


def _save_profile_picture(image_data):
    os.makedirs(PROFILE_PICTURE_FOLDER, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    path = os.path.join(PROFILE_PICTURE_FOLDER, filename)
    with open(path, "wb") as picture_file:
        picture_file.write(image_data)
    return filename


def _delete_profile_picture(filename):
    if (
        not filename
        or os.path.basename(filename) != filename
        or not filename.endswith(".jpg")
    ):
        return

    path = os.path.join(PROFILE_PICTURE_FOLDER, filename)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            app.logger.warning(
                "Could not remove a replaced profile picture.",
                exc_info=True
            )


def _missing_password_reset_settings():
    required = (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL"
    )
    return [name for name in required if not os.environ.get(name)]


def _otp_digest(user_id, channel, otp):
    value = f"{user_id}:{channel}:{otp}".encode("utf-8")
    key = app.secret_key.encode("utf-8")
    return hmac.new(key, value, hashlib.sha256).hexdigest()


def _send_sms_otp(phone, otp):
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    response = requests.post(
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{account_sid}/Messages.json",
        auth=(account_sid, os.environ["TWILIO_AUTH_TOKEN"]),
        data={
            "From": os.environ["TWILIO_FROM_NUMBER"],
            "To": f"+91{phone}",
            "Body": f"Your Smart Weather Alert password reset code is {otp}. "
                    "It expires in 10 minutes."
        },
        timeout=15
    )
    response.raise_for_status()


def _send_email_otp(email, otp):
    message = EmailMessage()
    message["Subject"] = "Smart Weather Alert password reset code"
    message["From"] = os.environ["SMTP_FROM_EMAIL"]
    message["To"] = email
    message.set_content(
        f"Your password reset code is {otp}. "
        "It expires in 10 minutes. If you did not request this, ignore "
        "this email."
    )

    with smtplib.SMTP(
        os.environ["SMTP_HOST"],
        int(os.environ.get("SMTP_PORT", "587")),
        timeout=15
    ) as smtp:
        smtp.starttls()
        smtp.login(
            os.environ["SMTP_USERNAME"],
            os.environ["SMTP_PASSWORD"]
        )
        smtp.send_message(message)


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
    profile_picture_upload = None

    if data is None and request.mimetype == "multipart/form-data":
        data = request.form.to_dict()
        profile_picture_upload = request.files.get("profile_picture")

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

    picture_data, picture_error = _process_profile_picture(
        profile_picture_upload
    )
    if picture_error:
        return jsonify({
            "success": False,
            "message": picture_error
        }), 400

    saved_picture = None
    if picture_data is not None:
        try:
            saved_picture = _save_profile_picture(picture_data)
        except OSError:
            app.logger.exception("Could not save registration profile picture.")
            return jsonify({
                "success": False,
                "message": "Could not save the profile picture. Please try again."
            }), 500
        data["profile_picture"] = saved_picture

    # Save the registration details using database.py.
    success, message, user_id = register_user(data)

    if not success:
        _delete_profile_picture(saved_picture)
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
# PASSWORD RESET
# --------------------------------------------------

@app.route("/forgot-password/request", methods=["POST"])
def request_password_reset():
    session.pop("password_reset_verified_user_id", None)

    missing_settings = _missing_password_reset_settings()
    if missing_settings:
        return jsonify({
            "success": False,
            "message": (
                "Password reset delivery is not configured. Add these "
                "settings to the project's .env file and restart the app: "
                + ", ".join(missing_settings)
            )
        }), 503

    data = request.get_json(silent=True)
    identifier = data.get("identifier", "").strip() if isinstance(
        data, dict
    ) and isinstance(data.get("identifier"), str) else ""
    user = get_user_by_identifier(identifier) if identifier else None

    if user:
        user_id = user.get("user_id")
        phone = user.get("phone")
        email = user.get("email")

        if user_id and phone and email:
            now = int(time.time())
            session["password_reset_user_id"] = user_id

            with get_connection() as conn:
                previous = conn.execute(
                    "SELECT created_at FROM password_reset_otps "
                    "WHERE user_id = ?",
                    (user_id,)
                ).fetchone()

            if not previous or now - previous["created_at"] >= (
                PASSWORD_RESET_RESEND_SECONDS
            ):
                sms_otp = f"{secrets.randbelow(1_000_000):06d}"
                email_otp = f"{secrets.randbelow(1_000_000):06d}"
                while email_otp == sms_otp:
                    email_otp = f"{secrets.randbelow(1_000_000):06d}"

                with get_connection() as conn:
                    conn.execute("""
                        INSERT INTO password_reset_otps (
                            user_id,
                            sms_otp_hash,
                            email_otp_hash,
                            expires_at,
                            attempts,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, 0, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            sms_otp_hash = excluded.sms_otp_hash,
                            email_otp_hash = excluded.email_otp_hash,
                            expires_at = excluded.expires_at,
                            attempts = 0,
                            created_at = excluded.created_at,
                            verified_at = NULL
                    """, (
                        user_id,
                        _otp_digest(user_id, "sms", sms_otp),
                        _otp_digest(user_id, "email", email_otp),
                        now + PASSWORD_RESET_TTL_SECONDS,
                        now
                    ))

                try:
                    _send_sms_otp(phone, sms_otp)
                    _send_email_otp(email, email_otp)
                except (
                    requests.RequestException,
                    OSError,
                    smtplib.SMTPException,
                    ValueError
                ):
                    app.logger.exception(
                        "Could not deliver password reset codes."
                    )
                    session.pop("password_reset_user_id", None)
                    session.pop("password_reset_verified_user_id", None)
                    with get_connection() as conn:
                        conn.execute(
                            "DELETE FROM password_reset_otps WHERE user_id = ?",
                            (user_id,)
                        )
        else:
            session.pop("password_reset_user_id", None)
    else:
        session.pop("password_reset_user_id", None)

    return jsonify({
        "success": True,
        "message": PASSWORD_RESET_MESSAGE
    })


@app.route("/forgot-password/verify", methods=["POST"])
def verify_password_reset():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Invalid password reset request."
        }), 400

    sms_otp = data.get("sms_otp", "")
    email_otp = data.get("email_otp", "")

    if not isinstance(sms_otp, str) or not isinstance(email_otp, str):
        return jsonify({
            "success": False,
            "message": "Enter both verification codes."
        }), 400

    user_id = session.get("password_reset_user_id")
    if not user_id:
        return jsonify({
            "success": False,
            "message": "Request new verification codes to continue."
        }), 400

    now = int(time.time())
    with get_connection() as conn:
        challenge = conn.execute(
            "SELECT sms_otp_hash, email_otp_hash, expires_at, attempts, "
            "verified_at "
            "FROM password_reset_otps WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if challenge and challenge["verified_at"] is not None:
            return jsonify({
                "success": False,
                "message": "Verification is complete. Create your new password."
            }), 409

        if not challenge or challenge["expires_at"] <= now:
            conn.execute(
                "DELETE FROM password_reset_otps WHERE user_id = ?",
                (user_id,)
            )
            session.pop("password_reset_user_id", None)
            return jsonify({
                "success": False,
                "message": "Verification codes expired. Request new codes."
            }), 400

        if challenge["attempts"] >= PASSWORD_RESET_MAX_ATTEMPTS:
            conn.execute(
                "DELETE FROM password_reset_otps WHERE user_id = ?",
                (user_id,)
            )
            session.pop("password_reset_user_id", None)
            return jsonify({
                "success": False,
                "message": "Too many attempts. Request new verification codes."
            }), 429

        conn.execute(
            "UPDATE password_reset_otps SET attempts = attempts + 1 "
            "WHERE user_id = ?",
            (user_id,)
        )

        valid_sms = hmac.compare_digest(
            challenge["sms_otp_hash"],
            _otp_digest(user_id, "sms", sms_otp)
        )
        valid_email = hmac.compare_digest(
            challenge["email_otp_hash"],
            _otp_digest(user_id, "email", email_otp)
        )

        if not (valid_sms and valid_email):
            if challenge["attempts"] + 1 >= PASSWORD_RESET_MAX_ATTEMPTS:
                conn.execute(
                    "DELETE FROM password_reset_otps WHERE user_id = ?",
                    (user_id,)
                )
                session.pop("password_reset_user_id", None)
                return jsonify({
                    "success": False,
                    "message": "Too many attempts. Request new verification codes."
                }), 429

            return jsonify({
                "success": False,
                "message": "One or both codes are incorrect."
            }), 400

        conn.execute(
            "UPDATE password_reset_otps SET verified_at = ?, expires_at = ? "
            "WHERE user_id = ?",
            (now, now + PASSWORD_RESET_TTL_SECONDS, user_id)
        )

    session["password_reset_verified_user_id"] = user_id
    return jsonify({
        "success": True,
        "message": "Codes verified. Create your new password to finish."
    })


@app.route("/forgot-password/complete", methods=["POST"])
def complete_password_reset():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Invalid password reset request."
        }), 400

    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    if not isinstance(password, str) or not isinstance(
        confirm_password, str
    ):
        return jsonify({
            "success": False,
            "message": "Invalid password reset details."
        }), 400

    if len(password) < 8:
        return jsonify({
            "success": False,
            "message": "Password must contain at least 8 characters."
        }), 400

    if password != confirm_password:
        return jsonify({
            "success": False,
            "message": "Passwords do not match."
        }), 400

    user_id = session.get("password_reset_verified_user_id")
    if not user_id:
        return jsonify({
            "success": False,
            "message": "Verify both codes before creating a new password."
        }), 400

    now = int(time.time())
    with get_connection() as conn:
        challenge = conn.execute(
            "SELECT expires_at, verified_at FROM password_reset_otps "
            "WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if (
            not challenge
            or challenge["verified_at"] is None
            or challenge["expires_at"] <= now
        ):
            conn.execute(
                "DELETE FROM password_reset_otps WHERE user_id = ?",
                (user_id,)
            )
            session.pop("password_reset_user_id", None)
            session.pop("password_reset_verified_user_id", None)
            return jsonify({
                "success": False,
                "message": "Verification expired. Request and verify new codes."
            }), 400

        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (generate_password_hash(password), user_id)
        )
        if cursor.rowcount != 1:
            return jsonify({
                "success": False,
                "message": "Farmer account could not be found."
            }), 404

        conn.execute(
            "DELETE FROM password_reset_otps WHERE user_id = ?",
            (user_id,)
        )

    session.pop("password_reset_user_id", None)
    session.pop("password_reset_verified_user_id", None)
    return jsonify({
        "success": True,
        "message": "New password created successfully. You can now log in."
    })


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
# LOGGED-IN FARMER PROFILE API
# --------------------------------------------------

@app.route("/api/profile")
def api_profile():
    # Check whether farmer is logged in
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    # Fetch only the logged-in farmer's profile
    with get_connection() as conn:
        farmer = conn.execute("""
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
                profile_picture
            FROM users
            WHERE user_id = ?
            LIMIT 1
        """, (user_id,)).fetchone()

    if not farmer:
        return jsonify({
            "success": False,
            "message": "Farmer profile not found."
        }), 404

    return jsonify({
        "success": True,
        "profile": {
            **dict(farmer),
            "profile_picture": (
                url_for(
                    "profile_picture",
                    filename=farmer["profile_picture"]
                )
                if farmer["profile_picture"]
                else None
            )
        }
    })


@app.route("/api/profile/picture/<filename>")
def profile_picture(filename):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    with get_connection() as conn:
        picture = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? AND profile_picture = ?",
            (user_id, filename)
        ).fetchone()

    if not picture:
        return jsonify({
            "success": False,
            "message": "Profile picture not found."
        }), 404

    response = send_from_directory(
        PROFILE_PICTURE_FOLDER,
        filename,
        mimetype="image/jpeg"
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/api/profile/picture", methods=["POST"])
def update_profile_picture():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    picture_data, picture_error = _process_profile_picture(
        request.files.get("profile_picture")
    )
    if picture_error:
        return jsonify({
            "success": False,
            "message": picture_error
        }), 400

    if picture_data is None:
        return jsonify({
            "success": False,
            "message": "Choose a profile picture to upload."
        }), 400

    try:
        new_filename = _save_profile_picture(picture_data)
    except OSError:
        app.logger.exception("Could not save updated profile picture.")
        return jsonify({
            "success": False,
            "message": "Could not save the profile picture. Please try again."
        }), 500

    with get_connection() as conn:
        farmer = conn.execute(
            "SELECT profile_picture FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not farmer:
            _delete_profile_picture(new_filename)
            return jsonify({
                "success": False,
                "message": "Farmer profile not found."
            }), 404

        old_filename = farmer["profile_picture"]
        conn.execute(
            "UPDATE users SET profile_picture = ? WHERE user_id = ?",
            (new_filename, user_id)
        )

    if old_filename != new_filename:
        _delete_profile_picture(old_filename)

    return jsonify({
        "success": True,
        "message": "Profile picture updated successfully.",
        "profile_picture": url_for(
            "profile_picture",
            filename=new_filename
        )
    })


# --------------------------------------------------
# LOGGED-IN FARMER WEATHER API
# --------------------------------------------------

@app.route("/api/my-weather")
def api_my_weather():

    # 1. Check whether the farmer is logged in
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    # 2. Get the farmer's saved GPS location
    with get_connection() as conn:
        farmer = conn.execute("""
            SELECT latitude, longitude
            FROM users
            WHERE user_id = ?
            LIMIT 1
        """, (user_id,)).fetchone()

    if not farmer:
        return jsonify({
            "success": False,
            "message": "Farmer profile not found."
        }), 404

    latitude = farmer["latitude"]
    longitude = farmer["longitude"]

    # 3. Check that GPS coordinates are available
    if latitude is None or longitude is None:
        return jsonify({
            "success": False,
            "message": "Farm GPS location is not saved."
        }), 400

    # 4. Fetch weather for the farmer's location
    weather_data = get_weather(latitude, longitude)

    if weather_data is None:
        return jsonify({
            "success": False,
            "message": "Weather service is temporarily unavailable."
        }), 502

    # 5. Return weather data
    return jsonify({
        "success": True,
        "weather": weather_data
    })
# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    # Debug mode is disabled to reduce information exposure.
    app.run(debug=False)