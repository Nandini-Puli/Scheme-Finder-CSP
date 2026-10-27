
import os
from datetime import date

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
    send_file,
    current_app,
)

from app.database.connection import get_db_connection


profile_bp = Blueprint("profile", __name__)


# ---------------------------------------------------------
# PROFILE CONFIGURATION
# ---------------------------------------------------------

SECTION_FIELDS = {
    "education": [
        "qualification_level",
        "institution_name",
        "course_name",
        "field_of_study",
        "graduation_year",
        "grade_or_cgpa",
    ],
    "employment": [
        "employment_status",
        "employer_name",
        "job_title",
        "work_experience_years",
        "monthly_salary",
    ],
    "location": [
        "address_line",
        "district",
        "city",
        "state",
        "pincode",
    ],
    "income": [
        "annual_income",
        "income_source",
        "family_income",
        "ration_card_type",
    ],
}

TABLES = {
    "education": "education_details",
    "employment": "employment_details",
    "location": "location_details",
    "income": "income_details",
}

PERSONAL_FIELDS = [
    "full_name",
    "email",
    "mobile_number",
    "date_of_birth",
    "gender",
    "state",
    "category",
    "district",
    "annual_income",
]

CORE_USER_FIELDS = [
    "full_name",
    "email",
    "mobile_number",
    "date_of_birth",
    "gender",
    "state",
    "category",
]


# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------

def logged_in_user_id():
    """Return the authenticated user's ID, never an admin's ID."""
    if session.get("role") != "user":
        return None

    user_id = session.get("user_id")
    return user_id if user_id else None


def age_from_dob(value):
    """Calculate age from a date or ISO-formatted date string."""
    if not value:
        return None

    try:
        if isinstance(value, str):
            value = date.fromisoformat(value[:10])

        today = date.today()

        return (
            today.year
            - value.year
            - ((today.month, today.day) < (value.month, value.day))
        )

    except (ValueError, TypeError, AttributeError):
        return None


def first_present(*values):
    """Return the first non-NULL, non-blank value."""
    for value in values:
        if value is not None:
            if not isinstance(value, str) or value.strip():
                return value

    return None


def clean_value(value):
    """Convert blank HTML form values to SQL NULL."""
    if isinstance(value, str) and not value.strip():
        return None

    return value


def get_user_row(cursor, user_id):
    """Retrieve the user while supporting a legacy dob column."""
    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )

    user = cursor.fetchone()

    if not user:
        return None

    user["__db_columns"] = set(user.keys())

    user["date_of_birth"] = first_present(
        user.get("date_of_birth"),
        user.get("dob"),
    )

    return user


def ensure_personal_info(cursor, user):
    """
    Create a personal_info row if one does not exist.

    Existing non-empty personal information is preserved.
    """
    cursor.execute(
        """
        INSERT INTO personal_info (
            user_id,
            full_name,
            email,
            mobile_number,
            date_of_birth,
            gender,
            state,
            category
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            full_name = COALESCE(
                NULLIF(full_name, ''),
                VALUES(full_name)
            ),
            email = COALESCE(
                NULLIF(email, ''),
                VALUES(email)
            ),
            mobile_number = COALESCE(
                NULLIF(mobile_number, ''),
                VALUES(mobile_number)
            ),
            date_of_birth = COALESCE(
                date_of_birth,
                VALUES(date_of_birth)
            ),
            gender = COALESCE(
                NULLIF(gender, ''),
                VALUES(gender)
            ),
            state = COALESCE(
                NULLIF(state, ''),
                VALUES(state)
            ),
            category = COALESCE(
                NULLIF(category, ''),
                VALUES(category)
            )
        """,
        (
            user["user_id"],
            user.get("full_name"),
            user.get("email"),
            user.get("mobile_number"),
            user.get("date_of_birth"),
            user.get("gender"),
            user.get("state"),
            user.get("category"),
        ),
    )


