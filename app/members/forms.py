from flask_wtf import FlaskForm
from wtforms import StringField


class MemberSearchForm(FlaskForm):
    firstname = StringField('ชื่อ')
    lastname = StringField('นามสกุล')
    license_id = StringField('หมายเลขใบอนุญาต (ท.น.)')