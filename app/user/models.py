from app import db


class CandidateProfile(db.Model):
    __tablename__ = 'candidate_profiles'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), info={'label': 'คำนำหน้า'})
    firstname = db.Column(db.String(), nullable=False, info={'label': 'ชื่อ'})
    lastname = db.Column(db.String(), nullable=False, info={'label': 'นามสกุล'})
    created_at = db.Column('created_at', db.DateTime(timezone=True))
    updated_at = db.Column('updated_at', db.DateTime(timezone=True))


class CandidateDegree(db.Model):
    __tablename__ = 'candidate_degrees'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    degree = db.Column(db.String(), info={'label': 'ประวัติการศึกษา'})
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate_profiles.id'))
    candidate = db.relationship('CandidateProfile',
                                backref=db.backref('degrees', cascade='all, delete-orphan'))


class CandidateVision(db.Model):
    __tablename__ = 'candidate_visions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    vision = db.Column(db.Text(), info={'label': 'วิสัยทัศน์ในการพัฒนาวิชาชีพ'})
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate_profiles.id'))
    candidate = db.relationship('CandidateProfile',
                                backref=db.backref('visions', cascade='all, delete-orphan'))


class CandidateJobPosition(db.Model):
    __tablename__ = 'candidate_job_positions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_position = db.Column(db.String(), info={'label': 'ตำแหน่งงานปัจจุบัน'})
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate_profiles.id'))
    candidate = db.relationship('CandidateProfile',
                                backref=db.backref('job_positions', cascade='all, delete-orphan'))


class CandidateExperience(db.Model):
    __tablename__ = 'candidate_experiences'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experience = db.Column(db.String(), info={'label': 'ประสบการณ์ทำงาน'})
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate_profiles.id'))
    candidate = db.relationship('CandidateProfile',
                                backref=db.backref('experiences', cascade='all, delete-orphan'))
