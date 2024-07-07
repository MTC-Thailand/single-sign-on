from sqlalchemy import func

from . import db, login_manager
from flask_login import UserMixin
import uuid
import secrets
import string
from werkzeug.security import generate_password_hash

alphabet = string.digits


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column('name', db.String(), unique=True, nullable=False)
    _password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    @property
    def password(self):
        raise ValueError

    @password.setter
    def set_password(self, pw):
        self._password_hash = generate_password_hash(pw)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.String(255), primary_key=True)
    name = db.Column('name', db.String(), unique=True)
    email = db.Column('email', db.String(), nullable=False, unique=True)
    company = db.Column('company', db.String(), nullable=True)
    _secret = db.Column('secret', db.String(), nullable=False)
    is_valid = db.Column(db.Boolean(), default=True)
    creator_id = db.Column(db.ForeignKey('users.id'))
    creator = db.relationship(User, backref=db.backref('clients',
                                                       lazy='dynamic',
                                                       cascade='all, delete-orphan'))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    @property
    def client_secret(self):
        return self._secret

    @client_secret.setter
    def set_client_secret(self):
        raise ValueError

    def generate_client_secret(self):
        key = uuid.uuid4()
        self._secret = generate_password_hash(str(key))
        return key

    def generate_client_id(self):
        self.id = ''.join(secrets.choice(alphabet) for i in range(16))
