
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session, current_app
from app.database.connection import get_db_connection


notification_bp = Blueprint("notification", __name__)

ADMIN_SETTING_ALIASES = {
    "new_application_alerts": (
        "new_application_alerts",
        "new_applications",
        "new_application",
    ),
    "new_user_registration": (
        "new_user_registration",
        "new_user_registrations",
    ),
}

USER_SETTING_KEYS = {"scheme_updates", "reminders"}

DEFAULT_USER_SETTINGS = {
    "scheme_updates": False,
    "reminders": False,
}


# ==========================================================
# SHARED HELPERS
# ==========================================================

def get_connection():
    return get_db_connection()


def close_resources(cursor=None, conn=None):
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.warning(
                "Could not close database cursor.", exc_info=True
            )

    if conn is not None:
        try:
            conn.close()
        except Exception:
            current_app.logger.warning(
                "Could not close database connection.", exc_info=True
            )


def admin_id():
    if session.get("role") != "admin":
        return None
    return session.get("admin_id")


def user_id():
    if session.get("role") != "user":
        return None
    return session.get("user_id")


def response_error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def parse_setting_value(value):
    """Convert JSON, database booleans, and common strings to Python values."""
    if isinstance(value, (dict, list, bool)):
        return value

    if isinstance(value, (int, float)):
        return value == 1

    if isinstance(value, str):
        text = value.strip()

        try:
            return json.loads(text)
        except (ValueError, TypeError):
            normalized = text.lower()

            if normalized in ("true", "1", "yes", "on"):
                return True
            if normalized in ("false", "0", "no", "off", ""):
                return False

    return False


def parse_bool(value):
    return parse_setting_value(value) is True


