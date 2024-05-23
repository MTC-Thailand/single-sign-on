from app import db, models

event_type_fee_rates = db.Table('cmte_event_type_fee_assoc',
                          db.Column('event_type_id', db.Integer,
                                    db.ForeignKey('cmte_event_types.id')),
                          db.Column('fee_rate_id', db.Integer,
                                    db.ForeignKey('cmte_event_fee_rates.id'))
                          )


class CMTEEventSponsor(db.Model):
    __tablename__ = 'cmte_event_sponsors'
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    name = db.Column('name', db.String(), nullable=False)
    affiliation = db.Column('affiliation', db.String())
    address = db.Column('address', db.Text())
    telephone = db.Column('telephone', db.String())
    expire_datetime = db.Column('expire_datetime', db.DateTime(timezone=True))


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
    submitted_datetime = db.Column('submitted_datetime', db.DateTime(timezone=True))
    approved_datetime = db.Column('approved_datetime', db.DateTime(timezone=True))
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

    def __str__(self):
        return self.title