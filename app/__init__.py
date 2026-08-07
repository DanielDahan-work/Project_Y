from flask import Flask
from app.config import Config
from app.routes import register_blueprints


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)

    register_blueprints(app)

    return app