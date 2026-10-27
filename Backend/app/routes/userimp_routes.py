
from flask import Blueprint, request, jsonify, session, current_app

from app.database.connection import get_db_connection


# ==========================================================
# SCHEME MANAGEMENT BLUEPRINT
# ==========================================================

userimp_bp = Blueprint("userimp", __name__)


def require_user():
    if not session.get("user_id") or session.get("role") != "user":
        return jsonify({
            "message": "Please log in as a user."
        }), 401

    return None


# ==========================================================
# CONVERT DATES FOR JSON
# ==========================================================

def convert_dates(rows, fields):
    for row in rows:
        for field in fields:
            value = row.get(field)
            if value is not None and hasattr(value, "isoformat"):
                row[field] = value.isoformat()
    return rows


# ==========================================================
# SAVE A SCHEME
# POST /api/saved-schemes
# ==========================================================

@userimp_bp.route("/api/saved-schemes", methods=["POST"])
def save_scheme():
    auth_error = require_user()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    scheme_id = data.get("scheme_id")

    try:
        if isinstance(scheme_id, bool):
            raise ValueError

        scheme_id = int(scheme_id)

        if scheme_id <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "message": "A valid scheme ID is required."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT scheme_id
            FROM adminschemes
            WHERE scheme_id = %s
              AND status = 'Active'
            LIMIT 1
        """, (scheme_id,))

        if not cursor.fetchone():
            return jsonify({
                "message": "Active scheme not found."
            }), 404

        # The unique (user_id, scheme_id) index is the final
        # protection against duplicate saves.
        cursor.execute("""
            SELECT saved_id
            FROM saved_schemes
            WHERE user_id = %s
              AND scheme_id = %s
            LIMIT 1
        """, (session["user_id"], scheme_id))

        if cursor.fetchone():
            return jsonify({
                "message": "This scheme is already saved."
            }), 200

        cursor.execute("""
            INSERT INTO saved_schemes (user_id, scheme_id)
            VALUES (%s, %s)
        """, (session["user_id"], scheme_id))

        connection.commit()

        return jsonify({
            "message": "Scheme saved successfully.",
            "scheme_id": scheme_id
        }), 201

    except Exception:
        if connection:
            connection.rollback()

        current_app.logger.exception("Failed to save scheme")

        return jsonify({
            "message": "Unable to save scheme."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# GET SAVED SCHEMES
# GET /api/saved-schemes
# ==========================================================

@userimp_bp.route("/api/saved-schemes", methods=["GET"])
def get_saved_schemes():
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
                ss.saved_id,
                ss.user_id,
                ss.scheme_id,
                ss.saved_at,
                a.scheme_name,
                a.category,
                a.description,
                a.eligibility_criteria,
                a.benefits,
                a.required_documents,
                a.application_link,
                a.status,
                a.deadline
            FROM saved_schemes AS ss
            INNER JOIN adminschemes AS a
                ON a.scheme_id = ss.scheme_id
            WHERE ss.user_id = %s
            ORDER BY ss.saved_at DESC
        """, (session["user_id"],))

        schemes = cursor.fetchall()
        convert_dates(schemes, ["saved_at", "deadline"])

        return jsonify({
            "schemes": schemes
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to retrieve saved schemes"
        )

        return jsonify({
            "message": "Unable to load saved schemes."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# REMOVE A SAVED SCHEME
# DELETE /api/saved-schemes/<scheme_id>
# ==========================================================

@userimp_bp.route(
    "/api/saved-schemes/<int:scheme_id>",
    methods=["DELETE"]
)
def remove_saved_scheme(scheme_id):
    auth_error = require_user()
    if auth_error:
        return auth_error

    if scheme_id <= 0:
        return jsonify({
            "message": "A valid scheme ID is required."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM saved_schemes
            WHERE user_id = %s
              AND scheme_id = %s
        """, (session["user_id"], scheme_id))

        deleted = cursor.rowcount

        if deleted == 0:
            connection.rollback()
            return jsonify({
                "message": "Saved scheme not found."
            }), 404

        connection.commit()

        return jsonify({
            "message": "Scheme removed successfully."
        }), 200

    except Exception:
        if connection:
            connection.rollback()

        current_app.logger.exception(
            "Failed to remove saved scheme"
        )

        return jsonify({
            "message": "Failed to remove saved scheme."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# USER VIEWED-SCHEMES SUMMARY
# GET /api/user/viewed-schemes/summary
# ==========================================================

@userimp_bp.route(
    "/api/user/viewed-schemes/summary",
    methods=["GET"]
)
def user_viewed_schemes_summary():
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
                COUNT(*) AS total_views,
                COUNT(DISTINCT scheme_id) AS unique_schemes_viewed
            FROM viewed_schemes
            WHERE user_id = %s
        """, (session["user_id"],))

        stats = cursor.fetchone() or {}

        return jsonify({
            "success": True,
            "total_views": stats.get("total_views") or 0,
            "unique_schemes_viewed":
                stats.get("unique_schemes_viewed") or 0
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load user scheme-view statistics"
        )

        return jsonify({
            "message": "Unable to load viewing statistics."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# RECORD A SCHEME VIEW
# POST /api/schemes/<scheme_id>/view
# ==========================================================

@userimp_bp.route(
    "/api/schemes/<int:scheme_id>/view",
    methods=["POST"]
)
def record_scheme_view(scheme_id):
    auth_error = require_user()
    if auth_error:
        return auth_error

    if scheme_id <= 0:
        return jsonify({
            "message": "A valid scheme ID is required."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT scheme_id
            FROM adminschemes
            WHERE scheme_id = %s
              AND status = 'Active'
            LIMIT 1
        """, (scheme_id,))

        if not cursor.fetchone():
            return jsonify({
                "message": "Active scheme not found."
            }), 404

        cursor.execute("""
            INSERT INTO viewed_schemes (user_id, scheme_id)
            VALUES (%s, %s)
        """, (session["user_id"], scheme_id))

        cursor.execute("""
            SELECT COUNT(*) AS view_count
            FROM viewed_schemes
            WHERE scheme_id = %s
        """, (scheme_id,))

        result = cursor.fetchone() or {}

        connection.commit()

        return jsonify({
            "message": "Scheme view recorded.",
            "scheme_id": scheme_id,
            "view_count": result.get("view_count") or 0
        }), 200

    except Exception:
        if connection:
            connection.rollback()

        current_app.logger.exception(
            "Failed to record scheme view"
        )

        return jsonify({
            "message": "Unable to record scheme view."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# RECORD APPLY-NOW CLICK
# POST /api/schemes/<scheme_id>/apply-click
# ==========================================================

@userimp_bp.route(
    "/api/schemes/<int:scheme_id>/apply-click",
    methods=["POST"]
)
def record_apply_click(scheme_id):
    auth_error = require_user()
    if auth_error:
        return auth_error

    if scheme_id <= 0:
        return jsonify({
            "success": False,
            "message": "A valid scheme ID is required."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT scheme_id, scheme_name
            FROM adminschemes
            WHERE scheme_id = %s
              AND status = 'Active'
            LIMIT 1
        """, (scheme_id,))

        scheme = cursor.fetchone()

        if not scheme:
            return jsonify({
                "success": False,
                "message": "This scheme is unavailable."
            }), 404

        user_id = session["user_id"]

        # FIX: documents_count has a placeholder, so supply 0.
        # This preserves the current behavior of recording clicks
        # in applied_schemes. It does not prove an external
        # application was actually submitted.
        cursor.execute("""
            INSERT INTO applied_schemes
                (user_id, scheme_id, status, documents_count)
            VALUES (%s, %s, 'Pending', %s)
        """, (user_id, scheme_id, 0))

        message = (
            f"User ID {user_id} clicked Apply Now for "
            f"'{scheme['scheme_name']}'."
        )

        cursor.execute("""
            INSERT INTO admin_applynotifications
                (user_id, scheme_id, message, notification_type)
            VALUES (%s, %s, %s, 'apply_click')
        """, (user_id, scheme_id, message))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Apply Now click recorded.",
            "scheme_id": scheme_id
        }), 200

    except Exception:
        if connection:
            connection.rollback()

        current_app.logger.exception(
            "Failed to record Apply Now click"
        )

        return jsonify({
            "success": False,
            "message": "Unable to record the Apply Now click."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# ==========================================================
# APPLY-NOW SUMMARY
# GET /api/user/apply-clicks/summary
# ==========================================================

@userimp_bp.route(
    "/api/user/apply-clicks/summary",
    methods=["GET"]
)
def user_apply_clicks_summary():
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
                COUNT(DISTINCT scheme_id) AS unique_schemes,
                COUNT(*) AS total_clicks
            FROM applied_schemes
            WHERE user_id = %s
        """, (session["user_id"],))

        stats = cursor.fetchone() or {}

        return jsonify({
            "success": True,
            "unique_schemes": stats.get("unique_schemes") or 0,
            "total_clicks": stats.get("total_clicks") or 0
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load Apply Now summary"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load Apply Now statistics."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
