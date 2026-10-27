
import json
import re
from datetime import date, datetime

from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.database.connection import get_db_connection


adminset_bp = Blueprint("adminset", __name__)


# ==========================================================
# CONSTANTS
# ==========================================================

ALLOWED_GENDERS = {"Male", "Female", "Other"}

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

DEFAULT_PREFERENCES = {
    "notifications": {
        "new_applications": True,
        "new_user_registration": True,
        "scheme_updates": True,
        "system_notifications": True,
    },
    "general": {
        "compact_view": False,
        "confirm_before_leaving": True,
    },
}

ALLOWED_NOTIFICATION_KEYS = set(
    DEFAULT_PREFERENCES["notifications"].keys()
)

ALLOWED_GENERAL_KEYS = set(
    DEFAULT_PREFERENCES["general"].keys()
)


# ==========================================================
# HELPERS
# ==========================================================

def get_logged_in_admin():
    """Return the authenticated admin ID, or None."""
    if (
        session.get("role") != "admin"
        or not session.get("admin_id")
    ):
        return None

    return session["admin_id"]


def close_database_resources(cursor=None, conn=None):
    """Close database resources without masking earlier errors."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close admin settings cursor"
            )

    if conn is not None:
        try:
            conn.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close admin settings connection"
            )


def get_json_object():
    """Return a JSON object, or None for invalid request data."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return None

    return data


def serialize_date(value):
    """Convert date/time values to JSON-friendly strings."""
    if value is None:
        return ""

    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")

    return str(value)[:10]


def get_default_preferences():
    """Return a fresh copy of the default preferences."""
    return {
        section: values.copy()
        for section, values in DEFAULT_PREFERENCES.items()
    }


def read_preferences(cursor, admin_id):
    """Load saved preferences and merge them with application defaults."""
    preferences = get_default_preferences()

    cursor.execute(
        """
        SELECT setting_key, setting_value
        FROM admin_settings
        WHERE admin_id = %s
          AND setting_key IN ('notifications', 'general')
        """,
        (admin_id,),
    )

    rows = cursor.fetchall()

    for row in rows:
        key = row["setting_key"]
        value = row["setting_value"]

        if key not in preferences:
            continue

        if isinstance(value, bytes):
            value = value.decode("utf-8")

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                current_app.logger.warning(
                    "Invalid JSON in admin_settings for admin_id=%s, key=%s",
                    admin_id,
                    key,
                )
                continue

        if not isinstance(value, dict):
            continue

        # Only apply recognized keys with actual Boolean values.
        allowed_keys = (
            ALLOWED_NOTIFICATION_KEYS
            if key == "notifications"
            else ALLOWED_GENERAL_KEYS
        )

        for setting, setting_value in value.items():
            if (
                setting in allowed_keys
                and type(setting_value) is bool
            ):
                preferences[key][setting] = setting_value

    return preferences


