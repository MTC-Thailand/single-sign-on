import datetime

from flask_login import UserMixin
from sqlalchemy_utils import EmailType
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms.validators import DataRequired
from pytz import timezone
from datetime import datetime, timedelta
from sqlalchemy_continuum import make_versioned
import sqlalchemy as sa

from app import db

make_versioned(user_cls=None)

event_activity_fee_rates = db.Table('cmte_event_activity_fee_assoc',
                                    db.Column('event_activity_id', db.Integer, db.ForeignKey('cmte_event_activities.id')),
                                    db.Column('fee_rate_id', db.Integer, db.ForeignKey('cmte_event_fee_rates.id'))
                                    )

sponsor_qualifications = db.Table('sponsor_qualification_assoc',
                                  db.Column('event_sponsor_id', db.ForeignKey('cmte_event_sponsors.id')),
                                  db.Column('qualification_id',
                                            db.ForeignKey('cmte_sponsor_qualification.id')),
                                  )

BANGKOK = timezone('Asia/Bangkok')


class CMTEEventSponsor(db.Model):
    __versioned__ = {}
    __tablename__ = 'cmte_event_sponsors'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    old_id = db.Column(db.Integer)
    name = db.Column('name', db.String(), nullable=False, info={'label': 'ชื่อสถาบัน'})
    code = db.Column('code', db.String(), info={'label': 'รหัสสถาบัน'})
    affiliation = db.Column('affiliation', db.String(), info={'label': 'สังกัด'})
    address = db.Column('address', db.Text(), info={'label': 'ที่อยู่'})
    zipcode = db.Column('zipcode', db.String(), info={'label': 'รหัสไปรษณีย์'})
    telephone = db.Column('telephone', db.String(), info={'label': 'หมายเลขโทรศัพท์'})
    email = db.Column('email', EmailType(), info={'label': 'E-mail'})
    website = db.Column('website', db.String(), info={'label': 'website'})
    registered_datetime = db.Column('registered_datetime', db.DateTime(timezone=True))
    expire_date = db.Column('expire_date', db.Date())
    type = db.Column(db.String(), info={'label': 'ลักษณะขององค์กร',
                                        'choices': [(c, c) for c in (
                                            'เป็นสถาบันการศึกษา(คณะ/ภาควิชา/หน่วยงานที่มีฐานะเทียบเท่าคณะหรือภาควิชาที่ผลิตบัณฑิตเทคนิคการแพทย์)',
                                            'เป็นสถาบันการศึกษา(คณะ/ภาควิชา/หน่วยงานที่มีฐานะเทียบเท่าคณะหรือภาควิชา)',
                                            'เป็นสถานพยาบาล',
                                            'เป็นหน่วยงาน/องค์กรตามที่สภาเทคนิคการแพทย์ประกาศกําหนด',
                                            'เป็นหน่วยงาน/องค์กรของรัฐหรือเอกชน')]})
    type_detail = db.Column('type_detail', db.String())
    qualifications = db.relationship('CMTESponsorQualification', secondary=sponsor_qualifications)
    private_sector = db.Column('private_sector', db.Boolean(), default=False)
    disable_at = db.Column('disable_at', db.DateTime(timezone=True))

    def __str__(self):
        return self.name

    @property
    def num_pending_events(self):
        return self.events.filter_by(is_pending=True).count()

    @property
    def num_approved_events(self):
        return self.events.filter(CMTEEvent.approved_datetime != None).count()

    @property
    def num_submitted_events(self):
        return self.events.filter_by(submitted_datetime=None).count()

    def expire_status(self):
        today = datetime.now().date()
        status = "inactive"
        if self.expire_date:
            status = "active"
            if self.expire_date:
                if self.expire_date < today:
                    status = "expired"
                else:
                    delta = self.expire_date - today
                    if delta.days <= 90:
                        status = "nearly_expire"

        return status


