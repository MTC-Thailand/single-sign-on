from datetime import date

from flask_login import UserMixin

from app import db


class Member(db.Model, UserMixin):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False)
    code = db.Column(db.String())
    old_mem_id = db.Column('old_mem_id', db.Integer())
    th_title = db.Column('th_title', db.String(), info={'label': 'คำนำหน้า'})
    th_firstname = db.Column(db.String(), nullable=False, info={'label': 'ชื่อ'})
    th_lastname = db.Column(db.String(), nullable=False, info={'label': 'นามสกุล'})
    en_title = db.Column('en_title', db.String(), info={'label': 'Title'})
    en_firstname = db.Column(db.String(), info={'label': 'Firstname'})
    en_lastname = db.Column(db.String(), info={'label': 'Lastname'})
    dob = db.Column(db.Date(), info={'label': 'วันเกิด'})
    pid = db.Column(db.String(), nullable=False, info={'label': 'เลขบัตรประชาชน'})
    email = db.Column(db.String(), info={'label': 'E-mail'})
    tel = db.Column(db.String(), info={'label': 'โทรศัพท์'})
    username = db.Column(db.String())
    password = db.Column(db.String())
    status = db.Column(db.String(), info={'label': 'สถานะ',
                                          'choices': [(c, c) for c in ('ปกติ', 'ลาออก', 'พ้นสมาชิกภาพ', 'ตาย')]})
    end_date = db.Column(db.Date(), info={'label': 'วันสิ้นอายุสมาชิกภาพ'})
    begin_date = db.Column(db.Date(), info={'label': 'วันเริ่มต้นสมาชิกภาพ'})
    # TODO: import begin date from the legacy database.

    def __str__(self):
        return self.th_fullname

    @property
    def license_number(self):
        if self.license:
            return self.license.number
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
    today = date.today().strftime('%Y-%m-%d')
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False, info={'label': 'หมายเลข'})
    issue_date = db.Column(db.Date(), nullable=False, info={'label': 'วันอนุมัติใบอนุญาต'})
    start_date = db.Column(db.Date(), nullable=False, info={'label': 'วันเริ่ม'})
    end_date = db.Column(db.Date(), nullable=False, info={'label': 'วันสิ้นสุด'})
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))
    member = db.relationship(Member,
                             backref=db.backref('license',
                                                uselist=False,
                                                order_by='License.end_date.desc()'))
    # member = db.relationship(Member,
    #                          backref=db.backref('license',
    #                                             uselist=False,
    #                                             primaryjoin=f'and_(License.member_id=={Member.id}, License.start_date <= "{today}", License.end_date >= "{today}")'),
    #                          uselist=False)
    status = db.Column(db.String(), info={'label': 'สถานะ',
                                          'choices': [(c,c) for c in ('ปกติ', 'พักใช้', 'เพิกถอน', 'สิ้นสุด')]})

    def __str__(self):
        return f'{self.number}: {self.end_date}'

    def get_active_cmte_fee_payment(self):
        record = self.cmte_fee_payment_records\
            .filter_by(end_date=self.end_date).first()
        return record

    @property
    def pending_individual_cmte_records(self):
        return self.cmte_records.filter_by(approved_date=None, individual=True)

    @property
    def pending_cmte_records(self):
        return self.cmte_records.filter_by(approved_date=None)

    @property
    def valid_cmte_records(self):
        return (rec for rec in
                self.cmte_records.filter_by(score_valid_until=self.end_date)
                if rec.approved_date is not None)

    @property
    def total_cmte_scores(self):
        return sum([rec.score for rec in self.cmte_records if rec.approved_date is not None])

    @property
    def valid_cmte_scores(self):
        return sum([rec.score for rec in self.valid_cmte_records])

    @property
    def dates(self):
        date_format = '%d/%m/%Y'
        return f'{self.start_date.strftime(date_format)} - {self.end_date.strftime(date_format)}'

    @property
    def is_expired(self):
        return self.end_date <= date.today()


# class MemberAddress(db.Model):
#     __tablename__ = 'member_addresses'
#     id = db.Column(db.Integer, primary_key=True, autoincrement=True)
#     street_number = db.Column(db.Text())
#     add_id = db.Column(db.Integer, info={'label': 'ชนิด',
#                                          'choices': [('1', 'ที่อยู่'),
#                                                      ('2', 'ที่ทำงาน'),
#                                                      ('3', 'ที่อยู่ตามทะเบียนบ้าน')]})
#     zipcode = db.Column('zipcode', db.Integer, info={'label': 'รหัสไปรษณีย์'})
