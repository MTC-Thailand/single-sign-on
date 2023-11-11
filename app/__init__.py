import os

from flask import Flask, render_template
from flask_restful import Api
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_admin import Admin, AdminIndexView
from flasgger import Swagger
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

from app.api.views import CMTEScore, Login, RefreshToken, MemberInfo


class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated


admin = Admin(index_view=MyAdminIndexView())
migrate = Migrate()
db = SQLAlchemy()
swagger = Swagger()
jwt = JWTManager()
login_manager = LoginManager()
login_manager.login_view = 'users.login'


from app.api import api_bp

api = Api(api_bp)

api.add_resource(Login, '/auth/login')
api.add_resource(CMTEScore, '/members/<int:lic_id>/cmte/scores')
api.add_resource(MemberInfo, '/members/<string:pin>/info')
api.add_resource(RefreshToken, '/auth/refresh')


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
    database_url = os.environ.get('DATABASE_URL')

    if database_url.startswith('postgresql'):
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres', 'postgresql')

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    admin.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    app.register_blueprint(api_bp)
    swagger.init_app(app)
    login_manager.init_app(app)

    from app.user import user_bp
    app.register_blueprint(user_bp)

    from app.members import member_blueprint
    app.register_blueprint(member_blueprint)

    @app.route('/')
    def index():
        return render_template('index.html')

    return app
