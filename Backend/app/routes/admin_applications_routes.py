
from flask import Blueprint, jsonify, request, session, current_app

from app.database.connection import get_db_connection


adminapplications_bp = Blueprint(
    "adminapplications",
    __name__
)


# ==========================================================
# ADMIN AUTHENTICATION
# ==========================================================

def require_admin():
    if (
        not session.get("admin_id")
        or session.get("role") != "admin"
    ):
        return jsonify({
            "success": False,
            "message": "Admin login required."
        }), 401

    return None


# ==========================================================
# DATABASE CLEANUP
# ==========================================================

def close_database_resources(cursor=None, conn=None):
    """Close cursor and connection without masking route errors."""

    if cursor:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database cursor"
            )

    if conn:
        try:
            conn.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database connection"
            )


# ==========================================================
# GET APPLICATIONS AND SUMMARY COUNTS
# ==========================================================

@adminapplications_bp.route(
    "/api/admin/applications",
    methods=["GET"]
)
def get_admin_applications():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                a.apply_id,
                a.user_id,
                u.full_name,
                a.scheme_id,
                s.scheme_name,
                a.applied_at,
                (
                    SELECT COUNT(*)
                    FROM user_documents d
                    WHERE d.user_id = a.user_id
                ) AS documents_count,
                a.status,
                a.rejection_reason
            FROM applied_schemes a
            JOIN users u
                ON u.user_id = a.user_id
            JOIN adminschemes s
                ON s.scheme_id = a.scheme_id
            ORDER BY
                a.applied_at DESC,
                a.apply_id DESC
        """)

        applications = cursor.fetchall()

        for item in applications:
            applied_at = item.get("applied_at")

            if hasattr(applied_at, "isoformat"):
                item["applied_at"] = applied_at.isoformat()

            item["documents_count"] = int(
                item.get("documents_count") or 0
            )

        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(
                    SUM(status = 'Pending'), 0
                ) AS pending,
                COALESCE(
                    SUM(status = 'Approved'), 0
                ) AS approved,
                COALESCE(
                    SUM(status = 'Rejected'), 0
                ) AS rejected
            FROM applied_schemes
        """)

        counts = cursor.fetchone() or {}

        return jsonify({
            "success": True,
            "total_applications": int(counts.get("total") or 0),
            "pending": int(counts.get("pending") or 0),
            "approved": int(counts.get("approved") or 0),
            "rejected": int(counts.get("rejected") or 0),
            "applications": applications
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin applications"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load applications."
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# APPROVE OR REJECT APPLICATION
# ==========================================================

@adminapplications_bp.route(
    "/api/admin/applications/<int:apply_id>/status",
    methods=["PUT"]
)
def update_application_status(apply_id):
    auth_error = require_admin()

    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}

    status = str(
        payload.get("status", "")
    ).strip()

    reason = str(
        payload.get("rejection_reason", "")
    ).strip()

    if status not in ("Approved", "Rejected"):
        return jsonify({
            "success": False,
            "message": "Invalid application status."
        }), 400

    if status == "Rejected" and not reason:
        return jsonify({
            "success": False,
            "message": "Please enter a rejection reason."
        }), 400

    if len(reason) > 4000:
        return jsonify({
            "success": False,
            "message": "The rejection reason is too long."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Lock this application row while changing its status.
        cursor.execute("""
            SELECT
                a.apply_id,
                a.user_id,
                a.status,
                s.scheme_name
            FROM applied_schemes a
            JOIN adminschemes s
                ON s.scheme_id = a.scheme_id
            WHERE a.apply_id = %s
            LIMIT 1
            FOR UPDATE
        """, (apply_id,))

        application = cursor.fetchone()

        if not application:
            conn.rollback()

            return jsonify({
                "success": False,
                "message": "Application not found."
            }), 404

        current_status = application.get("status")

        # Prevent repeated actions for an unchanged status.
        if current_status == status:
            conn.rollback()

            return jsonify({
                "success": False,
                "message": (
                    f"This application is already "
                    f"{status.lower()}."
                )
            }), 409

        user_id = application["user_id"]
        scheme_name = application["scheme_name"]

        # Update the application status.
        cursor.execute("""
            UPDATE applied_schemes
            SET
                status = %s,
                rejection_reason = %s
            WHERE apply_id = %s
        """, (
            status,
            reason if status == "Rejected" else None,
            apply_id
        ))

        # Notify the applicant only when the application is rejected.
        if status == "Rejected":
            notification_title = (
                f"Application Rejected: {scheme_name}"
            )

            notification_message = (
                f"Your application for '{scheme_name}' "
                f"has been rejected. "
                f"Reason: {reason}"
            )

            cursor.execute("""
                INSERT INTO notifications (
                    user_id,
                    title,
                    message,
                    notification_type
                )
                VALUES (%s, %s, %s, %s)
            """, (
                user_id,
                notification_title,
                notification_message,
                "application_rejected"
            ))

        conn.commit()

        return jsonify({
            "success": True,
            "message": (
                f"Application {status.lower()} successfully."
            ),
            "apply_id": apply_id,
            "status": status
        }), 200

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Failed to roll back application update"
                )

        current_app.logger.exception(
            "Failed to update application status"
        )

        return jsonify({
            "success": False,
            "message": "Unable to update application status."
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# ADMIN DASHBOARD ANALYTICS
# ==========================================================

@adminapplications_bp.route(
    "/api/admin/dashboard-analytics",
    methods=["GET"]
)
def get_admin_dashboard_analytics():
    auth_error = require_admin()

    if auth_error:
        return auth_error

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --------------------------------------------------
        # 1. Admin full name
        # --------------------------------------------------

        admin_id = session.get("admin_id")
        admin_name = session.get("admin_name", "Admin")

        if admin_id is not None:
            cursor.execute("""
                SELECT full_name
                FROM admins
                WHERE admin_id = %s
                LIMIT 1
            """, (admin_id,))

            admin = cursor.fetchone()

            if admin and admin.get("full_name"):
                admin_name = admin["full_name"]

        # --------------------------------------------------
        # 2. Total registered users
        # --------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*) AS total_users
            FROM users
        """)

        row = cursor.fetchone() or {}

        total_users = int(
            row.get("total_users") or 0
        )

        # --------------------------------------------------
        # 3. Total applications
        # --------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*) AS total_applications
            FROM applied_schemes
        """)

        row = cursor.fetchone() or {}

        total_applications = int(
            row.get("total_applications") or 0
        )

        # --------------------------------------------------
        # 4. Unique user-scheme views
        # --------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*) AS total_views
            FROM (
                SELECT DISTINCT user_id, scheme_id
                FROM viewed_schemes
            ) AS unique_views
        """)

        row = cursor.fetchone() or {}

        total_views = int(
            row.get("total_views") or 0
        )

        # --------------------------------------------------
        # 5. Unread admin notifications
        # --------------------------------------------------
        # This assumes admin notifications are shared by all
        # administrators. If they are per-admin, filter by
        # the relevant admin ID in both subqueries.

        cursor.execute("""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM admin_applynotifications
                    WHERE is_read = 0
                )
                +
                (
                    SELECT COUNT(*)
                    FROM admin_newnotifications
                    WHERE is_read = 0
                ) AS unread_notifications
        """)

        row = cursor.fetchone() or {}

        unread_notifications = int(
            row.get("unread_notifications") or 0
        )

        # --------------------------------------------------
        # 6. Applications by user category
        # --------------------------------------------------
        # Confirm users.category exists in your database.
        # If your schema uses occupation instead, replace
        # u.category with u.occupation in this query.

        cursor.execute("""
            SELECT
                COALESCE(
                    NULLIF(TRIM(u.category), ''),
                    'Uncategorized'
                ) AS category,
                COUNT(*) AS applications
            FROM applied_schemes a
            INNER JOIN users u
                ON u.user_id = a.user_id
            GROUP BY
                COALESCE(
                    NULLIF(TRIM(u.category), ''),
                    'Uncategorized'
                )
            ORDER BY
                applications DESC,
                category ASC
        """)

        category_rows = cursor.fetchall()

        applications_by_category = [
            {
                "category": row["category"],
                "applications": int(row["applications"] or 0)
            }
            for row in category_rows
        ]

        # --------------------------------------------------
        # 7. Top-performing schemes
        # --------------------------------------------------
        # Aggregate each table independently to avoid
        # multiplying counts from joins.

        cursor.execute("""
            SELECT
                s.scheme_id,
                s.scheme_name,
                COALESCE(v.views, 0) AS views,
                COALESCE(a.applications, 0) AS applications,
                ROUND(
                    CASE
                        WHEN COALESCE(v.views, 0) = 0
                            THEN 0
                        ELSE
                            COALESCE(a.applications, 0)
                            * 100.0 / v.views
                    END,
                    2
                ) AS success_rate
            FROM adminschemes s
            LEFT JOIN (
                SELECT
                    scheme_id,
                    COUNT(*) AS views
                FROM viewed_schemes
                GROUP BY scheme_id
            ) v
                ON v.scheme_id = s.scheme_id
            LEFT JOIN (
                SELECT
                    scheme_id,
                    COUNT(*) AS applications
                FROM applied_schemes
                GROUP BY scheme_id
            ) a
                ON a.scheme_id = s.scheme_id
            ORDER BY
                views DESC,
                applications DESC,
                s.scheme_id DESC
            LIMIT 5
        """)

        scheme_rows = cursor.fetchall()

        top_schemes = []

        for scheme in scheme_rows:
            views = int(scheme["views"] or 0)
            applications = int(scheme["applications"] or 0)
            rate = float(scheme["success_rate"] or 0)

            if rate > 75:
                performance = "High"
            elif rate > 50:
                performance = "Medium"
            else:
                performance = "Low"

            top_schemes.append({
                "scheme_id": scheme["scheme_id"],
                "scheme_name": scheme["scheme_name"],
                "views": views,
                "applications": applications,
                "success_rate": rate,
                "performance": performance
            })

        return jsonify({
            "success": True,
            "admin_name": admin_name,
            "unread_notifications": unread_notifications,
            "total_users": total_users,
            "total_applications": total_applications,
            "total_views": total_views,
            "applications_by_category": applications_by_category,
            "top_schemes": top_schemes
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin dashboard analytics"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load dashboard analytics."
        }), 500

    finally:
        close_database_resources(cursor, conn)
