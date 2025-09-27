from email.policy import default

from flask_wtf import FlaskForm
from wtforms import StringField, DateField, FormField, FieldList
from wtforms.fields.simple import PasswordField
from wtforms.validators import DataRequired, Optional
from wtforms_alchemy import model_form_factory

from app.members.models import *

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


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


class MemberLoginForm(FlaskForm):
    pid = StringField('รหัสบัตรประชาชน', validators=[DataRequired()])
    telephone = StringField('หมายเลขโทรศัพท์', validators=[DataRequired()])
    otp = PasswordField('OTP', validators=[DataRequired()])


class MemberLoginOldForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class MemberUsernamePasswordForm(ModelForm):
    class Meta:
        model = Member
        only = ['username', 'password']


class MemberAddressForm(ModelForm):
    class Meta:
        model = MemberAddress
        exclude = ['updated_at']


class MemberInfoForm(ModelForm):
    class Meta:
        model = Member
        only = ['tel', 'email']
    addresses = FieldList(FormField(MemberAddressForm, default=MemberAddress),
                          min_entries=1, max_entries=1)
