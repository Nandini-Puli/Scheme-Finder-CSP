from datetime import date
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, session, current_app

from app.database.connection import get_db_connection


# ==========================================================
# SCHEME MANAGEMENT BLUEPRINT
# ==========================================================

adminscheme_bp = Blueprint("adminscheme", __name__)


# ==========================================================
# DATABASE CLEANUP
# ==========================================================

def close_database_resources(cursor=None, connection=None):
    """Safely close database resources."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception("Failed to close database cursor")

    if connection is not None:
        try:
            connection.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database connection"
            )


# ==========================================================
# CHECK ADMIN LOGIN
# ==========================================================

def require_admin():
    if (
        not session.get("admin_id")
        or session.get("role") != "admin"
    ):
        return jsonify({
            "success": False,
            "message": "Please log in as an admin."
        }), 401

    return None


# ==========================================================
# SERIALIZE DATE VALUES
# ==========================================================

def serialize_scheme_dates(schemes):
    for scheme in schemes:
        for field in ("deadline", "created_at", "updated_at"):
            value = scheme.get(field)

            if value is not None and hasattr(value, "isoformat"):
                scheme[field] = value.isoformat()

    return schemes


# ==========================================================
# VALIDATE SCHEME DATA
# ==========================================================

def get_scheme_payload(data):
    scheme_name = str(data.get("scheme_name") or "").strip()
    category = str(data.get("category") or "").strip()
    description = str(data.get("description") or "").strip()

    eligibility = str(
        data.get("eligibility_criteria") or ""
    ).strip()

    benefits = str(data.get("benefits") or "").strip()

    required_documents = str(
        data.get("required_documents") or ""
    ).strip()

    application_link = str(
        data.get("application_link") or ""
    ).strip()

    status = str(data.get("status") or "Active").strip()
    deadline_value = str(data.get("deadline") or "").strip()

    if not scheme_name or not category or not description:
        return None, (
            "Scheme name, category, and description are required."
        )

    if len(scheme_name) > 200:
        return None, "Scheme name cannot exceed 200 characters."

    if len(category) > 100:
        return None, "Category cannot exceed 100 characters."

    if len(application_link) > 1000:
        return None, "Application link cannot exceed 1000 characters."

    if status not in {"Active", "Inactive"}:
        return None, "Status must be Active or Inactive."

    if application_link:
        parsed_url = urlparse(application_link)

        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or not parsed_url.hostname
        ):
            return None, (
                "Enter a valid application URL starting with "
                "http:// or https://."
            )

    deadline = None

    if deadline_value:
        try:
            deadline = date.fromisoformat(deadline_value)
        except ValueError:
            return None, (
                "Enter a valid deadline date in YYYY-MM-DD format."
            )

    scheme = {
        "scheme_name": scheme_name,
        "category": category,
        "description": description,
        "eligibility_criteria": eligibility or None,
        "benefits": benefits or None,
        "required_documents": required_documents or None,
        "application_link": application_link or None,
        "status": status,
        "deadline": deadline,
    }

    return scheme, None


# ==========================================================
# GET ALL SCHEMES FOR ADMIN
# GET /api/admin/schemes
# ==========================================================

@adminscheme_bp.route("/api/admin/schemes", methods=["GET"])
def get_admin_schemes():
    auth_error = require_admin()

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
                status,
                deadline,
                created_at,
                updated_at
            FROM adminschemes
            ORDER BY updated_at DESC, scheme_id DESC
        """)

        schemes = serialize_scheme_dates(cursor.fetchall())

        return jsonify({
            "success": True,
            "schemes": schemes,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to retrieve admin schemes"
        )

        return jsonify({
            "success": False,
            "message": "Unable to retrieve schemes from the database."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# GET ACTIVE SCHEMES FOR PUBLIC SEARCH
# GET /api/schemes
# NO ADMIN LOGIN REQUIRED
# ==========================================================

@adminscheme_bp.route("/api/schemes", methods=["GET"])
def get_schemes_for_search():
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

        schemes = serialize_scheme_dates(cursor.fetchall())

        return jsonify({
            "success": True,
            "schemes": schemes,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to retrieve public schemes"
        )

        return jsonify({
            "success": False,
            "message": "Unable to retrieve schemes."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# ADD NEW SCHEME
# POST /api/admin/schemes
# ==========================================================

@adminscheme_bp.route("/api/admin/schemes", methods=["POST"])
def add_admin_scheme():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Please submit scheme details as JSON."
        }), 400

    scheme, error = get_scheme_payload(data)

    if error:
        return jsonify({
            "success": False,
            "message": error,
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO adminschemes (
                scheme_name,
                category,
                description,
                eligibility_criteria,
                benefits,
                required_documents,
                application_link,
                status,
                deadline
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            scheme["scheme_name"],
            scheme["category"],
            scheme["description"],
            scheme["eligibility_criteria"],
            scheme["benefits"],
            scheme["required_documents"],
            scheme["application_link"],
            scheme["status"],
            scheme["deadline"],
        ))

        scheme_id = cursor.lastrowid
        connection.commit()

        return jsonify({
            "success": True,
            "message": "Scheme added successfully.",
            "scheme_id": scheme_id,
        }), 201

    except Exception:
        if connection is not None:
            connection.rollback()

        current_app.logger.exception(
            "Failed to insert scheme"
        )

        return jsonify({
            "success": False,
            "message": "Unable to save the scheme. Please try again."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# TOTAL SCHEME VIEWS
# GET /api/admin/reports/scheme-views
# ==========================================================

@adminscheme_bp.route(
    "/api/admin/reports/scheme-views",
    methods=["GET"]
)
def admin_scheme_view_report():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT COUNT(*) AS total_views
            FROM viewed_schemes
        """)

        stats = cursor.fetchone()

        return jsonify({
            "success": True,
            "total_views": stats["total_views"] or 0,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load total scheme views"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load scheme-view count."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# APPLICATION STATISTICS
# GET /api/admin/apply-clicks/summary
# ==========================================================

@adminscheme_bp.route(
    "/api/admin/apply-clicks/summary",
    methods=["GET"]
)
def admin_apply_clicks_summary():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(*) AS total_clicks,
                COUNT(DISTINCT user_id) AS total_users,
                COUNT(DISTINCT scheme_id) AS different_schemes
            FROM applied_schemes
        """)

        stats = cursor.fetchone()

        return jsonify({
            "success": True,
            "total_clicks": stats["total_clicks"] or 0,
            "total_users": stats["total_users"] or 0,
            "different_schemes": stats["different_schemes"] or 0,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load application statistics"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load admin statistics."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# UPDATE SCHEME STATUS
# PUT /api/admin/schemes/<scheme_id>
# ==========================================================

@adminscheme_bp.route(
    "/api/admin/schemes/<int:scheme_id>",
    methods=["PUT"]
)
def update_admin_scheme(scheme_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Please submit the updated status as JSON."
        }), 400

    status = str(data.get("status") or "").strip()

    if status not in {"Active", "Inactive"}:
        return jsonify({
            "success": False,
            "message": "Status must be Active or Inactive."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE adminschemes
            SET status = %s
            WHERE scheme_id = %s
        """, (status, scheme_id))

        if cursor.rowcount == 0:
            # A zero rowcount may mean the scheme doesn't exist,
            # or that the status was already the requested value.
            cursor.execute("""
                SELECT scheme_id, status
                FROM adminschemes
                WHERE scheme_id = %s
            """, (scheme_id,))

            existing_scheme = cursor.fetchone()

            if not existing_scheme:
                connection.rollback()

                return jsonify({
                    "success": False,
                    "message": "Scheme not found."
                }), 404

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Scheme status updated successfully.",
            "scheme_id": scheme_id,
            "status": status,
        }), 200

    except Exception:
        if connection is not None:
            connection.rollback()

        current_app.logger.exception(
            "Failed to update scheme status"
        )

        return jsonify({
            "success": False,
            "message": "Unable to update scheme status."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# PERMANENTLY DELETE SCHEME
# DELETE /api/admin/schemes/<scheme_id>
# ==========================================================

@adminscheme_bp.route(
    "/api/admin/schemes/<int:scheme_id>",
    methods=["DELETE"]
)
def delete_admin_scheme(scheme_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM adminschemes
            WHERE scheme_id = %s
        """, (scheme_id,))

        if cursor.rowcount == 0:
            connection.rollback()

            return jsonify({
                "success": False,
                "message": "Scheme not found."
            }), 404

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Scheme permanently deleted.",
            "scheme_id": scheme_id,
        }), 200

    except Exception:
        if connection is not None:
            connection.rollback()

        current_app.logger.exception(
            "Failed to permanently delete scheme"
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to delete the scheme. It may be referenced "
                "by related records in the database."
            )
        }), 500

    finally:
        close_database_resources(cursor, connection)


# ==========================================================
# ADMIN HEADER DETAILS
# GET /api/admin/header
# ==========================================================

@adminscheme_bp.route("/api/admin/header", methods=["GET"])
def get_admin_header():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    admin_id = session.get("admin_id")

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT full_name
            FROM admins
            WHERE admin_id = %s
            LIMIT 1
        """, (admin_id,))

        admin = cursor.fetchone()

        if not admin:
            return jsonify({
                "success": False,
                "message": "Admin account not found."
            }), 404

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

        result = cursor.fetchone()
        unread_count = int(result["unread_notifications"] or 0)

        return jsonify({
            "success": True,
            "full_name": admin["full_name"],
            "unread_notifications": unread_count,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin header details"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load admin header details."
        }), 500

    finally:
        close_database_resources(cursor, connection)
