import os

import arrow
from flask_principal import Principal, PermissionDenied, ActionNeed
from flask_restful import Api
from pytz import timezone

from flask import Flask, render_template
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_admin import Admin, AdminIndexView
from flask_wtf.csrf import CSRFProtect
from flasgger import Swagger
from flask_migrate import Migrate
from flask_mail import Mail, Message
from dotenv import load_dotenv

from app.api.views import MemberPIDPhoneNumber

load_dotenv()


class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and admin_permission.can()


admin = Admin(index_view=MyAdminIndexView())
migrate = Migrate()
db = SQLAlchemy()
swagger = Swagger()
jwt = JWTManager()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = 'users.login'
login_manager.blueprint_login_views = {
    'member': 'member.login',
    'cmte': 'cmte.sponsor_member_login',
}
login_manager.login_message = 'กรุณาลงชื่อเข้าใช้งานระบบ'
login_manager.login_message_category = 'info'
principal = Principal()
mail = Mail()


def send_mail(recp, title, message):
    message = Message(subject=title, body=message, recipients=recp)
    mail.send(message)


from flask_principal import Permission, RoleNeed

admin_permission = Permission(RoleNeed('Admin'))
cmte_admin_permission = Permission(RoleNeed('CMTEAdmin'))
cmte_sponsor_admin_permission = Permission(RoleNeed('CMTESponsorAdmin'))
sponsor_event_management_permission = Permission(ActionNeed('manageEvents'))

from app.api import api_bp

api = Api(api_bp, decorators=[csrf.exempt])


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = ('MTC Web Services', os.environ.get('MAIL_USERNAME'))
    database_url = os.environ.get('DATABASE_URL')

    if database_url.startswith('postgresql'):
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = \
            os.environ.get('DATABASE_URL').replace('postgres', 'postgresql')

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    admin.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    swagger.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    principal.init_app(app)
    mail.init_app(app)

    from app.members import member_blueprint
    app.register_blueprint(member_blueprint)

    from app.cmte import cmte_bp as cmte_blueprint
    app.register_blueprint(cmte_blueprint)

    from app.user import user_bp
    app.register_blueprint(user_bp)

    from app.institutions import inst as institution_blueprint
    app.register_blueprint(institution_blueprint)

    from app.admin import webadmin as webadmin_blueprint
    app.register_blueprint(webadmin_blueprint)

    from app.api.views import (Login,
                               CMTEScore,
                               MemberInfo,
                               MemberPID,
                               MemberLicense,
                               RefreshToken,
                               CMTEFeePaymentResource,
                               CMTEEventResource)

    api.add_resource(Login, '/auth/login')
    api.add_resource(CMTEEventResource, '/cmte/upcoming-events')
    api.add_resource(CMTEScore, '/members/<string:lic_id>/cmte/scores')
    api.add_resource(MemberPID, '/members/pids/<string:pid>')
    api.add_resource(MemberLicense, '/members/licenses/<string:license_number>')
    api.add_resource(MemberInfo, '/members/<string:pin>/info')
    api.add_resource(RefreshToken, '/auth/refresh')
    api.add_resource(CMTEFeePaymentResource, '/members/<string:lic_no>/cmte-fee-payment-record')
    api.add_resource(MemberPIDPhoneNumber, '/members/<string:pid>/phone/<string:phone>/info')

    app.register_blueprint(api_bp)

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
            return arrow.get(dt).to('Asia/Bangkok').humanize(locale='th', granularity=['year', 'day'])
        else:
            return None

    @app.errorhandler(403)
    def page_not_found(e):
        return render_template('errors/403.html', error=e), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html', error=e), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html', error=e), 500

    @app.errorhandler(PermissionDenied)
    def permission_denied(e):
        return render_template('errors/403.html', error=e), 403

    return app
