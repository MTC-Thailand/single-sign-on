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

load_dotenv()


class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and admin_permission.can()


admin_ext = Admin(index_view=MyAdminIndexView())
admin = admin_ext
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
api_resources_registered = False


def create_app():
    global api_resources_registered

    app = Flask(__name__)
    app.config['DEBUG'] = os.environ.get('FLASK_DEBUG') == '1'
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")
    app.config['TESTING'] = os.environ.get('TESTING') == '1'
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    public_base_url = os.environ.get('PUBLIC_BASE_URL')
    default_secure_cookies = bool(public_base_url and public_base_url.lower().startswith('https://'))
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    # Auto-enable secure cookies when PUBLIC_BASE_URL is HTTPS; env var can still override.
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get(
        'SESSION_COOKIE_SECURE',
        '1' if default_secure_cookies else '0'
    ) == '1'
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
    app.config['REMEMBER_COOKIE_SECURE'] = os.environ.get(
        'REMEMBER_COOKIE_SECURE',
        '1' if default_secure_cookies else '0'
    ) == '1'
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = ('MTC Web Services', os.environ.get('MAIL_USERNAME'))
    app.config['PUBLIC_BASE_URL'] = public_base_url
    database_url = os.environ.get('DATABASE_URL')

    if database_url.startswith('postgresql'):
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = \
            os.environ.get('DATABASE_URL').replace('postgres', 'postgresql')

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    admin_ext.init_app(app)
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
    globals()['admin'] = admin_ext
    app.register_blueprint(webadmin_blueprint)

    from app.api.views import (Login,
                               CMTEScore,
                               MemberAddressResource,
                               MemberEducationResource,
                               MemberExpertiseResource,
                               MemberInfo,
                               MemberLicenseRegistrationResource,
                               MemberRegistrationResource,
                               MemberPID,
                               MemberPIDPhoneNumber,
                               MemberLicense,
                               RefreshToken,
                               CMTEFeePaymentResource,
                               CMTEEventResource)

    if not api_resources_registered:
        api.add_resource(Login, '/auth/login')
        api.add_resource(CMTEEventResource, '/cmte/upcoming-events')
        api.add_resource(CMTEScore, '/members/<string:lic_id>/cmte/scores')
        api.add_resource(MemberPID, '/members/pids/<string:pid>')
        api.add_resource(MemberLicense, '/members/licenses/<string:license_number>')
        api.add_resource(MemberLicenseRegistrationResource, '/members/licenses/registration')
        api.add_resource(MemberRegistrationResource, '/members/registration')
        api.add_resource(MemberEducationResource, '/members/education', '/members/<string:pin>/education')
        api.add_resource(MemberExpertiseResource, '/members/expertise', '/members/<string:pin>/expertise')
        api.add_resource(MemberInfo, '/members/<string:pin>/info')
        api.add_resource(MemberAddressResource, '/members/<string:pin>/addresses')
        api.add_resource(RefreshToken, '/auth/refresh')
        api.add_resource(CMTEFeePaymentResource, '/members/<string:lic_no>/cmte-fee-payment-record')
        api.add_resource(MemberPIDPhoneNumber, '/members/<string:pid>/check-info', '/members/<string:pid>/phone/<string:phone>/info')
        api_resources_registered = True

    app.register_blueprint(api_bp)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.after_request
    def set_security_headers(response):
        # Prevent intermediary caches from storing authenticated/dynamic responses.
        response.headers.setdefault('Cache-Control', 'no-store, private')
        response.headers.setdefault('Pragma', 'no-cache')
        return response

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
