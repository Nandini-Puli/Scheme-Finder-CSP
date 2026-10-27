
import os
import re
from datetime import date

from flask import (
    Blueprint,
    request,
    jsonify,
    session,
    current_app,
    make_response,
)
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError

from app.database.connection import get_db_connection


admin_bp = Blueprint("admin", __name__)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

ALLOWED_STATES = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep",
    "Puducherry",
}


def close_database_resources(cursor=None, connection=None):
    """Close database resources without masking the original error."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception("Failed to close database cursor")

    if connection is not None:
        try:
            connection.close()
        except Exception:
            current_app.logger.exception("Failed to close database connection")


def is_admin_logged_in():
    """Return whether the current session belongs to an authenticated admin."""
    return bool(session.get("admin_id")) and session.get("role") == "admin"


def get_string(data, key, default=""):
    """Safely retrieve a string field from a JSON object."""
    value = data.get(key, default)
    return value.strip() if isinstance(value, str) else default


def prevent_caching(response):
    """Prevent sensitive authentication responses from being cached."""
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --------------------------------------------------
# Admin Registration
# --------------------------------------------------

@admin_bp.route("/api/admin/register", methods=["POST"])
def register_admin():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "Invalid request data."}), 400

    full_name = get_string(data, "full_name")
    date_of_birth = get_string(data, "date_of_birth")
    gender = get_string(data, "gender")
    state = get_string(data, "state")
    mobile_number = get_string(data, "mobile_number")
    email = get_string(data, "email").lower()
    username = get_string(data, "username")
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    invitation_code = get_string(data, "invitation_code")

    expected_code = os.getenv("ADMIN_INVITATION_CODE", "")

    # Validate required fields.
    if not all([
        full_name,
        date_of_birth,
        gender,
        state,
        mobile_number,
        email,
        username,
        password,
        confirm_password,
        invitation_code,
    ]):
        return jsonify({"message": "Please fill in all fields."}), 400

    if not isinstance(password, str) or not isinstance(confirm_password, str):
        return jsonify({"message": "Invalid password format."}), 400

    # Restrict admin registration.
    if not expected_code or invitation_code != expected_code:
        return jsonify({"message": "Invalid admin invitation code."}), 403

    if password != confirm_password:
        return jsonify({"message": "Passwords do not match."}), 400

    if len(password) < 8:
        return jsonify({
            "message": "Password must contain at least 8 characters."
        }), 400

    if not re.fullmatch(r"[0-9]{10}", mobile_number):
        return jsonify({
            "message": "Enter a valid 10-digit mobile number."
        }), 400

    try:
        dob = date.fromisoformat(date_of_birth)
    except ValueError:
        return jsonify({"message": "Invalid date of birth."}), 400

    if dob >= date.today():
        return jsonify({
            "message": "Date of birth must be in the past."
        }), 400

    if gender not in {"Male", "Female", "Other"}:
        return jsonify({"message": "Please select a valid gender."}), 400

    if state not in ALLOWED_STATES:
        return jsonify({"message": "Please select a valid state."}), 400

    if not re.fullmatch(r"[A-Za-z0-9_.]{3,50}", username):
        return jsonify({
            "message": (
                "Username must be 3-50 characters and use "
                "letters, numbers, dots, or underscores."
            )
        }), 400

    # Basic email format validation.
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"message": "Enter a valid email address."}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO admins (
                full_name,
                date_of_birth,
                gender,
                state,
                mobile_number,
                email,
                username,
                password_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                dob,
                gender,
                state,
                mobile_number,
                email,
                username,
                password_hash,
            ),
        )

        connection.commit()

        return jsonify({
            "message": "Admin account created successfully."
        }), 201

    except IntegrityError:
        if connection is not None:
            connection.rollback()

        return jsonify({
            "message": (
                "Email, mobile number, or username is already registered."
            )
        }), 409

    except Exception:
        if connection is not None:
            connection.rollback()

        current_app.logger.exception("Admin registration failed")

        return jsonify({
            "message": (
                "A server error occurred while creating the admin account."
            )
        }), 500

    finally:
        close_database_resources(cursor, connection)


# --------------------------------------------------
# Admin Login
# --------------------------------------------------

@admin_bp.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "Invalid request data."}), 400

    identifier = get_string(data, "identifier")
    password = data.get("password", "")

    if not identifier or not isinstance(password, str) or not password:
        return jsonify({
            "message": "Please enter your username/email and password."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Match username, email, or mobile number.
        # Lowercase the email-style identifier for case-insensitive matching
        # when the database column/collation does not already do this.
        email_identifier = identifier.lower()

        cursor.execute(
            """
            SELECT
                admin_id,
                full_name,
                username,
                email,
                mobile_number,
                password_hash
            FROM admins
            WHERE username = %s
               OR email = %s
               OR mobile_number = %s
            LIMIT 1
            """,
            (identifier, email_identifier, identifier),
        )

        admin = cursor.fetchone()

        if not admin or not check_password_hash(
            admin["password_hash"], password
        ):
            return jsonify({
                "message": "Invalid admin credentials."
            }), 401

        # Start a clean session after successful authentication.
        session.clear()
        session["admin_id"] = admin["admin_id"]
        session["admin_name"] = admin["full_name"]
        session["role"] = "admin"

        response = make_response(jsonify({
            "message": "Admin login successful.",
            "redirect": "admin_dashboard.html",
        }), 200)

        return prevent_caching(response)

    except Exception:
        current_app.logger.exception("Admin login failed")

        return jsonify({
            "message": "A server error occurred during admin login."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# --------------------------------------------------
# Admin Dashboard
# --------------------------------------------------

@admin_bp.route("/api/admin/dashboard", methods=["GET"])
def get_admin_dashboard():
    if not is_admin_logged_in():
        return jsonify({"message": "Please log in as admin."}), 401

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # 1. Logged-in admin's full name.
        cursor.execute(
            """
            SELECT full_name
            FROM admins
            WHERE admin_id = %s
            LIMIT 1
            """,
            (session["admin_id"],),
        )

        admin = cursor.fetchone()

        if not admin:
            session.clear()
            return jsonify({"message": "Admin account not found."}), 404

        # 2. Total schemes.
        cursor.execute(
            "SELECT COUNT(*) AS total FROM adminschemes"
        )
        total_schemes = cursor.fetchone()["total"]

        # 3. Total users.
        cursor.execute(
            "SELECT COUNT(*) AS total FROM users"
        )
        total_users = cursor.fetchone()["total"]

        # 4. Application count.
        #
        # This preserves your original data source. It counts rows in
        # admin_applynotifications, NOT necessarily unique applications.
        # If applied_schemes is your canonical applications table, replace
        # this query with:
        # SELECT COUNT(*) AS total FROM applied_schemes
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM admin_applynotifications
            """
        )
        total_applications = cursor.fetchone()["total"]

        # 5. Unread admin alerts from both existing admin alert tables.
        # This assumes both tables belong to one shared admin inbox.
        cursor.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM admin_applynotifications
                    WHERE COALESCE(is_read, 0) = 0
                )
                +
                (
                    SELECT COUNT(*)
                    FROM admin_newnotifications
                    WHERE COALESCE(is_read, 0) = 0
                ) AS unread
            """
        )
        unread_alerts = cursor.fetchone()["unread"]

        # 6. User category counts for the dashboard chart.
        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(category), ''), 'Others') AS category,
                COUNT(*) AS count
            FROM users
            GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'Others')
            ORDER BY count DESC
            """
        )
        category_counts = cursor.fetchall()

        # 7. Recent activity.
        #
        # IMPORTANT: This query assumes the referenced tables have the
        # columns used below. If any column is absent, update this query
        # to match your actual database schema.
        cursor.execute(
            """
            SELECT activity, details, created_at
            FROM (
                SELECT
                    'New user registered' AS activity,
                    CONCAT('User: ', full_name) AS details,
                    created_at
                FROM users

                UNION ALL

                SELECT
                    'New scheme added' AS activity,
                    scheme_name AS details,
                    created_at
                FROM adminschemes

                UNION ALL

                SELECT
                    'Application submitted' AS activity,
                    message AS details,
                    created_at
                FROM admin_applynotifications

                UNION ALL

                SELECT
                    'Alert sent' AS activity,
                    message AS details,
                    created_at
                FROM notifications
            ) AS activities
            ORDER BY created_at DESC
            LIMIT 8
            """
        )

        recent_activity = cursor.fetchall()

        # Convert date/time objects into JSON-serializable strings.
        for item in recent_activity:
            created_at = item.get("created_at")

            if created_at is not None:
                if hasattr(created_at, "isoformat"):
                    item["created_at"] = created_at.isoformat(
                        sep=" ",
                        timespec="seconds",
                    )
                else:
                    item["created_at"] = str(created_at)

        response = jsonify({
            "admin": {
                "full_name": admin["full_name"],
            },
            "stats": {
                "total_schemes": total_schemes,
                "total_users": total_users,
                "total_applications": total_applications,
                "active_alerts": unread_alerts,
            },
            "unread_alerts": unread_alerts,
            "category_counts": category_counts,
            "recent_activity": recent_activity,
        })

        return prevent_caching(response), 200

    except Exception:
        current_app.logger.exception("Failed to load admin dashboard")

        return jsonify({
            "message": (
                "Unable to load dashboard data. "
                "Check the Flask server log."
            )
        }), 500

    finally:
        close_database_resources(cursor, connection)


# --------------------------------------------------
# Admin Logout
# --------------------------------------------------

@admin_bp.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()

    response = make_response(jsonify({
        "success": True,
        "message": "Admin logged out successfully",
    }), 200)

    return prevent_caching(response)


# --------------------------------------------------
# Check Admin Session
# --------------------------------------------------

@admin_bp.route("/api/admin/session", methods=["GET"])
def check_admin_session():
    authenticated = is_admin_logged_in()

    response = make_response(jsonify({
        "success": authenticated,
        "authenticated": authenticated,
    }), 200 if authenticated else 401)

    return prevent_caching(response)
