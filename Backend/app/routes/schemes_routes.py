
from flask import (
    Blueprint,
    jsonify,
    session,
    current_app,
)

from app.database.connection import get_db_connection


# ==========================================================
# SCHEME MANAGEMENT BLUEPRINT
# ==========================================================

scheme_bp = Blueprint("scheme", __name__)


# ==========================================================
# AUTHENTICATION
# ==========================================================

def require_user():
    """Ensure the request belongs to an authenticated user."""
    if session.get("role") != "user" or not session.get("user_id"):
        return jsonify({
            "message": "Please log in as a user."
        }), 401

    return None


# ==========================================================
# DATE CONVERSION
# ==========================================================

def convert_dates(rows, fields):
    """Convert date/datetime objects to ISO strings for JSON."""
    for row in rows:
        for field in fields:
            value = row.get(field)

            if value is not None and hasattr(value, "isoformat"):
                row[field] = value.isoformat()

    return rows


# ==========================================================
# DATABASE CLEANUP
# ==========================================================

def close_database(connection, cursor):
    """Close cursor and connection safely."""
    if cursor:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database cursor"
            )

    if connection:
        try:
            if connection.is_connected():
                connection.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database connection"
            )


# ==========================================================
# GET ALL ACTIVE SCHEMES
# GET /api/schemes
# ==========================================================

@scheme_bp.route("/api/schemes", methods=["GET"])
def get_schemes():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                scheme_id,
                scheme_name,
                category,
                description,
                eligibility_criteria,
                benefits,
                required_documents,
                application_link,
                status,
                deadline
            FROM adminschemes
            WHERE status = 'Active'
            ORDER BY scheme_name ASC
        """)

        schemes = cursor.fetchall()

        convert_dates(schemes, ["deadline"])

        response = jsonify({
            "schemes": schemes
        })
        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception:
        current_app.logger.exception(
            "Failed to load schemes"
        )

        return jsonify({
            "message": "Unable to load schemes."
        }), 500

    finally:
        close_database(connection, cursor)


# ==========================================================
# GET ONE ACTIVE SCHEME
# GET /api/schemes/<scheme_id>
# ==========================================================

@scheme_bp.route(
    "/api/schemes/<int:scheme_id>",
    methods=["GET"]
)
def get_scheme_details(scheme_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                scheme_id,
                scheme_name,
                category,
                description,
                eligibility_criteria,
                benefits,
                required_documents,
                application_link,
                status,
                deadline
            FROM adminschemes
            WHERE scheme_id = %s
              AND status = 'Active'
            LIMIT 1
        """, (scheme_id,))

        scheme = cursor.fetchone()

        if not scheme:
            return jsonify({
                "message": "Scheme not found."
            }), 404

        convert_dates([scheme], ["deadline"])

        return jsonify(scheme), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load scheme details"
        )

        return jsonify({
            "message": "Unable to load scheme details."
        }), 500

    finally:
        close_database(connection, cursor)


# ==========================================================
# GET LOGGED-IN USER'S NAME
# GET /api/user/profileusername
# ==========================================================

@scheme_bp.route(
    "/api/user/profileusername",
    methods=["GET"]
)
def get_logged_in_user_profile():
    auth_error = require_user()

    if auth_error:
        return auth_error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT full_name
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """, (session["user_id"],))

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "message": "User profile not found."
            }), 404

        return jsonify({
            "user": {
                "full_name": user.get("full_name") or "User"
            }
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to retrieve user profile"
        )

        return jsonify({
            "message": "Unable to retrieve user profile."
        }), 500

    finally:
        close_database(connection, cursor)


# ==========================================================
# GET RECOMMENDED SCHEMES
# GET /api/user/recommended-schemes
# ==========================================================

@scheme_bp.route(
    "/api/user/recommended-schemes",
    methods=["GET"]
)
def get_recommended_schemes():
    auth_error = require_user()

    if auth_error:
        return auth_error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                scheme_id,
                scheme_name,
                category,
                description,
                eligibility_criteria,
                benefits,
                required_documents,
                application_link,
                deadline
            FROM adminschemes
            WHERE status = 'Active'
            ORDER BY scheme_name ASC
        """)

        schemes = cursor.fetchall()

        convert_dates(schemes, ["deadline"])

        response = jsonify({
            "success": True,
            "schemes": schemes
        })

        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception:
        current_app.logger.exception(
            "Failed to load recommended schemes"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load recommended schemes."
        }), 500

    finally:
        close_database(connection, cursor)
