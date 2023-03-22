import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_migrate import Migrate

admin = Admin()
migrate = Migrate()
db = SQLAlchemy()


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)
    admin.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)

    return app