def serialize_datetime(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def get_admin_preference(cursor, aid, setting_key, default=False):
    """
    Read a preference in either supported format:
      1. Separate row: setting_key = new_user_registration
      2. JSON row: setting_key = notifications,
         setting_value = {"new_user_registration": true}

    Per-setting rows take precedence over the JSON preference object.
    """
    aliases = ADMIN_SETTING_ALIASES.get(
        setting_key, (setting_key,)
    )

    placeholders = ",".join(["%s"] * len(aliases))

    cursor.execute(
        f"""
        SELECT setting_value
        FROM admin_settings
        WHERE admin_id = %s
          AND setting_key IN ({placeholders})
        """,
        (aid, *aliases),
    )

    rows = cursor.fetchall()

    if rows:
        return parse_bool(rows[0]["setting_value"])

    cursor.execute(
        """
        SELECT setting_value
        FROM admin_settings
        WHERE admin_id = %s
          AND setting_key = %s
        LIMIT 1
        """,
        (aid, "notifications"),
    )

    row = cursor.fetchone()

    if row:
        value = parse_setting_value(row["setting_value"])

        if isinstance(value, dict):
            for alias in aliases:
                if alias in value:
                    return parse_bool(value[alias])

    return default


def get_all_admin_preferences(cursor, aid):
    return {
        key: get_admin_preference(cursor, aid, key, False)
        for key in ADMIN_SETTING_ALIASES
    }


def save_setting(cursor, owner_id, key, value):
    cursor.execute(
        """
        INSERT INTO admin_settings
            (admin_id, setting_key, setting_value)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            setting_value = VALUES(setting_value)
        """,
        (owner_id, key, json.dumps(bool(value))),
    )


def is_admin_alert_enabled(cursor, setting_key):
    """
    Alerts are enabled if at least one admin enabled the relevant preference.
    """
    cursor.execute("SELECT admin_id FROM admins")
    admins = cursor.fetchall()

    for admin in admins:
        aid = (
            admin["admin_id"]
            if isinstance(admin, dict)
            else admin[0]
        )

        if get_admin_preference(cursor, aid, setting_key, False):
            return True

    return False


# ==========================================================
# USER SCHEME REMINDERS
# ==========================================================

def generate_scheme_reminders(cursor, uid):
    """
    Create one reminder per saved scheme/deadline.

    Call this helper from an authenticated user request or scheduled job.
    """
    cursor.execute(
        """
        SELECT setting_value
        FROM user_notification_settings
        WHERE user_id = %s AND setting_key = %s
        LIMIT 1
        """,
        (uid, "reminders"),
    )

    preference = cursor.fetchone()

    if not preference:
        return

    value = parse_setting_value(preference["setting_value"])

    if value is not True:
        return

    cursor.execute(
        """
        SELECT s.scheme_id, s.scheme_name, s.deadline
        FROM saved_schemes ss
        JOIN adminschemes s ON s.scheme_id = ss.scheme_id
        WHERE ss.user_id = %s
          AND s.deadline >= CURDATE()
          AND s.deadline < DATE_ADD(CURDATE(), INTERVAL 6 DAY)
        """,
        (uid,),
    )

    for scheme in cursor.fetchall():
        deadline = scheme["deadline"]

        if hasattr(deadline, "strftime"):
            deadline_text = deadline.strftime("%Y-%m-%d")
        else:
            deadline_text = str(deadline)

        title = "Scheme Deadline Reminder"
        message = (
            f"Reminder: {scheme['scheme_name']} has an application "
            f"deadline of {deadline_text}. Please check the scheme "
            "details before applying."
        )

        cursor.execute(
            """
            SELECT notification_id
            FROM notifications
            WHERE user_id = %s
              AND title = %s
              AND message = %s
            LIMIT 1
            """,
            (uid, title, message),
        )

        if cursor.fetchone():
            continue

        cursor.execute(
            """
            INSERT INTO notifications
                (user_id, title, message, notification_type,
                 is_read, created_at)
            VALUES (%s, %s, %s, %s, 0, NOW())
            """,
            (uid, title, message, "general"),
        )


# ==========================================================
# ADMIN ALERT CREATION HELPERS
# ==========================================================

def create_application_admin_alert(cursor, uid, scheme_id):
    """Call after a successful Apply Now/application action."""
    if not is_admin_alert_enabled(cursor, "new_application_alerts"):
        return False

    cursor.execute(
        """
        SELECT scheme_name
        FROM adminschemes
        WHERE scheme_id = %s
        LIMIT 1
        """,
        (scheme_id,),
    )

    scheme = cursor.fetchone()

    scheme_name = (
        scheme["scheme_name"]
        if scheme
        else f"Scheme #{scheme_id}"
    )

    message = (
        f"A user (ID: {uid}) clicked Apply Now for {scheme_name}."
    )

    cursor.execute(
        """
        INSERT INTO admin_applynotifications
            (user_id, scheme_id, message, notification_type,
             is_read, created_at)
        VALUES (%s, %s, %s, %s, 0, NOW())
        """,
        (uid, scheme_id, message, "apply_click"),
    )

    return True


def create_registration_admin_alert(cursor, uid, full_name=None):
    """Call after successful user registration."""
    if not is_admin_alert_enabled(cursor, "new_user_registration"):
        return False

    display_name = (full_name or "").strip() or f"User ID {uid}"
    message = f"New user registered: {display_name}."

    cursor.execute(
        """
        INSERT INTO admin_newnotifications
            (user_id, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, 0, NOW())
        """,
        (uid, message, "registration"),
    )

    return True


# ==========================================================
# ADMIN NOTIFICATION SETTINGS
# ==========================================================

@notification_bp.route(
    "/api/admin/settings/notifications",
    methods=["GET", "PUT"],
)
def admin_notification_settings():
    aid = admin_id()

    if not aid:
        return response_error("Admin login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == "PUT":
            payload = request.get_json(silent=True) or {}
            key = payload.get("setting_key")
            value = payload.get("setting_value")

            if key not in ADMIN_SETTING_ALIASES:
                return response_error("Invalid setting.")

            if not isinstance(value, bool):
                return response_error(
                    "Setting value must be true or false."
                )

            save_setting(cursor, aid, key, value)
            conn.commit()

            return jsonify({
                "success": True,
                "message": "Setting saved.",
                "setting_key": key,
                "setting_value": value,
            })

        return jsonify({
            "success": True,
            "settings": get_all_admin_preferences(cursor, aid),
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to process admin notification settings"
        )

        return response_error(
            "Unable to process admin settings.", 500
        )

    finally:
        close_resources(cursor, conn)


# ==========================================================
# USER NOTIFICATION SETTINGS
# ==========================================================

@notification_bp.route(
    "/api/user/settings/notifications",
    methods=["GET", "PUT"],
)
def user_notification_settings():
    uid = user_id()

    if not uid:
        return response_error("User login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == "PUT":
            payload = request.get_json(silent=True) or {}

            if "setting_key" in payload:
                key = payload.get("setting_key")
                value = payload.get("setting_value")

                if (
                    key not in USER_SETTING_KEYS
                    or not isinstance(value, bool)
                ):
                    return response_error(
                        "Invalid notification setting."
                    )

                settings_to_save = {key: value}

            else:
                settings_to_save = payload.get("settings", {})

                if (
                    not isinstance(settings_to_save, dict)
                    or not settings_to_save
                    or not set(settings_to_save).issubset(
                        USER_SETTING_KEYS
                    )
                ):
                    return response_error(
                        "Invalid notification settings."
                    )

                if any(
                    not isinstance(value, bool)
                    for value in settings_to_save.values()
                ):
                    return response_error(
                        "Setting values must be true or false."
                    )

            for key, value in settings_to_save.items():
                cursor.execute(
                    """
                    INSERT INTO user_notification_settings
                        (user_id, setting_key, setting_value)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        setting_value = VALUES(setting_value)
                    """,
                    (uid, key, json.dumps(value)),
                )

            conn.commit()

            return jsonify({
                "success": True,
                "message": "Notification preferences saved.",
                "settings": settings_to_save,
            })

        cursor.execute(
            """
            SELECT setting_key, setting_value
            FROM user_notification_settings
            WHERE user_id = %s
            """,
            (uid,),
        )

        settings = DEFAULT_USER_SETTINGS.copy()

        for row in cursor.fetchall():
            key = row["setting_key"]

            if key in USER_SETTING_KEYS:
                settings[key] = parse_bool(row["setting_value"])

        return jsonify({
            "success": True,
            "settings": settings,
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to process user notification settings"
        )

        return response_error(
            "Unable to process notification settings.", 500
        )

    finally:
        close_resources(cursor, conn)



@notification_bp.route("/reminders/count", methods=["GET"])
def get_reminders_count():
    if not session.get("user_id"):
        return jsonify({"message": "Unauthorized"}), 401

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        today = date.today()
        next_three_days = today + timedelta(days=3)

        cursor.execute("""
            SELECT COUNT(*) AS reminders_count
            FROM adminschemes
            WHERE deadline IS NOT NULL
              AND DATE(deadline) BETWEEN %s AND %s
        """, (today, next_three_days))

        result = cursor.fetchone()

        return jsonify({
            "reminders_count": result["reminders_count"]
        })

    except Exception as e:
        print("Reminders count error:", e)
        return jsonify({"message": "Failed to load reminders"}), 500

    finally:
        cursor.close()
        connection.close()
# ==========================================================
# USER ALERTS
# ==========================================================

@notification_bp.route("/api/user/alerts", methods=["GET"])
def get_user_alerts():
    uid = user_id()

    if not uid:
        return response_error("User login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT notification_id, title, message,
                   notification_type, is_read, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC, notification_id DESC
            """,
            (uid,),
        )

        alerts = cursor.fetchall()

        for alert in alerts:
            alert["is_read"] = bool(alert["is_read"])
            alert["created_at"] = serialize_datetime(
                alert.get("created_at")
            )

        return jsonify({"success": True, "alerts": alerts})

    except Exception:
        current_app.logger.exception("Unable to load user alerts")
        return response_error("Unable to load alerts.", 500)

    finally:
        close_resources(cursor, conn)


@notification_bp.route(
    "/api/user/alerts/<int:notification_id>/read",
    methods=["PATCH"],
)
def mark_user_alert_read(notification_id):
    uid = user_id()

    if not uid:
        return response_error("User login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE notification_id = %s AND user_id = %s
            """,
            (notification_id, uid),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return response_error("Notification not found.", 404)

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Notification marked as read.",
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to mark user notification as read"
        )

        return response_error("Unable to update notification.", 500)

    finally:
        close_resources(cursor, conn)


@notification_bp.route(
    "/api/user/alerts/<int:notification_id>",
    methods=["DELETE"],
)
def delete_user_alert(notification_id):
    uid = user_id()

    if not uid:
        return response_error("User login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM notifications
            WHERE notification_id = %s AND user_id = %s
            """,
            (notification_id, uid),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return response_error("Notification not found.", 404)

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Notification deleted.",
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception("Unable to delete user alert")
        return response_error("Unable to delete notification.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# ADMIN SENDS NOTIFICATIONS TO USERS
# ==========================================================

@notification_bp.route(
    "/api/admin/notifications",
    methods=["POST"],
)
def send_admin_notification():
    aid = admin_id()

    if not aid:
        return response_error("Admin login required.", 401)

    payload = request.get_json(silent=True) or {}

    title = payload.get("title") or ""
    message = payload.get("message") or ""
    notification_type = (
        payload.get("notification_type") or "general"
    )
    audience = payload.get("audience") or "all"
    category = payload.get("category") or ""

    if not all(isinstance(value, str) for value in (
        title, message, notification_type, audience, category
    )):
        return response_error("Invalid notification data.")

    title = title.strip()
    message = message.strip()
    notification_type = notification_type.strip().lower()
    audience = audience.strip().lower()
    category = category.strip()

    if not title or not message:
        return response_error("Title and message are required.")

    if len(title) > 200 or len(message) > 10000:
        return response_error("Title or message is too long.")

    if notification_type not in {
        "important", "general", "new", "system"
    }:
        return response_error("Invalid notification type.")

    if audience not in {"all", "category"}:
        return response_error("Invalid target audience.")

    if audience == "category" and not category:
        return response_error("Choose a target category.")

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if audience == "category":
            cursor.execute(
                """
                SELECT user_id
                FROM users
                WHERE category = %s
                """,
                (category,),
            )
        else:
            cursor.execute("SELECT user_id FROM users")

        recipients = cursor.fetchall()
        sent_count = 0

        for recipient in recipients:
            uid = recipient["user_id"]

            # "new" is treated as a scheme-update notification.
            if notification_type == "new":
                cursor.execute(
                    """
                    SELECT setting_value
                    FROM user_notification_settings
                    WHERE user_id = %s
                      AND setting_key = %s
                    LIMIT 1
                    """,
                    (uid, "scheme_updates"),
                )

                preference = cursor.fetchone()

                if not preference or not parse_bool(
                    preference["setting_value"]
                ):
                    continue

            cursor.execute(
                """
                INSERT INTO notifications
                    (user_id, title, message, notification_type,
                     is_read, created_at)
                VALUES (%s, %s, %s, %s, 0, NOW())
                """,
                (uid, title, message, notification_type),
            )

            sent_count += 1

        # IMPORTANT: Save ONE history row after the recipient loop.
        cursor.execute(
            """
            INSERT INTO admin_sent_notifications
                (
                    admin_id,
                    title,
                    message,
                    notification_type,
                    audience,
                    category,
                    recipients_count,
                    created_at
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                aid,
                title,
                message,
                notification_type,
                audience,
                category or None,
                sent_count,
            ),
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Notification sent.",
            "recipients": sent_count,
        }), 201

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to send admin notification"
        )

        return response_error("Unable to send notification.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# GET COMBINED ADMIN ALERTS
# ==========================================================

@notification_bp.route("/api/admin/alerts", methods=["GET"])
def get_admin_alerts():
    if not admin_id():
        return response_error("Admin login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Application alerts
        cursor.execute(
            """
            SELECT
                CONCAT('application:', notification_id) AS alert_id,
                notification_id AS source_id,
                'application' AS source,
                user_id,
                scheme_id,
                message,
                notification_type,
                is_read,
                created_at
            FROM admin_applynotifications
            """
        )

        alerts = cursor.fetchall()

        # Registration alerts
        cursor.execute(
            """
            SELECT
                CONCAT('registration:', notification_id) AS alert_id,
                notification_id AS source_id,
                'registration' AS source,
                user_id,
                NULL AS scheme_id,
                message,
                notification_type,
                is_read,
                created_at
            FROM admin_newnotifications
            """
        )

        alerts.extend(cursor.fetchall())

        # Notifications sent by the admin
        cursor.execute(
            """
            SELECT
                CONCAT('admin_sent:', notification_id) AS alert_id,
                notification_id AS source_id,
                'admin_sent' AS source,
                NULL AS user_id,
                NULL AS scheme_id,
                message,
                notification_type,
                1 AS is_read,
                created_at,
                title,
                recipients_count,
                audience,
                category
            FROM admin_sent_notifications
            """
        )

        alerts.extend(cursor.fetchall())

        for alert in alerts:
            if alert["source"] == "application":
                alert["title"] = "New Application Alert"

            elif alert["source"] == "registration":
                alert["title"] = "New User Registration"

            # admin_sent entries keep their database title.

            alert["is_read"] = bool(alert["is_read"])
            alert["created_at"] = serialize_datetime(
                alert.get("created_at")
            )

        alerts.sort(
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )

        return jsonify({
            "success": True,
            "alerts": alerts,
        })

    except Exception:
        current_app.logger.exception("Unable to load admin alerts")
        return response_error("Unable to load admin alerts.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# MARK ONE ADMIN ALERT AS READ
# ==========================================================

def parse_admin_alert_id(alert_id):
    try:
        source, raw_id = alert_id.split(":", 1)
        notification_id = int(raw_id)

        if notification_id <= 0:
            return None, None

        return source, notification_id

    except (ValueError, AttributeError):
        return None, None


@notification_bp.route(
    "/api/admin/alerts/<path:alert_id>/read",
    methods=["PATCH"],
)
def mark_admin_alert_read(alert_id):
    if not admin_id():
        return response_error("Admin login required.", 401)

    source, notification_id = parse_admin_alert_id(alert_id)

    table_by_source = {
        "application": "admin_applynotifications",
        "registration": "admin_newnotifications",
    }

    table = table_by_source.get(source)

    if not table:
        return response_error("Invalid alert ID.")

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            UPDATE {table}
            SET is_read = 1
            WHERE notification_id = %s
            """,
            (notification_id,),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return response_error("Alert not found.", 404)

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Alert marked as read.",
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to mark admin alert as read"
        )

        return response_error("Unable to update alert.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# MARK ALL ADMIN ALERTS AS READ
# ==========================================================

@notification_bp.route(
    "/api/admin/alerts/read-all",
    methods=["PATCH"],
)
def mark_all_admin_alerts_read():
    if not admin_id():
        return response_error("Admin login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE admin_applynotifications SET is_read = 1"
        )

        cursor.execute(
            "UPDATE admin_newnotifications SET is_read = 1"
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "All admin alerts marked as read.",
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to mark all admin alerts as read"
        )

        return response_error("Unable to update alerts.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# DELETE ONE ADMIN ALERT
# ==========================================================

@notification_bp.route(
    "/api/admin/alerts/<path:alert_id>",
    methods=["DELETE"],
)
def delete_admin_alert(alert_id):
    if not admin_id():
        return response_error("Admin login required.", 401)

    source, notification_id = parse_admin_alert_id(alert_id)

    table_by_source = {
        "application": "admin_applynotifications",
        "registration": "admin_newnotifications",
    }

    table = table_by_source.get(source)

    if not table:
        return response_error("Invalid alert ID.")

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            f"DELETE FROM {table} WHERE notification_id = %s",
            (notification_id,),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return response_error("Alert not found.", 404)

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Alert deleted.",
        })

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception("Unable to delete admin alert")
        return response_error("Unable to delete alert.", 500)

    finally:
        close_resources(cursor, conn)


# ==========================================================
# ADMIN HEADER: NAME + UNREAD NOTIFICATION COUNT
# ==========================================================

@notification_bp.route("/api/admin/header", methods=["GET"])
def get_admin_header():
    aid = admin_id()

    if not aid:
        return response_error("Admin login required.", 401)

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT full_name
            FROM admins
            WHERE admin_id = %s
            LIMIT 1
            """,
            (aid,),
        )

        admin = cursor.fetchone()

        if not admin:
            return response_error("Admin not found.", 404)

        cursor.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM admin_applynotifications
            WHERE is_read = 0
            """
        )

        application_result = cursor.fetchone()
        application_unread = int(
            application_result["unread_count"] or 0
        )

        cursor.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM admin_newnotifications
            WHERE is_read = 0
            """
        )

        registration_result = cursor.fetchone()
        registration_unread = int(
            registration_result["unread_count"] or 0
        )

        unread_total = application_unread + registration_unread

        return jsonify({
            "success": True,
            "admin_name": admin["full_name"],
            "unread_notifications": unread_total,
            "unread_count": unread_total,
        })

    except Exception:
        current_app.logger.exception(
            "Unable to load admin header"
        )

        return response_error(
            "Unable to load admin header.", 500
        )

    finally:
        close_resources(cursor, conn)
