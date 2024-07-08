from flask_wtf import FlaskForm
from wtforms import StringField, DateField
from wtforms.fields.simple import PasswordField
from wtforms.validators import DataRequired, Optional


class MemberSearchForm(FlaskForm):
    firstname = StringField('ชื่อ')
    lastname = StringField('นามสกุล')
    license_id = StringField('หมายเลขใบอนุญาต (ท.น.)')
    license_renewal_date = DateField('วันต่ออายุใบอนุญาต',
                                     format='%Y-%m-%d', validators=[Optional()])
    license_expire_date = DateField('วันหมดอายุใบอนุญาต',
                                    format='%Y-%m-%d', validators=[Optional()])


class AnonymousMemberSearchForm(FlaskForm):
    firstname = StringField('ชื่อ')
    lastname = StringField('นามสกุล')
    license_id = StringField('หมายเลขใบอนุญาต (ท.น.)')
    license_renewal_date = DateField('วันต่ออายุใบอนุญาต',
                                     format='%Y-%m-%d', validators=[Optional()])
    license_expire_date = DateField('วันหมดอายุใบอนุญาต',
                                    format='%Y-%m-%d', validators=[Optional()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
