from sqlalchemy import func

from . import db
import uuid
from werkzeug.security import generate_password_hash


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column('name', db.String())
    _password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    @property
    def password(self):
        raise ValueError

    @password.setter
    def set_password(self, pw):
        self._password_hash = generate_password_hash(pw)


class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.String(255), primary_key=True)
    name = db.Column('name', db.String())
    email = db.Column('email', db.String(), nullable=False)
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