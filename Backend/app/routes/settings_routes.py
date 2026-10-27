
from flask import Blueprint, jsonify, session, current_app

from app.database.connection import get_db_connection


# ==========================================================
# USER SETTINGS BLUEPRINT
# ==========================================================

settings_bp = Blueprint("settings", __name__)


# ==========================================================
# AUTHENTICATION
# ==========================================================

def require_user():
    if session.get("role") != "user" or not session.get("user_id"):
        return jsonify({
            "success": False,
            "message": "Please log in as a user."
        }), 401

    return None


# ==========================================================
# DATABASE CLEANUP
# ==========================================================

def close_database(conn, cursor):
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close settings database cursor"
            )

    if conn is not None:
        try:
            if conn.is_connected():
                conn.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close settings database connection"
            )


# ==========================================================
# GET USER SETTINGS PROFILE
# GET /api/user/settings/profile
# ==========================================================

@settings_bp.route(
    "/api/user/settings/profile",
    methods=["GET"]
)
def get_settings_profile():
    auth_error = require_user()

    if auth_error:
        return auth_error

    user_id = session["user_id"]

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get basic account information and optional profile information.
        cursor.execute(
            """
            SELECT
                u.full_name AS user_full_name,
                u.email AS user_email,
                u.mobile_number AS user_mobile_number,
                u.date_of_birth AS user_date_of_birth,
                u.category AS user_category,
                u.state AS user_state,
                p.full_name,
                p.category,
                p.state,
                p.email,
                p.mobile_number,
                p.date_of_birth
            FROM users u
            LEFT JOIN personal_info p
                ON p.user_id = u.user_id
            WHERE u.user_id = %s
            LIMIT 1
            """,
            (user_id,)
        )

        row = cursor.fetchone()

        if not row:
            return jsonify({
                "success": False,
                "message": "User profile not found."
            }), 404

        # Preserve the existing response keys and prefer personal_info.
        user = {
            "full_name": (
                row.get("full_name")
                or row.get("user_full_name")
            ),
            "category": (
                row.get("category")
                or row.get("user_category")
            ),
            "state": (
                row.get("state")
                or row.get("user_state")
            ),
            "email": (
                row.get("email")
                or row.get("user_email")
            ),
            "mobile_number": (
                row.get("mobile_number")
                or row.get("user_mobile_number")
            ),
            "date_of_birth": (
                row.get("date_of_birth")
                or row.get("user_date_of_birth")
            ),
        }

        # Convert date/datetime objects to JSON-safe strings.
        for key, value in user.items():
            if value is not None and hasattr(value, "isoformat"):
                user[key] = value.isoformat()

        response = jsonify({
            "success": True,
            "user": user
        })

        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception:
        current_app.logger.exception(
            "Failed to load settings profile"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load account settings."
        }), 500

    finally:
        close_database(conn, cursor)