class CMTESponsorMember(UserMixin, db.Model):
    __versioned__ = {}
    __tablename__ = 'cmte_sponsor_members'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    old_user_id = db.Column('old_user_id', db.Integer())
    title = db.Column('title', db.String(), info={'label': 'คำนำหน้า'})
    firstname = db.Column('firstname', db.String(), info={'label': 'ชื่อ', 'validators': [DataRequired()]})
    lastname = db.Column('lastname', db.String(), info={'label': 'นามสกุล', 'validators': [DataRequired()]})
    email = db.Column('email', EmailType(), info={'label': 'E-mail', 'validators': [DataRequired()]})
    _password_hash = db.Column(db.String(255))
    mobile_phone = db.Column('mobile_phone', db.String(), info={'label': 'โทรศัพท์มือถือ'})
    telephone = db.Column('telephone', db.String(), info={'label': 'โทรศัพท์'})
    position = db.Column('position', db.String(), info={'label': 'ตำแหน่ง'})
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship(CMTEEventSponsor,
                              backref=db.backref('members', lazy='dynamic', cascade="all, delete-orphan"))
    is_coordinator = db.Column('is_coordinator', db.Boolean(), default=False)
    is_valid = db.Column('is_valid', db.Boolean(), default=True)

    @property
    def is_active(self):
        return self.is_valid

    def verify_password(self, password):
        return check_password_hash(self._password_hash, password)

    @property
    def password(self):
        # raise ValueError
        return 'Password is not accessible'

    @password.setter
    def password(self, pw):
        self._password_hash = generate_password_hash(pw)

    def __str__(self):
        return f'{self.title or ""} {self.firstname} {self.lastname}'

    @property
    def unique_id(self):
        return f'sponsor-member-{self.id}'


class CMTESponsorQualification(db.Model):
    __tablename__ = 'cmte_sponsor_qualification'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    type = db.Column('type', db.String(255), nullable=False)
    private_sector = db.Column('private_sector', db.Boolean(), default=False)

    def __str__(self):
        return self.type


class CMTESponsorRequest(db.Model):
    __tablename__ = 'cmte_sponsor_requests'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship(CMTEEventSponsor,
                              backref=db.backref('requests',
                                                 lazy='dynamic',
                                                 cascade='all, delete-orphan'))
    member_id = db.Column('member_id', db.ForeignKey('cmte_sponsor_members.id'))
    member = db.relationship(CMTESponsorMember,
                             backref=db.backref('member_requests', lazy='dynamic'))
    type = db.Column('type', db.String())
    created_at = db.Column('created_at', db.DateTime(timezone=True))
    expired_sponsor_date = db.Column('expired_sponsor_date', db.Date())
    approved_at = db.Column('approved_at', db.DateTime(timezone=True))
    paid_at = db.Column('paid_at', db.DateTime(timezone=True))
    verified_at = db.Column('verified_at', db.DateTime(timezone=True))
    comment = db.Column('comment', db.String())
    rejected_at = db.Column('rejected_at', db.DateTime(timezone=True))
    cancelled_at = db.Column('cancelled_at', db.DateTime(timezone=True))


class CMTESponsorEditRequest(db.Model):
    __tablename__ = 'cmte_sponsor_edit_requests'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship(CMTEEventSponsor,
                              backref=db.backref('edit_requests', lazy='dynamic'))
    member_id = db.Column('member_id', db.ForeignKey('cmte_sponsor_members.id'))
    member = db.relationship(CMTESponsorMember,
                             backref=db.backref('edit_requests', lazy='dynamic'))
    created_at = db.Column('created_at', db.DateTime(timezone=True))
    status = db.Column('status', db.String())
    updated_at = db.Column('updated_at', db.DateTime(timezone=True))
    version_index = db.Column('version_index', db.Integer())


class CMTESponsorDoc(db.Model):
    __tablename__ = 'cmte_sponsor_docs'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    request_id = db.Column('request_id', db.ForeignKey('cmte_sponsor_requests.id'))
    request = db.relationship(CMTESponsorRequest,
                              backref=db.backref('docs', lazy='dynamic'))
    sponsor = db.relationship(CMTEEventSponsor,
                              backref=db.backref('docs', cascade='all, delete-orphan', lazy='dynamic'))
    qualification_id = db.Column('qualification_id', db.ForeignKey('cmte_sponsor_qualification.id'))
    qualification = db.relationship(CMTESponsorQualification,
                                    backref=db.backref('docs'))
    key = db.Column('key', db.Text(), nullable=False)
    filename = db.Column('filename', db.Text(), nullable=False)
    upload_datetime = db.Column('upload_datetime', db.DateTime(timezone=True))
    note = db.Column('note', db.Text(), info={'label': 'คำอธิบาย'})
    is_payment_slip = db.Column('is_payment_slip', db.Boolean(), default=False)


class CMTEReceiptDoc(db.Model):
    __tablename__ = 'cmte_receipt_docs'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column('request_id', db.ForeignKey('cmte_sponsor_requests.id'))
    request = db.relationship(CMTESponsorRequest,
                              backref=db.backref('receipt_docs'))
    key = db.Column('key', db.Text(), nullable=False)
    filename = db.Column('filename', db.Text(), nullable=False)
    upload_datetime = db.Column('upload_datetime', db.DateTime(timezone=True))
    note = db.Column('note', db.Text(), info={'label': 'คำอธิบาย'})


