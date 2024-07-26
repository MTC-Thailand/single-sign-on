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


class License(db.Model):
    __tablename__ = 'licenses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    number = db.Column(db.String(), unique=True, nullable=False)
    issue_date = db.Column(db.Date(), nullable=False)
    start_date = db.Column(db.Date(), nullable=False)
    end_date = db.Column(db.Date(), nullable=False)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))
    member = db.relationship(Member, backref=db.backref('licenses',
                                                        order_by='License.end_date.desc()'))
