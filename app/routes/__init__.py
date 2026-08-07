from app.routes.home import home_bp
from app.routes.architecture import architecture_bp
from app.routes.dashboard import dashboard_bp
from app.routes.servers import servers_bp
from app.routes.auth import auth_bp


def register_blueprints(app):

    app.register_blueprint(home_bp)
    app.register_blueprint(architecture_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(auth_bp)