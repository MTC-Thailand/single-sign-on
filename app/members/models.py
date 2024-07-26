from datetime import datetime, date

import arrow

from app import db


class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False)
    th_firstname = db.Column(db.String(), nullable=False)
    th_lastname = db.Column(db.String(), nullable=False)
    en_firstname = db.Column(db.String(), nullable=False)
    en_lastname = db.Column(db.String(), nullable=False)
    dob = db.Column(db.Date())
    pid = db.Column(db.String(), nullable=False, unique=True)
    email = db.Column(db.String(), unique=True)
    tel = db.Column(db.String(), unique=True)

    def __str__(self):
        return self.number

    @property
    def valid_license(self):
        today = arrow.now('Asia/Bangkok').date()
        return self.licenses.filter(License.end_date>=today).first()

    @property
    def th_fullname(self):
        return f'{self.th_firstname} {self.th_lastname}'

    @property
    def en_fullname(self):
        return f'{self.en_firstname} {self.en_lastname}'


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
