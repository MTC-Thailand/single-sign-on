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
    _api_key = db.Column(db.String(), nullable=False)
    is_valid = db.Column(db.Boolean(), default=True)
    creator_id = db.Column(db.ForeignKey('users.id'))
    creator = db.relationship(User, backref=db.backref('clients',
                                                       lazy='dynamic',
                                                       cascade='all, delete-orphan'))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    @property
    def api_key(self):
        return self._api_key

    @api_key.setter
    def set_api_key(self):
        raise ValueError

    def generate_api_key(self):
        key = uuid.uuid4()
        self._api_key = generate_password_hash(str(key))
        return key