import datetime

from flask_login import UserMixin
from sqlalchemy_utils import EmailType
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.validators import DataRequired

from app import db

event_type_fee_rates = db.Table('cmte_event_type_fee_assoc',
                                db.Column('event_type_id', db.Integer,
                                          db.ForeignKey('cmte_event_types.id')),
                                db.Column('fee_rate_id', db.Integer,
                                          db.ForeignKey('cmte_event_fee_rates.id'))
                                )


class CMTEEventSponsor(db.Model):
    __tablename__ = 'cmte_event_sponsors'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    old_id = db.Column(db.Integer)
    name = db.Column('name', db.String(), nullable=False, info={'label': 'ชื่อสถาบัน'})
    code = db.Column('code', db.String(), info={'label': 'รหัสสถาบัน'})
    affiliation = db.Column('affiliation', db.String(), info={'label': 'สังกัด'})
    address = db.Column('address', db.Text(), info={'label': 'ที่อยู่'})
    zipcode = db.Column('zipcode', db.String(), info={'label': 'รหัสไปรษณีย์'})
    telephone = db.Column('telephone', db.String(), info={'label': 'หมายเลขโทรศัพท์'})
    registered_datetime = db.Column('registered_datetime', db.DateTime(timezone=True))
    expire_date = db.Column('expire_date', db.Date())

    def __str__(self):
        return self.name


class CMTESponsorMember(UserMixin, db.Model):
    __tablename__ = 'cmte_sponsor_members'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    title = db.Column('title', db.String(), info={'label': 'คำนำหน้า'})
    firstname = db.Column('firstname', db.String(), info={'label': 'ชื่อ', 'validators': [DataRequired()]})
    lastname = db.Column('lastname', db.String(), info={'label': 'นามสกุล', 'validators': [DataRequired()]})
    email = db.Column('email', EmailType(), info={'label': 'E-mail', 'validators': [DataRequired()]})
    _password_hash = db.Column(db.String(255))
    mobile_phone = db.Column('mobile_phone', db.String(), info={'label': 'โทรศัพท์มือถือ'})
    telephone = db.Column('telephone', db.String(), info={'label': 'โทรศัพท์'})
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship(CMTEEventSponsor, backref=db.backref('members', lazy='dynamic', cascade="all, delete-orphan"))
    is_coordinator = db.Column('is_coordinator', db.Boolean(), default=False)

    def verify_password(self, password):
        return check_password_hash(self._password_hash, password)

    @property
    def password(self):
        raise ValueError

    @password.setter
    def password(self, pw):
        self._password_hash = generate_password_hash(pw)

    def __str__(self):
        return f'{self.firstname} {self.lastname}'

    @property
    def unique_id(self):
        return f'sponsor-member-{self.id}'


class CMTEEventCategory(db.Model):
    __tablename__ = 'cmte_event_categories'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    name = db.Column('name', db.String(255), unique=True, nullable=False)

    def __str__(self):
        return self.name


class CMTEEventType(db.Model):
    __tablename__ = 'cmte_event_types'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    name = db.Column('name', db.String(255), unique=True, nullable=False)
    for_group = db.Column('for_group', db.Boolean(), default=False)
    is_sponsored = db.Column('is_sponsored', db.Boolean(), default=False)
    category_id = db.Column('category_id', db.Integer, db.ForeignKey('cmte_event_categories.id'))
    category = db.relationship('CMTEEventCategory', backref=db.backref('types'))
    submission_due = db.Column('submission_due', db.Integer(), default=30)
    max_score = db.Column('max_score', db.Integer(), default=25)
    score_criteria = db.Column('score_criteria', db.String())
    fee_rates = db.relationship('CMTEEventFeeRate', secondary=event_type_fee_rates, backref=db.backref('event_types'))
    desc = db.Column('desc', db.Text(), info={'label': 'รายละเอียด'})

    def __str__(self):
        return self.name


class CMTEEventFormat(db.Model):
    __tablename__ = 'cmte_event_formats'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    format = db.Column('format', db.String(255), nullable=False)

    def __str__(self):
        return self.format


class CMTEEventFeeRate(db.Model):
    __tablename__ = 'cmte_event_fee_rates'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    max_participants = db.Column('max_participants', db.Integer())
    fee_rate = db.Column('fee_rate', db.Numeric())
    is_online = db.Column('is_online', db.Boolean(), default=False, info={'label': 'รูปแบบออนไลน์'})
    desc = db.Column('desc', db.Text())

    def __str__(self):
        format = 'รูปแบบ Online' if self.is_online else 'รูปแบบ Onsite'
        if self.fee_rate and self.max_participants:
            return f'{format} ไม่เกิน {self.max_participants} คน: {self.fee_rate} บาท'
        elif self.fee_rate:
            return f'{format}: {self.fee_rate} บาท'
        elif self.max_participants:
            return f'{format} ไม่เกิน {self.max_participants} คน: ไม่มีค่าธรรมเนียม'
        else:
            return f'{format} ไม่มีค่าธรรมเนียม'


class CMTEEventCode(db.Model):
    __tablename__ = 'cmte_event_codes'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    prefix = db.Column('prefix', db.String())
    number = db.Column('number', db.Integer())

    def __str__(self):
        return f'{self.prefix}{self.number:04}'

    def increment(self):
        self.number = self.number + 1


