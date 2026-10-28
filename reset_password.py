
import getpass
from werkzeug.security import generate_password_hash
from database import get_connection

print("\n--- Farmer Password Reset ---")

user_id = input("Enter your Farmer ID: ").strip().upper()

password = getpass.getpass("Enter your new password: ")
confirm_password = getpass.getpass("Confirm your new password: ")

if len(password) < 8:
    print("Error: Password must contain at least 8 characters.")

elif password != confirm_password:
    print("Error: Passwords do not match.")

else:
    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, user_id FROM users WHERE upper(user_id) = ?",
            (user_id,)
        ).fetchone()

        if user is None:
            print("Error: Farmer ID not found.")

        else:
            password_hash = generate_password_hash(password)

            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user["id"])
            )

            print("\nPassword reset successful!")
            print("Farmer ID:", user["user_id"])
            print("You can now log in with your new password.")