class CMTEReceiptDetail(db.Model):
    __tablename__ = 'cmte_receipt_details'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    sponsor_id = db.Column('sponsor_id', db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship(CMTEEventSponsor,
                              backref=db.backref('receipt_details'))
    name = db.Column('name', db.String())
    receipt_item = db.Column('receipt_item', db.Text())
    tax_id = db.Column('tax_id', db.String())
    address = db.Column('address', db.Text(), info={'label': 'ที่อยู่'})
    zipcode = db.Column('zipcode', db.String(), info={'label': 'รหัสไปรษณีย์'})

    def __str__(self):
        return f'รายละเอียดบนใบเสร็จ ออกใบนาม: {self.name} รายการที่แสดงในใบเสร็จ(ถ้ามี): {self.receipt_item or ""} เลขที่ผู้เสียภาษี(ถ้ามี): {self.tax_id or ""} ที่อยู่: {self.address} {self.zipcode}'


class CMTEEventCategory(db.Model):
    __tablename__ = 'cmte_event_categories'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    name = db.Column('name', db.String(255), unique=True, nullable=False)

    def __str__(self):
        return self.name


class CMTEEventType(db.Model):
    """ประเภทกิจกรรม
    """
    __tablename__ = 'cmte_event_types'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    number = db.Column('number', db.Integer(), info={'label': 'ลำดับ'})
    old_id = db.Column('old_id', db.Integer)
    name = db.Column('name', db.String(255), unique=True, nullable=False, info={'label': 'ประเภท'})
    for_group = db.Column('for_group', db.Boolean(), default=False, info={'label': 'ขอคะแนนแบบกลุ่มได้'})
    is_sponsored = db.Column('is_sponsored', db.Boolean(), default=False, info={'label': 'จัดโดยสถาบัน'})
    category_id = db.Column('category_id', db.Integer, db.ForeignKey('cmte_event_categories.id'))
    category = db.relationship('CMTEEventCategory', backref=db.backref('types'))
    submission_due = db.Column('submission_due', db.Integer(), default=30, info={'label': 'กำหนดส่งรายชื่อผู้เข้าร่วม'})
    max_score = db.Column('max_score', db.Integer(), default=25, info={'label': 'คะแนนสูงสุดที่อนุมัติได้'})
    score_criteria = db.Column('score_criteria', db.String(), info={'label': 'เกณฑ์การพิจารณาอนุมัติคะแนน'})
    desc = db.Column('desc', db.Text(), info={'label': 'รายละเอียด'})
    deprecated = db.Column('deprecated', db.Boolean(), default=False, info={'label': 'ยกเลิก'})
    created_at = db.Column('created_at', db.DateTime(timezone=True))
    updated_at = db.Column('updated_at', db.DateTime(timezone=True))

    def __str__(self):
        return f'{self.number}. {self.name}'


class CMTEEventActivity(db.Model):
    """ชนิดกิจกรรม"""
    __tablename__ = 'cmte_event_activities'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    old_id = db.Column('old_id', db.Integer)
    number = db.Column('number', db.Integer(), info={'label': 'ลำดับ'})
    name = db.Column('name', db.String(255), unique=True, nullable=False, info={'label': 'ชื่อชนิดกิจกรรม'})
    type_id = db.Column('type_id', db.Integer, db.ForeignKey('cmte_event_types.id'))
    en_name = db.Column('en_name', db.String(255))
    detail = db.Column('detail', db.Text(), info={'label': 'รายละเอียด'})
    group_submission_only = db.Column('group_submission_only', db.Boolean(),
                                      default=False,
                                      info={'label': 'ยื่นขอคะแนนแบบกลุ่มเท่านั้น'})
    group_submission_allowed = db.Column('group_submission_allowed', db.Boolean(),
                                         default=False,
                                         info={'label': 'ยื่นขออนุมัติคะแนนแบบกลุ่มและส่วนตัว'})
    event_type = db.relationship('CMTEEventType', backref=db.backref('activities',
                                                                     lazy='dynamic',
                                                                     order_by='CMTEEventActivity.number',
                                                                     cascade='all, delete-orphan'))
    deprecated = db.Column('deprecated', db.Boolean(), default=False, info={'label': 'ยกเลิก'})
    created_at = db.Column('created_at', db.DateTime(timezone=True))
    updated_at = db.Column('updated_at', db.DateTime(timezone=True))
    fee_rates = db.relationship('CMTEEventFeeRate', secondary=event_activity_fee_rates,
                                backref=db.backref('event_activities'),
                                info={'label': 'อัตราค่าธรรมเนียม'})

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
            return f'{format} ไม่เกิน {self.max_participants} คน: {self.fee_rate} บาท {self.desc or ""}'
        elif self.fee_rate:
            return f'{format}: {self.fee_rate} บาท {self.desc or ""}'
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
    old_id = db.Column('old_id', db.Integer)
    main_event_id = db.Column('parent_id', db.Integer, db.ForeignKey('cmte_events.id'))
    sub_events = db.relationship('CMTEEvent', backref=db.backref('main_event', remote_side=[id]))
    title = db.Column('title', db.String(), nullable=False, info={'label': 'ชื่อกิจกรรม'})
    venue = db.Column('venue', db.Text(), info={'label': 'สถานที่จัดงาน'})
    event_type_id = db.Column('event_type_id', db.Integer, db.ForeignKey('cmte_event_types.id'))
    event_type = db.relationship('CMTEEventType', backref=db.backref('events'))
    activity_id = db.Column('activity_id', db.Integer, db.ForeignKey('cmte_event_activities.id'))
    activity = db.relationship(CMTEEventActivity, backref=db.backref('events',
                                                                     lazy='dynamic',
                                                                     cascade='all, delete-orphan'))
    start_date = db.Column('start_date', db.DateTime(timezone=True), info={'label': 'เริ่มต้น'})
    end_date = db.Column('end_date', db.DateTime(timezone=True), info={'label': 'สิ้นสุด'})
    submitted_datetime = db.Column('submitted_datetime', db.DateTime(timezone=True), info={'label': 'วันที่ยื่นขอ'})
    approved_datetime = db.Column('approved_datetime', db.DateTime(timezone=True), info={'label': 'วันที่อนุมัติ'})
    cancelled_datetime = db.Column('cancelled_datetime', db.DateTime(timezone=True))
    sponsor_id = db.Column('sponsor_id', db.Integer, db.ForeignKey('cmte_event_sponsors.id'))
    sponsor = db.relationship('CMTEEventSponsor', backref=db.backref('events', lazy='dynamic'))
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
    comment = db.Column('comment', db.String(), info={'label': 'ข้อคิดเห็นจากศูนย์ CMTE'})
    payment_approved_at = db.Column('payment_approve_datetime', db.DateTime(timezone=True), info={'label': 'วันที่ตรวจสอบการชำระเงิน'})
    is_pending = db.Column('is_pending', db.Boolean())
    info_request = db.Column('info_request', db.Text(), info={'label': 'รายการขอข้อมูลเพิ่มเติม'})
    participant_updated_at = db.Column('participant_updated_at', db.DateTime(timezone=True), info={'label': 'วันที่เพิ่ม/แก้ไขรายชื่อล่าสุด'})

    # TODO: add a field for an approver

    def to_dict(self):
        return {
            'id': self.id,
            'title': f'{self.title} (pending)' if self.is_pending else self.title,
            'start_date': self.start_date.astimezone(BANGKOK).isoformat() if self.start_date else None,
            'end_date': self.end_date.astimezone(BANGKOK).isoformat() if self.end_date else None,
            'event_type': str(self.event_type) if self.event_type else None,
            'fee_rate': str(self.fee_rate) if self.fee_rate else None,
            'submitted_datetime': self.submitted_datetime.astimezone(
                BANGKOK).isoformat() if self.submitted_datetime else None,
            'approved_datetime': self.approved_datetime.astimezone(
                BANGKOK).isoformat() if self.approved_datetime else None,
            'payment_datetime': self.payment_datetime.astimezone(
                BANGKOK).isoformat() if self.payment_datetime else None,
            'payment_approved_at': self.payment_datetime.astimezone(
                BANGKOK).isoformat() if self.payment_approved_at else None,
            'participant_updated_at': self.participant_updated_at.astimezone(
                BANGKOK).isoformat() if self.participant_updated_at else None,
            'venue': self.venue,
            'points': self.cmte_points,
            'website': self.website,
            'sponsor': str(self.sponsor) if self.sponsor else None,
            'num_pending_participants': self.num_pending_participants,
        }

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

    @property
    def is_editable(self):
        return self.is_pending or not self.submitted_datetime

    @property
    def status(self):
        if self.is_pending:
            return 'รอแก้ไขหรือส่งข้อมูลเพิ่มเติม'
        elif self.approved_datetime:
            return 'อนุมัติแล้ว'
        elif self.submitted_datetime:
            return 'รออนุมัติคะแนน'
        elif self.payment_datetime and not self.payment_approved_at:
            return 'รอตรวจสอบการชำระเงิน'
        elif not self.payment_datetime:
            return 'รอชำระเงิน'
        else:
            return 'รอยื่นขออนุมัติ'

    @property
    def num_pending_participants(self):
        return self.participants.filter(CMTEEventParticipationRecord.approved_date==None).count()


class CMTEEventParticipationRecord(db.Model):
    __tablename__ = 'cmte_event_participation_records'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    license_number = db.Column('license_number', db.ForeignKey('licenses.number'),
                               info={'label': 'หมายเลขใบอนุญาต (ท.น.)'})
    submitted_name = db.Column('submitted_name', db.String())
    event_id = db.Column('event_id', db.ForeignKey('cmte_events.id'))
    event = db.relationship(CMTEEvent, backref=db.backref('participants', lazy='dynamic', cascade='all, delete-orphan'))
    create_datetime = db.Column('create_datetime', db.DateTime(timezone=True))
    approved_date = db.Column('approved_date', db.Date())
    start_date = db.Column('start_date', db.Date(), info={'label': 'เริ่ม'})
    end_date = db.Column('end_date', db.Date(), info={'label': 'สิ้นสุด'})
    license = db.relationship('License', backref=db.backref('cmte_records', lazy='dynamic'))
    score = db.Column('score', db.Numeric(), info={'label': 'Score'})
    desc = db.Column('description', db.Text(), info={'label': 'รายละเอียดกิจกรรม'})
    individual = db.Column('individual', db.Boolean(), default=False)
    event_type_id = db.Column('event_type_id', db.ForeignKey('cmte_event_types.id'))
    score_valid_until = db.Column('score_valid_until', db.Date())
    closed_date = db.Column('closed_date', db.Date())
    reason = db.Column('reason', db.Text(), info={'label': 'เหตุผล'})
    activity_id = db.Column('activity_id', db.ForeignKey('cmte_event_activities.id'))
    activity = db.relationship(CMTEEventActivity, backref=db.backref('records',
                                                                     lazy='dynamic',
                                                                     cascade='all, delete-orphan'))

    @property
    def is_valid(self):
        return (self.score_valid_until < self.license.end_date) and self.approved_date is not None

    @property
    def status(self):
        if self.approved_date:
            return 'อนุมัติ'
        else:
            return 'รออนุมัติ'

    def set_score_valid_date(self):
        if self.event:
            if self.event.end_date.date() <= self.license.end_date:
                self.score_valid_until = self.license.end_date
        else:
            self.score_valid_until = self.license.end_date

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.license.member.th_fullname,
            'submitted_name': self.submitted_name if self.submitted_name else self.license.member.th_fullname,
            'name_matched': 'Mismatched' if self.submitted_name and self.submitted_name != self.license.member.th_fullname else '',
            'license_number': self.license_number,
            'score': self.score,
            'status': self.status,
            'created_at': self.create_datetime.astimezone(BANGKOK).isoformat() if self.create_datetime else None,
            'approved_at': self.approved_date.isoformat() if self.approved_date else None,
        }


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
    payment_datetime = db.Column('payment_datetime', db.DateTime(timezone=True), nullable=True,
                                 info={'label': 'วันที่ชำระ'})
    start_date = db.Column('start_date', db.Date(), nullable=False, info={'label': 'วันเริ่มต้น'})
    end_date = db.Column('end_date', db.Date(), nullable=False, info={'label': 'วันสิ้นสุด'})
    license_number = db.Column('license_number', db.ForeignKey('licenses.number'),
                               info={'label': 'หมายเลขใบอนุญาต (ท.น.)'})
    license = db.relationship('License', backref=db.backref('cmte_fee_payment_records',
                                                            lazy='dynamic', cascade='all, delete-orphan'))
    doc_id = db.Column('doc_id', db.ForeignKey('cmte_event_docs.id'))
    doc = db.relationship(CMTEEventDoc, uselist=False)
    note = db.Column('note', db.Text, info={'label': 'หมายเหตุ'})

    def to_dict(self):
        return {'end_date': self.end_date.strftime('%Y-%m-%d') if self.end_date else None,
                'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
                'payment_datetime': self.payment_datetime.isoformat() if self.payment_datetime else None,
                'license_number': self.license_number}


sa.orm.configure_mappers()
