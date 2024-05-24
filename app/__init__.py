import os

import arrow
from pytz import timezone

from flask import Flask, render_template
from flask_restful import Api
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_admin import Admin, AdminIndexView
from flask_wtf.csrf import CSRFProtect
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
csrf = CSRFProtect()
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
    csrf.init_app(app)

    from app.user import user_bp
    app.register_blueprint(user_bp)

    from app.members import member_blueprint
    app.register_blueprint(member_blueprint)

    from app.cmte import cmte_bp as cmte_blueprint
    app.register_blueprint(cmte_blueprint)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.template_filter("localdatetime")
    def local_datetime(dt):
        bangkok = timezone('Asia/Bangkok')
        datetime_format = '%d/%m/%Y %X'
        if dt:
            if dt.tzinfo:
                return dt.astimezone(bangkok).strftime(datetime_format)
        else:
            return None

    @app.template_filter("localdate")
    def local_date(dt):
        datetime_format = '%d/%m/%Y'
        if dt:
            return dt.strftime(datetime_format)
        else:
            return None

    @app.template_filter("humanizedate")
    def humanize_date(dt):
        if dt:
            return arrow.get(dt).humanize(locale='th', granularity='day')
        else:
            return None

    return app