class CMTEEvent(db.Model):
    __tablename__ = 'cmte_events'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    main_event_id = db.Column('parent_id', db.Integer, db.ForeignKey('cmte_events.id'))
    sub_events = db.relationship('CMTEEvent', backref=db.backref('main_event', remote_side=[id]))
    title = db.Column('title', db.String(), nullable=False, info={'label': 'ชื่อกิจกรรม'})
    venue = db.Column('venue', db.Text(), info={'label': 'สถานที่จัดงาน'})
    event_type_id = db.Column('event_type_id', db.Integer, db.ForeignKey('cmte_event_types.id'))
    event_type = db.relationship('CMTEEventType', backref=db.backref('events'))
    start_date = db.Column('start_date', db.DateTime(timezone=True), info={'label': 'เริ่มต้น'})
    end_date = db.Column('end_date', db.DateTime(timezone=True), info={'label': 'สิ้นสุด'})
    submitted_datetime = db.Column('submitted_datetime', db.DateTime(timezone=True), info={'label': 'วันที่ยื่นขอ'})
    approved_datetime = db.Column('approved_datetime', db.DateTime(timezone=True), info={'label': 'วันที่อนุมัติ'})
    cancelled_datetime = db.Column('cancelled_datetime', db.DateTime(timezone=True))
    sponsor_id = db.Column('sponsor_id', db.Integer, db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship('CMTEEventSponsor', backref=db.backref('events'))
    submission_due_date = db.Column('submission_due_date', db.Date())
    website = db.Column('website', db.Text(), info={'label': 'ลิงค์ไปยังเว็บไซต์ลงทะเบียน/ประชาสัมพันธ์'})
    coord_name = db.Column('coord_name', db.String(), info={'label': 'ชื่อผู้ประสานงาน'})
    coord_phone = db.Column('coord_phone', db.String(), info={'label': 'โทรศัพท์'})
    coord_email = db.Column('coord_email', db.String(), info={'label': 'อีเมล'})
    fee_rate_id = db.Column('fee_rate_id', db.ForeignKey('cmte_event_fee_rates.id'))
    fee_rate = db.relationship(CMTEEventFeeRate, backref=db.backref('events'))
    payment_datetime = db.Column('payment_datetime', db.DateTime(timezone=True))
    renewed_times = db.Column('renewed_times', db.Integer(), default=0)
    cmte_points = db.Column('cmte_points', db.Numeric(), info={'label': 'คะแนน CMTE'})
    event_code = db.Column('event_code', db.String(), info={'label': 'Code'})

    # TODO: add a field for an approver

    def __str__(self):
        return self.title

    @property
    def is_past_submission_date(self):
        today = datetime.datetime.today()
        if self.submission_due_date > today:
            return True
        return False

    @property
    def payment_slip(self):
        return self.docs.filter_by(is_payment_slip=True).first()


class CMTEEventParticipationRecord(db.Model):
    __tablename__ = 'cmte_event_participation_records'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    license_number = db.Column('license_number', db.ForeignKey('licenses.number'), info={'label': 'หมายเลขใบอนุญาต (ท.น.)'})
    event_id = db.Column('event_id', db.ForeignKey('cmte_events.id'))
    event = db.relationship(CMTEEvent, backref=db.backref('participants'))
    create_datetime = db.Column('create_datetime', db.DateTime(timezone=True))
    approved_date = db.Column('approved_date', db.Date())
    license = db.relationship('License', backref=db.backref('cmte_records', lazy='dynamic'))
    score = db.Column('score', db.Numeric(), info={'label': 'Score'})
    desc = db.Column('description', db.Text(), info={'label': 'รายละเอียดกิจกรรม'})
    individual = db.Column('individual', db.Boolean(), default=False)
    event_type_id = db.Column('event_type_id', db.ForeignKey('cmte_event_types.id'))
    score_valid_until = db.Column('score_valid_until', db.Date())

    @property
    def is_valid(self):
        return self.score_valid_until < self.license.end_date


class CMTEEventDoc(db.Model):
    __tablename__ = 'cmte_event_docs'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column('event_id', db.Integer, db.ForeignKey('cmte_events.id'))
    event = db.relationship(CMTEEvent, backref=db.backref('docs', cascade='all, delete-orphan', lazy='dynamic'))
    key = db.Column('key', db.Text(), nullable=False)
    filename = db.Column('filename', db.Text(), nullable=False)
    upload_datetime = db.Column('upload_datetime', db.DateTime(timezone=True))
    note = db.Column('note', db.Text(), info={'label': 'คำอธิบาย'})
    record_id = db.Column('record_id', db.ForeignKey('cmte_event_participation_records.id'))
    record = db.relationship(CMTEEventParticipationRecord,
                             backref=db.backref('docs', cascade='all, delete-orphan'))
    is_payment_slip = db.Column('is_payment_slip', db.Boolean(), default=False)


class CMTEFeePaymentRecord(db.Model):
    __tablename__ = 'cmte_fee_payment_records'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    payment_datetime = db.Column('payment_datetime', db.DateTime(timezone=True), nullable=False, info={'label': 'วันที่ชำระ'})
    start_date = db.Column('start_date', db.Date(), nullable=False, info={'label': 'วันเริ่มต้น'})
    end_date = db.Column('end_date', db.Date(), nullable=False, info={'label': 'วันสิ้นสุด'})
    license_number = db.Column('license_number', db.ForeignKey('licenses.number'), info={'label': 'หมายเลขใบอนุญาต (ท.น.)'})
    license = db.relationship('License', backref=db.backref('cmte_fee_payment_records', lazy='dynamic', cascade='all, delete-orphan'))

    def to_dict(self):
        return {'end_date': self.end_date.strftime('%Y-%m-%d'),
                'start_date': self.start_date.strftime('%Y-%m-%d'),
                'license_number': self.license_number}
