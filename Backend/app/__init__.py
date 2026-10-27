
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_mail import Mail

from app.routes.auth_routes import auth_bp
from app.routes.admin_routes import admin_bp
from app.routes.adminscheme_routes import adminscheme_bp
from app.routes.profile_routes import profile_bp
from app.routes.schemes_routes import scheme_bp
from app.routes.settings_routes import settings_bp
from app.routes.userimp_routes import userimp_bp
from app.routes.adminsettings_routes import adminset_bp
from app.routes.notification_routes import notification_bp
from app.routes.admin_users_routes import adminusers_bp
from app.routes.admin_applications_routes import adminapplications_bp


mail = Mail()


def create_app():
    app = Flask(__name__)

    # Configure Flask session secret
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY")

    if not app.config["SECRET_KEY"]:
        raise RuntimeError("FLASK_SECRET_KEY is missing from .env")

    app.config["MAX_CONTENT_LENGTH"] = 55 * 1024 * 1024

    # Configure CORS for the frontend
    
    # Configure CORS for the frontend
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": [
                    "http://127.0.0.1:5500",
                    "http://localhost:5500",
                ],
                "methods": [
                    "GET", "POST", "PUT", "PATCH",
                    "DELETE", "OPTIONS",
                ],
                "allow_headers": [
                    "Content-Type", "Authorization",
                ],
            }
        },
        supports_credentials=True,
    )


    # Configure email
    app.config.update(
        MAIL_SERVER="smtp.gmail.com",
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_USERNAME"),
    )

    # Initialize Flask-Mail with this app
    mail.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(adminscheme_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(scheme_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(userimp_bp)
    app.register_blueprint(adminset_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(adminusers_bp)
    app.register_blueprint(adminapplications_bp)

    @app.route("/")
    def home():
        return jsonify({
            "message": "Scheme Finder Flask backend is running!"
        })

    return app
