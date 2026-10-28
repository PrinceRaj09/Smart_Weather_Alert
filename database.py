
import sqlite3
from werkzeug.security import generate_password_hash

DATABASE_NAME = "weather_alert.db"


def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        # Create the users table if it does not exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                latitude REAL,
                longitude REAL,
                otp_verified INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check existing columns for backward compatibility
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        # Add missing columns without deleting existing data
        new_columns = {
            "email": "TEXT",
            "user_id": "TEXT",
            "password_hash": "TEXT",
            "state": "TEXT",
            "district": "TEXT",
            "village": "TEXT",
            "pin_code": "TEXT",
            "farming_type": "TEXT",
            "farm_size": "REAL",
            "crops": "TEXT",
            "profile_picture": "TEXT"
        }

        for name, data_type in new_columns.items():
            if name not in columns:
                conn.execute(
                    f"ALTER TABLE users ADD COLUMN {name} {data_type}"
                )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_otps (
                user_id TEXT PRIMARY KEY,
                sms_otp_hash TEXT NOT NULL,
                email_otp_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                verified_at INTEGER
            )
        """)
        otp_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(password_reset_otps)"
            ).fetchall()
        }
        if "verified_at" not in otp_columns:
            conn.execute(
                "ALTER TABLE password_reset_otps ADD COLUMN verified_at INTEGER"
            )

        # Assign IDs to older users that do not have a User ID
        old_users = conn.execute("""
            SELECT id FROM users
            WHERE user_id IS NULL OR user_id = ''
        """).fetchall()

        for user in old_users:
            conn.execute(
                "UPDATE users SET user_id = ? WHERE id = ?",
                (f"FARM{user['id']:05d}", user["id"])
            )

        # Make User IDs unique
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_user_id
            ON users(user_id)
        """)

        # Make non-empty email addresses unique
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
            WHERE email IS NOT NULL AND email != ''
        """)

    print("Database initialized successfully!")


def register_user(data):
    # Read registration details safely
    full_name = data.get("full_name", "")
    phone = data.get("phone", "")
    email = data.get("email", "")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    # Validate basic text fields
    if not all(isinstance(value, str) for value in
               [full_name, phone, email, password, confirm_password]):
        return False, "Invalid registration details.", None

    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()

    if not full_name or len(full_name) > 100:
        return False, "Please enter a valid full name.", None

    if not phone.isdigit() or len(phone) != 10:
        return False, "Enter a valid 10-digit mobile number.", None

    if not email:
        return False, "Email address is required.", None

    if len(password) < 8:
        return False, "Password must contain at least 8 characters.", None

    if password != confirm_password:
        return False, "Passwords do not match.", None

    # Validate GPS coordinates
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))

        if not (-90 <= latitude <= 90):
            return False, "Invalid latitude. Detect your location again.", None

        if not (-180 <= longitude <= 180):
            return False, "Invalid longitude. Detect your location again.", None

    except (TypeError, ValueError):
        return False, "Please detect a valid GPS location first.", None

    # Validate required farming and address details
    required_fields = [
        "state",
        "district",
        "village",
        "pin_code",
        "farming_type",
        "farm_size",
        "crops"
    ]

    for field in required_fields:
        value = data.get(field)

        if value is None or not str(value).strip():
            return False, f"{field.replace('_', ' ').title()} is required.", None

    pin_code = str(data.get("pin_code", "")).strip()

    if not pin_code.isdigit() or len(pin_code) != 6:
        return False, "Enter a valid 6-digit PIN code.", None

    try:
        farm_size = float(data["farm_size"])

        if farm_size <= 0:
            return False, "Farm size must be greater than zero.", None

    except (TypeError, ValueError):
        return False, "Farm size must be a valid number.", None

    try:
        with get_connection() as conn:
            # Check duplicate mobile number or email
            existing = conn.execute("""
                SELECT id FROM users
                WHERE phone = ?
                   OR lower(email) = lower(?)
            """, (phone, email)).fetchone()

            if existing:
                return (
                    False,
                    "Mobile number or email is already registered.",
                    None
                )

            # Hash the password before storing it
            password_hash = generate_password_hash(password)

            # Save registration details and GPS coordinates
            cursor = conn.execute("""
                INSERT INTO users (
                    full_name,
                    phone,
                    email,
                    password_hash,
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
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                full_name,
                phone,
                email,
                password_hash,
                str(data["state"]).strip(),
                str(data["district"]).strip(),
                str(data["village"]).strip(),
                pin_code,
                str(data["farming_type"]).strip(),
                farm_size,
                str(data["crops"]).strip(),
                latitude,
                longitude,
                data.get("profile_picture")
            ))

            # Generate a unique User ID
            user_id = f"FARM{cursor.lastrowid:05d}"

            conn.execute(
                "UPDATE users SET user_id = ? WHERE id = ?",
                (user_id, cursor.lastrowid)
            )

        return True, "Registration successful!", user_id

    except sqlite3.IntegrityError:
        return (
            False,
            "Mobile number or email is already registered.",
            None
        )
    except sqlite3.Error:
        return False, "A database error occurred. Please try again.", None


def get_user(phone):
    with get_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE phone = ?",
            (phone,)
        ).fetchone()

        return dict(user) if user else None


def get_user_by_identifier(identifier):
    identifier = identifier.strip()

    with get_connection() as conn:
        user = conn.execute("""
            SELECT * FROM users
            WHERE phone = ?
               OR lower(email) = lower(?)
               OR lower(user_id) = lower(?)
            LIMIT 1
        """, (identifier, identifier, identifier)).fetchone()

        return dict(user) if user else None


def update_location(phone, latitude, longitude):
    # Validate coordinates before updating an existing user
    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90):
            return False

        if not (-180 <= longitude <= 180):
            return False

    except (TypeError, ValueError):
        return False

    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE users
            SET latitude = ?, longitude = ?
            WHERE phone = ?
        """, (latitude, longitude, phone))

        return cursor.rowcount > 0


# Initialize database and add any missing columns
init_db()


if __name__ == "__main__":
    print("Database is ready.")