# ==========================================================
# GET ADMIN PROFILE
# GET /api/admin/settings/profile
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/profile",
    methods=["GET"],
)
def get_admin_settings_profile():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                admin_id,
                full_name,
                email,
                mobile_number,
                date_of_birth,
                gender,
                state,
                username
            FROM admins
            WHERE admin_id = %s
            LIMIT 1
            """,
            (admin_id,),
        )

        admin = cursor.fetchone()

        if not admin:
            session.clear()

            return jsonify({
                "success": False,
                "message": "Admin account not found.",
            }), 404

        admin["date_of_birth"] = serialize_date(
            admin.get("date_of_birth")
        )

        return jsonify({
            "success": True,
            "admin": admin,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin profile"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load admin profile.",
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# UPDATE ADMIN PROFILE
# PUT /api/admin/settings/profile
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/profile",
    methods=["PUT"],
)
def update_admin_settings_profile():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    data = get_json_object()

    if data is None:
        return jsonify({
            "success": False,
            "message": "Please submit profile details as JSON.",
        }), 400

    full_name = data.get("full_name")
    email = data.get("email")
    mobile = data.get("mobile_number")
    dob_value = data.get("date_of_birth")
    gender = data.get("gender")
    state = data.get("state")

    # Validate required fields.
    if not all(
        isinstance(value, str) and value.strip()
        for value in (full_name, email, mobile)
    ):
        return jsonify({
            "success": False,
            "message": "Name, email and mobile number are required.",
        }), 400

    full_name = full_name.strip()
    email = email.strip().lower()
    mobile = mobile.strip()

    if len(full_name) > 200:
        return jsonify({
            "success": False,
            "message": "Full name is too long.",
        }), 400

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({
            "success": False,
            "message": "Enter a valid email address.",
        }), 400

    if not re.fullmatch(r"[0-9]{10}", mobile):
        return jsonify({
            "success": False,
            "message": "Enter a valid 10-digit mobile number.",
        }), 400

    if gender is not None:
        if not isinstance(gender, str):
            return jsonify({
                "success": False,
                "message": "Invalid gender.",
            }), 400

        gender = gender.strip()

        if gender and gender not in ALLOWED_GENDERS:
            return jsonify({
                "success": False,
                "message": "Please select a valid gender.",
            }), 400

    if state is not None:
        if not isinstance(state, str):
            return jsonify({
                "success": False,
                "message": "Invalid state.",
            }), 400

        state = state.strip()

        if state and state not in ALLOWED_STATES:
            return jsonify({
                "success": False,
                "message": "Please select a valid state.",
            }), 400

    # Permit an empty DOB to clear the field.
    dob = None

    if dob_value not in (None, ""):
        if not isinstance(dob_value, str):
            return jsonify({
                "success": False,
                "message": "Invalid date of birth.",
            }), 400

        try:
            dob = date.fromisoformat(dob_value)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Date of birth must use YYYY-MM-DD format.",
            }), 400

        if dob >= date.today():
            return jsonify({
                "success": False,
                "message": "Date of birth must be in the past.",
            }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE admins
            SET
                full_name = %s,
                email = %s,
                mobile_number = %s,
                date_of_birth = %s,
                gender = %s,
                state = %s
            WHERE admin_id = %s
            """,
            (
                full_name,
                email,
                mobile,
                dob,
                gender or None,
                state or None,
                admin_id,
            ),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                SELECT admin_id
                FROM admins
                WHERE admin_id = %s
                """,
                (admin_id,),
            )

            if not cursor.fetchone():
                conn.rollback()

                return jsonify({
                    "success": False,
                    "message": "Admin account not found.",
                }), 404

        conn.commit()

        # Keep the displayed admin name synchronized with the session.
        session["admin_name"] = full_name

        return jsonify({
            "success": True,
            "message": "Profile updated successfully.",
        }), 200

    except Exception as error:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Failed to roll back admin profile update"
                )

        if getattr(error, "errno", None) == 1062:
            return jsonify({
                "success": False,
                "message": "That email or mobile number is already in use.",
            }), 409

        current_app.logger.exception(
            "Failed to update admin profile"
        )

        return jsonify({
            "success": False,
            "message": "Unable to update profile.",
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# UPDATE ADMIN PASSWORD
# PUT /api/admin/settings/password
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/password",
    methods=["PUT"],
)
def update_admin_password():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    data = get_json_object()

    if data is None:
        return jsonify({
            "success": False,
            "message": "Please submit password details as JSON.",
        }), 400

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if (
        not isinstance(current_password, str)
        or not isinstance(new_password, str)
        or not current_password
        or not new_password
    ):
        return jsonify({
            "success": False,
            "message": "Both passwords are required.",
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "success": False,
            "message": "The new password must be at least 8 characters.",
        }), 400

    if len(new_password) > 1024:
        return jsonify({
            "success": False,
            "message": "The new password is too long.",
        }), 400

    if new_password == current_password:
        return jsonify({
            "success": False,
            "message": "The new password must differ from the current password.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT password_hash
            FROM admins
            WHERE admin_id = %s
            LIMIT 1
            """,
            (admin_id,),
        )

        admin = cursor.fetchone()

        if not admin:
            session.clear()

            return jsonify({
                "success": False,
                "message": "Admin account not found.",
            }), 404

        if not check_password_hash(
            admin["password_hash"],
            current_password,
        ):
            return jsonify({
                "success": False,
                "message": "Current password is incorrect.",
            }), 400

        new_hash = generate_password_hash(new_password)

        cursor.execute(
            """
            UPDATE admins
            SET password_hash = %s
            WHERE admin_id = %s
            """,
            (new_hash, admin_id),
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Password updated successfully.",
        }), 200

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Failed to roll back admin password update"
                )

        current_app.logger.exception(
            "Failed to update admin password"
        )

        return jsonify({
            "success": False,
            "message": "Unable to update password.",
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# DELETE ADMIN ACCOUNT
# DELETE /api/admin/settings/account
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/account",
    methods=["DELETE"],
)
def delete_admin_account():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM admins
            WHERE admin_id = %s
            """,
            (admin_id,),
        )

        if cursor.rowcount == 0:
            conn.rollback()

            return jsonify({
                "success": False,
                "message": "Admin account not found.",
            }), 404

        conn.commit()

        # Log out only after the database deletion succeeds.
        session.clear()

        return jsonify({
            "success": True,
            "message": "Administrator account deleted successfully.",
        }), 200

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Failed to roll back admin account deletion"
                )

        current_app.logger.exception(
            "Failed to delete admin account"
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to delete admin account. Related database "
                "records or foreign-key constraints may prevent deletion."
            ),
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# GET ADMIN PREFERENCES
# GET /api/admin/settings/preferences
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/preferences",
    methods=["GET"],
)
def get_admin_settings_preferences():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        preferences = read_preferences(cursor, admin_id)

        return jsonify({
            "success": True,
            "preferences": preferences,
        }), 200

    except Exception:
        current_app.logger.exception(
            "Failed to load admin preferences"
        )

        return jsonify({
            "success": False,
            "message": "Unable to load preferences.",
        }), 500

    finally:
        close_database_resources(cursor, conn)


# ==========================================================
# SAVE ADMIN PREFERENCES
# PUT /api/admin/settings/preferences
# ==========================================================

@adminset_bp.route(
    "/api/admin/settings/preferences",
    methods=["PUT"],
)
def update_admin_settings_preferences():
    admin_id = get_logged_in_admin()

    if not admin_id:
        return jsonify({
            "success": False,
            "message": "Admin login required.",
        }), 401

    data = get_json_object()

    if data is None:
        return jsonify({
            "success": False,
            "message": "Please submit preferences as JSON.",
        }), 400

    # Allow partial updates, but reject unknown top-level sections.
    allowed_sections = {"notifications", "general"}

    if not set(data).issubset(allowed_sections):
        return jsonify({
            "success": False,
            "message": "Unknown preferences section.",
        }), 400

    if not data:
        return jsonify({
            "success": False,
            "message": "No preferences were provided.",
        }), 400

    notifications = data.get("notifications", {})
    general = data.get("general", {})

    if not isinstance(notifications, dict):
        return jsonify({
            "success": False,
            "message": "Invalid notifications preferences.",
        }), 400

    if not isinstance(general, dict):
        return jsonify({
            "success": False,
            "message": "Invalid general preferences.",
        }), 400

    if not set(notifications).issubset(ALLOWED_NOTIFICATION_KEYS):
        return jsonify({
            "success": False,
            "message": "Unknown notification preference.",
        }), 400

    if not set(general).issubset(ALLOWED_GENERAL_KEYS):
        return jsonify({
            "success": False,
            "message": "Unknown general preference.",
        }), 400

    if any(type(value) is not bool for value in notifications.values()):
        return jsonify({
            "success": False,
            "message": "Notification values must be true or false.",
        }), 400

    if any(type(value) is not bool for value in general.values()):
        return jsonify({
            "success": False,
            "message": "General preference values must be true or false.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Merge supplied values with existing settings so partial updates
        # don't reset other saved preferences.
        preferences = read_preferences(cursor, admin_id)

        preferences["notifications"].update(notifications)
        preferences["general"].update(general)

        settings_to_save = [
            (
                "notifications",
                json.dumps(preferences["notifications"]),
            ),
            (
                "general",
                json.dumps(preferences["general"]),
            ),
        ]

        for setting_key, setting_value in settings_to_save:
            cursor.execute(
                """
                INSERT INTO admin_settings (
                    admin_id,
                    setting_key,
                    setting_value
                )
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    setting_value = VALUES(setting_value)
                """,
                (admin_id, setting_key, setting_value),
            )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Preferences saved successfully.",
            "preferences": preferences,
        }), 200

    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                current_app.logger.exception(
                    "Failed to roll back admin preferences"
                )

        current_app.logger.exception(
            "Failed to save admin preferences"
        )

        return jsonify({
            "success": False,
            "message": "Unable to save preferences.",
        }), 500

    finally:
        close_database_resources(cursor, conn)
