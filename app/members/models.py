from datetime import datetime, date

import arrow
from flask_login import UserMixin

from app import db


class Member(db.Model, UserMixin):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False)
    th_title = db.Column('th_title', db.String())
    th_firstname = db.Column(db.String(), nullable=False)
    th_lastname = db.Column(db.String(), nullable=False)
    en_title = db.Column('en_title', db.String())
    en_firstname = db.Column(db.String(), nullable=False)
    en_lastname = db.Column(db.String(), nullable=False)
    dob = db.Column(db.Date())
    pid = db.Column(db.String(), nullable=False, unique=True)
    email = db.Column(db.String(), unique=True)
    tel = db.Column(db.String(), unique=True)
    username = db.Column(db.String())
    password = db.Column(db.String())

    def __str__(self):
        return self.th_fullname

    @property
    def valid_license(self):
        today = arrow.now('Asia/Bangkok').date()
        return self.licenses.filter(License.end_date >= today).first()

    @property
    def license_number(self):
        if self.licenses:
            return self.licenses[-1].number
        return None

    @property
    def th_fullname(self):
        return f'{self.th_firstname} {self.th_lastname}'

    @property
    def en_fullname(self):
        return f'{self.en_firstname} {self.en_lastname}'

    @property
    def unique_id(self):
        return f'mtc-member-{self.id}'

    def check_password(self, password):
        return self.password == password


class License(db.Model):
    __tablename__ = 'licenses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False)
    issue_date = db.Column(db.Date(), nullable=False)
    start_date = db.Column(db.Date(), nullable=False)
    end_date = db.Column(db.Date(), nullable=False)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))
    member = db.relationship(Member, backref=db.backref('licenses',
                                                        lazy='dynamic',
                                                        order_by='License.end_date.desc()'))

    def __str__(self):
        return f'{self.number}: {self.end_date}'

    def get_active_cmte_fee_payment(self):
        record = self.cmte_fee_payment_records.filter_by(end_date=self.end_date).first()
        return record if record else None

    @property
    def pending_individual_cmte_records(self):
        return self.cmte_records.filter_by(approved_date=None, individual=True)

    @property
    def pending_cmte_records(self):
        return self.cmte_records.filter_by(approved_date=None)
