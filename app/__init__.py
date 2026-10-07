from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from app.config import Config


db = SQLAlchemy()
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user and user.email_verification_required and not user.email_verified:
        return None
    return user


def create_app(test_config=None):

    app = Flask(__name__)

    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.routes import register_blueprints

    register_blueprints(app)

    from app.email_migration import migrate_email_verification
    app.cli.add_command(migrate_email_verification)

    return app
