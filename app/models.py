from sqlite3 import ProgrammingError

from flask import request
from flask_principal import Permission
from sqlalchemy import func

from . import db, login_manager
from flask_login import UserMixin
import uuid
import secrets
import string
from werkzeug.security import generate_password_hash

from .members.models import Member

alphabet = string.digits


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column('name', db.String(), unique=True, nullable=False, info={'label': 'Username'})
    _password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    is_activated = db.Column('is_activated', db.Boolean(), default=False)

    @property
    def is_active(self):
        return self.is_activated

    @property
    def password(self):
        raise ValueError

    @password.setter
    def password(self, pw):
        self._password_hash = generate_password_hash(pw)

    def __str__(self):
        return self.username

    @property
    def unique_id(self):
        return f'admin-{self.id}'


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


user_roles = db.Table('user_roles',
                      db.Column('user_id', db.Integer(), db.ForeignKey('users.id')),
                      db.Column('role_id', db.Integer(), db.ForeignKey('roles.id')))


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer(), primary_key=True)
    role_need = db.Column('role_need', db.String(), nullable=True)
    action_need = db.Column('action_need', db.String())
    resource_id = db.Column('resource_id', db.Integer())

    users = db.relationship('User',
                            backref=db.backref('roles'),
                            secondary=user_roles, lazy='dynamic')

    def to_tuple(self):
        return self.role_need, self.action_need, self.resource_id

    def __str__(self):
        return u'Role {}: can {} -> resource ID {}'.format(self.role_need, self.action_need, self.resource_id)
