
import os
import uuid
import json
import re
from datetime import date

from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from app.database.connection import get_db_connection
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


auth_bp = Blueprint("auth", __name__)

# Store documents outside public/static directories.
UPLOAD_FOLDER = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "private_uploads",
        "user_documents",
    )
)

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_DOCUMENTS = 10
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024


# =========================================
# Shared helpers
# =========================================

def close_database_resources(cursor=None, connection=None):
    """Close database resources without hiding the original error."""
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            current_app.logger.warning(
                "Could not close database cursor.", exc_info=True
            )

    if connection is not None:
        try:
            connection.close()
        except Exception:
            current_app.logger.warning(
                "Could not close database connection.", exc_info=True
            )


def get_reset_serializer():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("Flask SECRET_KEY is not configured.")

    return URLSafeTimedSerializer(secret_key)


def valid_email(email):
    if not email or len(email) > 150:
        return False

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    )


def valid_mobile(mobile):
    return bool(re.fullmatch(r"\d{10}", mobile or ""))


def parse_date_of_birth(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed >= date.today():
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def parse_bool(value):
    """Parse boolean values stored as JSON, strings, or database numbers."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value == 1

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off", ""):
            return False

        try:
            return parse_bool(json.loads(value))
        except (ValueError, TypeError):
            return False

    return False


# =========================================
# Notify admins about new user registration
# =========================================

def notify_admin_new_registration(cursor, user_id, full_name, contact):
    """
    Support the preferences schema:
      admin_settings(admin_id, setting_key, setting_value)
      setting_key = 'notifications'
      setting_value = JSON object containing new_user_registration

    Also support legacy rows where setting_key itself is
    'new_user_registration'.

    Create an alert if at least one admin has enabled this preference.
    """

    cursor.execute(
        """
        SELECT setting_value
        FROM admin_settings
        WHERE setting_key IN (%s, %s)
        """,
        ("notifications", "new_user_registration"),
    )

    rows = cursor.fetchall()
    enabled = False

    for row in rows:
        raw_value = row[0]

        # A legacy row may store the preference directly.
        if isinstance(raw_value, str):
            try:
                raw_value = json.loads(raw_value)
            except (ValueError, TypeError):
                pass

        if isinstance(raw_value, dict):
            if parse_bool(raw_value.get("new_user_registration")):
                enabled = True
                break
        elif parse_bool(raw_value):
            enabled = True
            break

    if not enabled:
        return False

    message = f"New user registered: {full_name} ({contact})."

    cursor.execute(
        """
        INSERT INTO admin_newnotifications
            (user_id, message, notification_type, is_read, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (user_id, message, "new_registration", 0),
    )

    return True


# =========================================
# Register
# =========================================

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    full_name = request.form.get("full_name", "").strip()
    contact = request.form.get("contact", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    dob_input = request.form.get("date_of_birth", "").strip()
    gender = request.form.get("gender", "").strip()
    category = request.form.get("category", "").strip()
    state = request.form.get("state", "").strip()

    if not all([
        full_name, contact, password, confirm_password,
        dob_input, gender, category, state,
    ]):
        return jsonify({
            "message": "Please fill in all required fields."
        }), 400

    if len(full_name) > 150:
        return jsonify({"message": "Name is too long."}), 400

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({
            "message": "Password must be at least 8 characters."
        }), 400

    if len(password) > MAX_PASSWORD_LENGTH:
        return jsonify({"message": "Password is too long."}), 400

    if password != confirm_password:
        return jsonify({"message": "Passwords do not match."}), 400

    parsed_dob = parse_date_of_birth(dob_input)
    if parsed_dob is None:
        return jsonify({
            "message": "Enter a valid date of birth in the past."
        }), 400

    if len(gender) > 30 or len(category) > 100 or len(state) > 100:
        return jsonify({"message": "One or more fields are too long."}), 400

    if "@" in contact:
        email = contact.lower()
        mobile = None

        if not valid_email(email):
            return jsonify({"message": "Enter a valid email address."}), 400
    else:
        email = None
        mobile = contact

        if not valid_mobile(mobile):
            return jsonify({
                "message": "Enter a valid email or 10-digit mobile number."
            }), 400

    document_names = request.form.getlist("document_names")
    document_files = request.files.getlist("documents")

    if len(document_names) != len(document_files):
        return jsonify({
            "message": "Each document must have a name and a PDF file."
        }), 400

    if len(document_files) > MAX_DOCUMENTS:
        return jsonify({
            "message": "You can upload a maximum of 10 documents."
        }), 400

    documents = []

    for name, uploaded_file in zip(document_names, document_files):
        name = name.strip()

        if not name or len(name) > 100:
            return jsonify({
                "message": "Each document name must contain 1–100 characters."
            }), 400

        original_filename = secure_filename(uploaded_file.filename or "")

        if not original_filename:
            return jsonify({
                "message": "Please select a PDF for every document name."
            }), 400

        if not original_filename.lower().endswith(".pdf"):
            return jsonify({
                "message": "Only PDF documents are allowed."
            }), 400

        uploaded_file.stream.seek(0, os.SEEK_END)
        file_size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0)

        if file_size == 0:
            return jsonify({
                "message": f"{original_filename} is empty."
            }), 400

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "message": f"{original_filename} exceeds the 5 MB limit."
            }), 400

        # This signature check does not prove the PDF is safe.
        if uploaded_file.stream.read(5) != b"%PDF-":
            uploaded_file.stream.seek(0)
            return jsonify({
                "message": f"{original_filename} is not a valid PDF."
            }), 400

        uploaded_file.stream.seek(0)

        documents.append({
            "name": name,
            "file": uploaded_file,
            "original_filename": original_filename,
            "file_size": file_size,
        })

    connection = None
    cursor = None
    saved_paths = []

    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users
                (full_name, email, mobile_number, password_hash,
                 date_of_birth, gender, category, state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                email,
                mobile,
                generate_password_hash(password),
                parsed_dob,
                gender,
                category,
                state,
            ),
        )

        user_id = cursor.lastrowid

        notify_admin_new_registration(
            cursor, user_id, full_name, contact
        )

        for document in documents:
            stored_filename = f"{uuid.uuid4().hex}.pdf"
            destination = os.path.join(UPLOAD_FOLDER, stored_filename)

            document["file"].save(destination)
            saved_paths.append(destination)

            cursor.execute(
                """
                INSERT INTO user_documents
                    (user_id, document_name, original_filename,
                     stored_filename, file_path, file_size)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    document["name"],
                    document["original_filename"],
                    stored_filename,
                    destination,
                    document["file_size"],
                ),
            )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Registration successful!",
        }), 201

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                current_app.logger.warning(
                    "Registration rollback failed.", exc_info=True
                )

        for path in saved_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                current_app.logger.warning(
                    "Could not remove an uploaded file after failure.",
                    exc_info=True,
                )

        if getattr(error, "errno", None) == 1062:
            return jsonify({
                "message": "This email or mobile number is already registered."
            }), 409

        current_app.logger.exception("Registration failed")
        return jsonify({
            "message": "Registration failed. Please try again."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# =========================================
# Login
# =========================================

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    identifier = data.get("identifier", "")
    password = data.get("password", "")

    if not isinstance(identifier, str) or not isinstance(password, str):
        return jsonify({"message": "Invalid login details."}), 400

    identifier = identifier.strip()

    if not identifier or not password:
        return jsonify({
            "message": "Enter your email/mobile number and password."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, full_name, email, mobile_number, password_hash
            FROM users
            WHERE email = %s OR mobile_number = %s
            LIMIT 1
            """,
            (
                identifier.lower() if "@" in identifier else identifier,
                identifier,
            ),
        )

        user = cursor.fetchone()

        if not user or not check_password_hash(
            user["password_hash"], password
        ):
            return jsonify({
                "message": "Invalid email/mobile number or password."
            }), 401

        # Prevent a previous admin/user identity from persisting.
        session.clear()
        session["user_id"] = user["user_id"]
        session["user_name"] = user["full_name"]
        session["role"] = "user"

        response = jsonify({
            "success": True,
            "message": "Login successful.",
            "redirect": "dashboard.html",
        })
        response.headers["Cache-Control"] = "no-store"
        return response, 200

    except Exception:
        current_app.logger.exception("Login failed")
        return jsonify({
            "message": "Login failed due to a server error."
        }), 500

    finally:
        close_database_resources(cursor, connection)


