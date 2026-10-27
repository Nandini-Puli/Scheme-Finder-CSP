
from flask import Blueprint, jsonify, session, current_app
from app.database.connection import get_db_connection


adminusers_bp = Blueprint("adminusers", __name__)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def require_admin():
    """Ensure that the request belongs to an authenticated admin."""
    if not session.get("admin_id") or session.get("role") != "admin":
        return jsonify({
            "success": False,
            "message": "Admin login required."
        }), 401

    return None


def close_database_resources(cursor=None, conn=None):
    """Safely close database resources."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close admin users cursor"
            )

    if conn is not None:
        try:
            conn.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close admin users database connection"
            )


def serialize_datetime_values(records):
    """Convert date, datetime, and similar values into JSON-safe strings."""
    for record in records:
        for key, value in record.items():
            if hasattr(value, "isoformat"):
                record[key] = value.isoformat()

    return records


# --------------------------------------------------
# Get All Users
# --------------------------------------------------

@adminusers_bp.route("/api/admin/users", methods=["GET"])
def get_admin_users():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Retrieve user details and user activity counts.
        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.mobile_number,
                u.category,
                u.state,
                u.gender,
                u.date_of_birth,
                u.created_at,

                (
                    SELECT COUNT(DISTINCT v.scheme_id)
                    FROM viewed_schemes v
                    WHERE v.user_id = u.user_id
                ) AS schemes_viewed,

                (
                    SELECT COUNT(*)
                    FROM applied_schemes a
                    WHERE a.user_id = u.user_id
                ) AS applications

            FROM users u
            ORDER BY u.user_id DESC
        """)

        users = cursor.fetchall()
        users = serialize_datetime_values(users)

        # Actual login/session activity is not tracked by this endpoint.
        # Keep the existing response field for frontend compatibility.
        for user in users:
            user["status"] = "Inactive"

        # Total registered users.
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM users
        """)

        total_users = cursor.fetchone()["total"]

        # Unread notifications across the two admin notification tables.
        # This assumes both tables belong to a shared admin inbox.
        cursor.execute("""
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
                ) AS unread_notifications
        """)

        unread = cursor.fetchone()["unread_notifications"]

        response = jsonify({
            "success": True,
            "admin_name": session.get("admin_name", "Admin"),
            "total_users": total_users,

            # These values are placeholders until real user-session
            # tracking is implemented.
            "active_users": 0,
            "inactive_users": total_users,

            "unread_notifications": unread,
            "users": users
        })

        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin users"
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to load users. Check the Flask server log "
                "and database columns."
            )
        }), 500

    finally:
        close_database_resources(cursor, conn)


# --------------------------------------------------
# Delete a User
# --------------------------------------------------

@adminusers_bp.route(
    "/api/admin/users/<int:user_id>",
    methods=["DELETE"]
)
def delete_admin_user(user_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete only the selected user.
        cursor.execute(
            """
            DELETE FROM users
            WHERE user_id = %s
            """,
            (user_id,)
        )

        if cursor.rowcount == 0:
            conn.rollback()

            return jsonify({
                "success": False,
                "message": "User not found."
            }), 404

        conn.commit()

        return jsonify({
            "success": True,
            "message": "User deleted successfully."
        }), 200

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Rollback failed after user deletion error"
                )

        current_app.logger.exception(
            "Failed to delete user with ID %s",
            user_id
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to delete user. Related records may prevent "
                "deletion. Check the Flask server log and foreign-key "
                "constraints."
            )
        }), 500

    finally:
        close_database_resources(cursor, conn)