def section_data(cursor, user_id, section):
    """Read the profile section for the specified user."""
    fields = SECTION_FIELDS[section]
    table = TABLES[section]

    cursor.execute(
        f"""
        SELECT {", ".join(fields)}
        FROM {table}
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return {field: None for field in fields}

    return {
        field: row.get(field)
        for field in fields
    }


def save_section_without_unique_key(
    cursor,
    user_id,
    section,
    submitted,
):
    """
    Update all existing rows for this user, or insert one if none exists.

    This also handles legacy section tables where user_id is not UNIQUE.
    """
    fields = SECTION_FIELDS[section]
    table = TABLES[section]

    current = section_data(cursor, user_id, section)

    clean = {}

    for field in fields:
        if field in submitted:
            clean[field] = clean_value(submitted[field])
        else:
            clean[field] = current.get(field)

    cursor.execute(
        f"""
        SELECT 1
        FROM {table}
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )

    exists = cursor.fetchone() is not None

    if exists:
        assignments = ", ".join(
            f"{field} = %s"
            for field in fields
        )

        values = [
            clean[field]
            for field in fields
        ]

        values.append(user_id)

        # Keep any legacy duplicate rows synchronized.
        cursor.execute(
            f"""
            UPDATE {table}
            SET {assignments}
            WHERE user_id = %s
            """,
            tuple(values),
        )

    else:
        columns = ["user_id"] + fields

        placeholders = ", ".join(
            ["%s"] * len(columns)
        )

        values = [user_id] + [
            clean[field]
            for field in fields
        ]

        cursor.execute(
            f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({placeholders})
            """,
            tuple(values),
        )


def profile_payload(cursor, user_id):
    """Build the complete profile response expected by the frontend."""
    user = get_user_row(cursor, user_id)

    if not user:
        return None

    ensure_personal_info(cursor, user)

    cursor.execute(
        """
        SELECT
            full_name,
            email,
            mobile_number,
            date_of_birth,
            gender,
            state,
            category,
            district,
            annual_income
        FROM personal_info
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )

    personal = cursor.fetchone() or {}

    for key in CORE_USER_FIELDS:
        personal[key] = first_present(
            personal.get(key),
            user.get(key),
        )

    personal["category"] = first_present(
        personal.get("category"),
        user.get("category"),
    )

    # Keep the legacy dob response key for frontend compatibility.
    personal["dob"] = personal.get("date_of_birth")

    result = {
        "user_id": user_id,
        **personal,
        "age": age_from_dob(
            personal.get("date_of_birth")
        ),
        "education": section_data(
            cursor, user_id, "education"
        ),
        "employment": section_data(
            cursor, user_id, "employment"
        ),
        "location": section_data(
            cursor, user_id, "location"
        ),
        "income": section_data(
            cursor, user_id, "income"
        ),
    }

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM user_documents
        WHERE user_id = %s
        """,
        (user_id,),
    )

    result["document_count"] = (
        cursor.fetchone() or {}
    ).get("total", 0)

    completion_values = [
        personal.get(key)
        for key in (
            "full_name",
            "email",
            "mobile_number",
            "date_of_birth",
            "gender",
            "state",
            "category",
            "district",
        )
    ]

    completion_values.extend([
        result["education"].get("qualification_level"),
        result["location"].get("pincode"),
        result["income"].get("annual_income"),
    ])

    completed = sum(
        value not in (None, "")
        for value in completion_values
    )

    result["profile_completion"] = round(
        completed * 100 / len(completion_values)
    )

    return result


def close_database(conn, cursor):
    """Safely close database resources."""
    if cursor:
        try:
            cursor.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database cursor"
            )

    if conn:
        try:
            if conn.is_connected():
                conn.close()
        except Exception:
            current_app.logger.exception(
                "Failed to close database connection"
            )


# ---------------------------------------------------------
# GET COMPLETE USER PROFILE
# GET /api/user/profile
# ---------------------------------------------------------

@profile_bp.route("/api/user/profile", methods=["GET"])
def get_profile():
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        data = profile_payload(cursor, user_id)

        if data is None:
            conn.rollback()

            return jsonify({
                "message": "User not found."
            }), 404

        conn.commit()

        return jsonify(data), 200

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Failed to retrieve complete user profile"
        )

        return jsonify({
            "message": (
                "Unable to retrieve user profile. "
                "Check profile tables and column names."
            )
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# UPDATE USER PROFILE
# PUT /api/user/profile
# ---------------------------------------------------------

@profile_bp.route("/api/user/profile", methods=["PUT"])
def update_profile():
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "message": "A valid JSON object is required."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user = get_user_row(cursor, user_id)

        if not user:
            conn.rollback()

            return jsonify({
                "message": "User not found."
            }), 404

        ensure_personal_info(cursor, user)

        cursor.execute(
            """
            SELECT
                full_name,
                email,
                mobile_number,
                date_of_birth,
                gender,
                state,
                category,
                district,
                annual_income
            FROM personal_info
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

        existing = cursor.fetchone() or {}

        personal = payload.get("personal")

        if not isinstance(personal, dict):
            personal = {
                key: payload[key]
                for key in PERSONAL_FIELDS
                if key in payload
            }
        else:
            personal = dict(personal)

        # Merge submitted values with existing values.
        merged = {}

        for key in CORE_USER_FIELDS:
            if key == "date_of_birth":
                continue

            if key in personal:
                merged[key] = clean_value(personal[key])
            else:
                merged[key] = first_present(
                    existing.get(key),
                    user.get(key),
                )

        if "date_of_birth" in personal:
            submitted_dob = clean_value(
                personal["date_of_birth"]
            )
        else:
            submitted_dob = None

        merged["date_of_birth"] = first_present(
            submitted_dob,
            existing.get("date_of_birth"),
            user.get("date_of_birth"),
            user.get("dob"),
        )

        category = (
            clean_value(personal["category"])
            if "category" in personal
            else first_present(
                existing.get("category"),
                user.get("category"),
            )
        )

        district = (
            clean_value(personal["district"])
            if "district" in personal
            else existing.get("district")
        )

        annual_income = (
            clean_value(personal["annual_income"])
            if "annual_income" in personal
            else existing.get("annual_income")
        )

        full_name = merged.get("full_name")

        if not isinstance(full_name, str) or not full_name.strip():
            conn.rollback()

            return jsonify({
                "message": "Full name is required."
            }), 400

        # Validate date format before writing to MySQL.
        dob = merged.get("date_of_birth")

        if dob:
            try:
                if isinstance(dob, date):
                    parsed_dob = dob
                else:
                    parsed_dob = date.fromisoformat(
                        str(dob)[:10]
                    )

                if parsed_dob > date.today():
                    conn.rollback()

                    return jsonify({
                        "message": (
                            "Date of birth cannot be in the future."
                        )
                    }), 400

                merged["date_of_birth"] = parsed_dob

            except (ValueError, TypeError):
                conn.rollback()

                return jsonify({
                    "message": (
                        "Invalid date of birth. Use YYYY-MM-DD."
                    )
                }), 400

        columns = user.get(
            "__db_columns",
            set(user.keys()),
        )

        assignments = [
            "full_name = %s",
            "email = %s",
            "mobile_number = %s",
        ]

        user_values = [
            merged.get("full_name"),
            merged.get("email"),
            merged.get("mobile_number"),
        ]

        dob_column = (
            "date_of_birth"
            if "date_of_birth" in columns
            else "dob"
            if "dob" in columns
            else None
        )

        if dob_column:
            if not merged.get("date_of_birth"):
                conn.rollback()

                return jsonify({
                    "message": (
                        "Date of birth is required. "
                        "Please select your date of birth."
                    )
                }), 400

            assignments.append(
                f"{dob_column} = %s"
            )

            user_values.append(
                merged["date_of_birth"]
            )

        for column in ("gender", "state"):
            if column in columns:
                assignments.append(
                    f"{column} = %s"
                )

                user_values.append(
                    merged.get(column)
                )

        if "category" in columns:
            assignments.append("category = %s")
            user_values.append(category)

        user_values.append(user_id)

        cursor.execute(
            f"""
            UPDATE users
            SET {", ".join(assignments)}
            WHERE user_id = %s
            """,
            tuple(user_values),
        )

        cursor.execute(
            """
            INSERT INTO personal_info (
                user_id,
                full_name,
                email,
                mobile_number,
                date_of_birth,
                gender,
                state,
                category,
                district,
                annual_income
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                full_name = VALUES(full_name),
                email = VALUES(email),
                mobile_number = VALUES(mobile_number),
                date_of_birth = VALUES(date_of_birth),
                gender = VALUES(gender),
                state = VALUES(state),
                category = VALUES(category),
                district = VALUES(district),
                annual_income = VALUES(annual_income)
            """,
            (
                user_id,
                merged.get("full_name"),
                merged.get("email"),
                merged.get("mobile_number"),
                merged.get("date_of_birth"),
                merged.get("gender"),
                merged.get("state"),
                category,
                district,
                annual_income,
            ),
        )

        # Save only sections actually included in the request.
        for section in SECTION_FIELDS:
            if section not in payload:
                continue

            values = payload[section]

            if not isinstance(values, dict):
                conn.rollback()

                return jsonify({
                    "message": (
                        f"Invalid {section} details."
                    )
                }), 400

            save_section_without_unique_key(
                cursor,
                user_id,
                section,
                values,
            )

        conn.commit()

        return jsonify({
            "message": "Profile updated successfully."
        }), 200

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to save profile"
        )

        return jsonify({
            "message": (
                "Unable to save profile. Verify the profile "
                "schema, unique keys, and field names."
            )
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# LIST USER DOCUMENTS
# GET /api/user/documents
# ---------------------------------------------------------

@profile_bp.route("/api/user/documents", methods=["GET"])
def list_user_documents():
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                document_id,
                document_name,
                original_filename,
                file_size,
                uploaded_at
            FROM user_documents
            WHERE user_id = %s
            ORDER BY uploaded_at DESC, document_id DESC
            """,
            (user_id,),
        )

        documents = cursor.fetchall()

        return jsonify({
            "documents": documents
        }), 200

    except Exception:
        current_app.logger.exception(
            "Unable to list user documents"
        )

        return jsonify({
            "message": "Unable to retrieve documents."
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# DOWNLOAD A USER DOCUMENT
# GET /api/user/documents/<document_id>/download
# ---------------------------------------------------------

@profile_bp.route(
    "/api/user/documents/<int:document_id>/download",
    methods=["GET"],
)
def download_user_document(document_id):
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                original_filename,
                file_path
            FROM user_documents
            WHERE document_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (document_id, user_id),
        )

        doc = cursor.fetchone()

        if not doc:
            return jsonify({
                "message": "Document not found."
            }), 404

        stored_path = doc.get("file_path")

        if not stored_path:
            return jsonify({
                "message": "The stored document file is unavailable."
            }), 404

        path = os.path.realpath(stored_path)

        # This path must match the upload route's storage directory.
        allowed_root = os.path.realpath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "private_uploads",
                "user_documents",
            )
        )

        try:
            inside = (
                os.path.commonpath([path, allowed_root])
                == allowed_root
            )
        except ValueError:
            inside = False

        if not inside or not os.path.isfile(path):
            return jsonify({
                "message": "The stored document file is unavailable."
            }), 404

        filename = (
            os.path.basename(
                doc.get("original_filename") or "document.pdf"
            )
        )

        # Release the database connection before transferring the file.
        close_database(conn, cursor)
        conn = None
        cursor = None

        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
        )

    except Exception:
        current_app.logger.exception(
            "Unable to download user document"
        )

        return jsonify({
            "message": "Unable to download document."
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# USER NOTIFICATION UNREAD COUNT
# GET /api/user/notifications/unread-count
# ---------------------------------------------------------

@profile_bp.route(
    "/api/user/notifications/unread-count",
    methods=["GET"],
)
def unread_notification_count():
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM notifications
            WHERE user_id = %s
              AND is_read = 0
            """,
            (user_id,),
        )

        result = cursor.fetchone() or {
            "unread_count": 0
        }

        return jsonify(result), 200

    except Exception:
        current_app.logger.exception(
            "Unable to count notifications"
        )

        return jsonify({
            "message": "Unable to count notifications."
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# LIST USER NOTIFICATIONS
# GET /api/user/notifications
# ---------------------------------------------------------

@profile_bp.route(
    "/api/user/notifications",
    methods=["GET"],
)
def list_notifications():
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                notification_id,
                title,
                message,
                is_read,
                created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,),
        )

        return jsonify({
            "notifications": cursor.fetchall()
        }), 200

    except Exception:
        current_app.logger.exception(
            "Unable to list notifications"
        )

        return jsonify({
            "message": "Unable to retrieve notifications."
        }), 500

    finally:
        close_database(conn, cursor)


# ---------------------------------------------------------
# MARK A NOTIFICATION AS READ
# POST /api/user/notifications/<notification_id>/read
# ---------------------------------------------------------

@profile_bp.route(
    "/api/user/notifications/<int:notification_id>/read",
    methods=["POST"],
)
def mark_notification_read(notification_id):
    user_id = logged_in_user_id()

    if not user_id:
        return jsonify({
            "message": "Please log in first."
        }), 401

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT notification_id
            FROM notifications
            WHERE notification_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (notification_id, user_id),
        )

        notification = cursor.fetchone()

        if not notification:
            return jsonify({
                "message": "Notification not found."
            }), 404

        cursor.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE notification_id = %s
              AND user_id = %s
            """,
            (notification_id, user_id),
        )

        conn.commit()

        return jsonify({
            "message": "Notification marked as read."
        }), 200

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        current_app.logger.exception(
            "Unable to mark notification read"
        )

        return jsonify({
            "message": "Unable to update notification."
        }), 500

    finally:
        close_database(conn, cursor)