# =========================================
# Logout
# =========================================

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()

    response = jsonify({
        "success": True,
        "message": "Logged out successfully.",
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


# =========================================
# Check session
# =========================================

@auth_bp.route("/api/auth/session", methods=["GET"])
def check_session():
    user_id = session.get("user_id")
    is_user = bool(user_id and session.get("role") == "user")

    response = jsonify({
        "authenticated": is_user,
        "role": "user" if is_user else None,
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


# =========================================
# Forgot password
# =========================================

@auth_bp.route("/api/auth/forgot-password", methods=["POST"])
def request_password_reset():
    connection = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        contact = data.get("contact", "")

        if not isinstance(contact, str):
            return jsonify({
                "success": False,
                "message": "Enter your registered email address.",
            }), 400

        contact = contact.strip().lower()

        if not valid_email(contact):
            return jsonify({
                "success": False,
                "message": "Enter a valid email address.",
            }), 400

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, email
            FROM users
            WHERE email = %s
            LIMIT 1
            """,
            (contact,),
        )
        user = cursor.fetchone()

        # Use the same response whether the email exists or not.
        response = jsonify({
            "success": True,
            "message": (
                "If the email is registered, a password-reset "
                "link will be sent."
            ),
        })

        if not user:
            return response, 200

        mail = current_app.extensions.get("mail")
        if mail is None:
            raise RuntimeError("Flask-Mail is not initialized.")

        token = get_reset_serializer().dumps({
            "user_id": user["user_id"],
            "purpose": "password-reset",
        })

        frontend_url = current_app.config.get("FRONTEND_RESET_URL")
        if not frontend_url:
            raise RuntimeError(
                "FRONTEND_RESET_URL must be configured."
            )

        separator = "&" if "?" in frontend_url else "?"
        reset_link = f"{frontend_url}{separator}token={token}"

        message = Message(
            subject="Scheme Finder - Reset your password",
            recipients=[user["email"]],
            body=(
                "We received a request to reset your Scheme Finder password.\n\n"
                f"Reset your password using this link:\n{reset_link}\n\n"
                "This link expires in 15 minutes. If you did not request "
                "this, ignore this email."
            ),
        )

        mail.send(message)
        return response, 200

    except Exception:
        current_app.logger.exception("Password reset request failed")
        return jsonify({
            "success": False,
            "message": "Unable to process the request right now.",
        }), 500

    finally:
        close_database_resources(cursor, connection)


# =========================================
# Reset password
# =========================================

@auth_bp.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    new_password = data.get("new_password", "")

    if not isinstance(token, str) or not isinstance(new_password, str):
        return jsonify({
            "success": False,
            "message": "Invalid reset request.",
        }), 400

    token = token.strip()

    if (
        not token
        or len(new_password) < MIN_PASSWORD_LENGTH
        or len(new_password) > MAX_PASSWORD_LENGTH
    ):
        return jsonify({
            "success": False,
            "message": (
                "A valid reset link and a password between "
                "8 and 1024 characters are required."
            ),
        }), 400

    try:
        payload = get_reset_serializer().loads(token, max_age=900)
    except SignatureExpired:
        return jsonify({
            "success": False,
            "message": "This reset link has expired. Please request another.",
        }), 400
    except BadSignature:
        return jsonify({
            "success": False,
            "message": "This reset link is invalid.",
        }), 400

    if (
        not isinstance(payload, dict)
        or payload.get("purpose") != "password-reset"
        or not payload.get("user_id")
    ):
        return jsonify({
            "success": False,
            "message": "Invalid reset request.",
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (
                generate_password_hash(new_password),
                payload["user_id"],
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return jsonify({
                "success": False,
                "message": "Unable to update the password.",
            }), 400

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Password changed successfully. Please log in.",
        }), 200

    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                current_app.logger.warning(
                    "Password-reset rollback failed.", exc_info=True
                )

        current_app.logger.exception("Password update failed")
        return jsonify({
            "success": False,
            "message": "Unable to update the password right now.",
        }), 500

    finally:
        close_database_resources(cursor, connection)
