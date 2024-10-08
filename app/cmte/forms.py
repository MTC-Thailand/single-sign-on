from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.validators import NumberRange, DataRequired, EqualTo, Email
from wtforms_alchemy import model_form_factory, QuerySelectField
from wtforms import FieldList, FormField, StringField, DecimalField, TextAreaField, PasswordField

from app.cmte.models import *

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class CMTEEventDocForm(ModelForm):
    class Meta:
        model = CMTEEventDoc
        only = ['note']

    upload_file = FileField('Document Upload')
    note = TextAreaField('คำอธิบาย', render_kw={'class': 'textarea'})


class CMTEEventForm(ModelForm):
    class Meta:
        model = CMTEEvent
        datetime_format = '%d/%m/%Y %H:%M'

    event_type = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventType.query.all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)


class ParticipantForm(FlaskForm):
    license_number = StringField('License Number')
    score = DecimalField('Score', validators=[NumberRange(min=0)])


class IndividualScoreForm(FlaskForm):
    desc = TextAreaField('รายละเอียด', validators=[DataRequired()])
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=5)


class CMTEEventCodeForm(FlaskForm):
    code = QuerySelectField('Code', query_factory=lambda: CMTEEventCode.query.all(),
                            allow_blank=True, blank_text='เลือกรหัสกิจกรรม')


class CMTEFeePaymentForm(ModelForm):
    class Meta:
        model = CMTEFeePaymentRecord
        datetime_format = '%d/%m/%Y %H:%M'
        only = ['payment_datetime', 'license_number']

    license_number = StringField('License Number')


class CMTESponsorMemberForm(ModelForm):
    class Meta:
        model = CMTESponsorMember

    password = PasswordField('รหัสผ่าน', validators=[DataRequired(), EqualTo('confirm_password', message='รหัสผ่านต้องตรงกัน')])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired()])


class CMTESponsorMemberLoginForm(ModelForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
