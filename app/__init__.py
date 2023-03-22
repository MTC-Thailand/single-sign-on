import os

from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flasgger import Swagger
from flask_migrate import Migrate

from app.api.views import CMTEScore

admin = Admin()
migrate = Migrate()
db = SQLAlchemy()
swagger = Swagger()

from app.api import api_bp

api = Api(api_bp)

api.add_resource(CMTEScore, '/<int:lic_id>/cmte/scores')


def create_app(config):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
    admin.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    app.register_blueprint(api_bp)
    swagger.init_app(app)

    return app