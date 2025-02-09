from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.validators import NumberRange, EqualTo, Email, Optional
from wtforms.widgets.core import CheckboxInput, ListWidget
from wtforms_alchemy import model_form_factory, QuerySelectField, QuerySelectMultipleField
from wtforms import FieldList, FormField, StringField, DecimalField, TextAreaField, PasswordField
from wtforms_components import DateField, DateTimeField

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

    event_type = QuerySelectField('ประเภทกิจกรรม', query_factory=lambda: CMTEEventType.query.order_by(CMTEEventType.number).all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)


class CMTEAdminEventForm(ModelForm):
    class Meta:
        model = CMTEEvent
        datetime_format = '%d/%m/%Y %H:%M'
        date_format = '%d/%m/%Y'

    event_type = QuerySelectField('ประเภทกิจกรรม', query_factory=lambda: CMTEEventType.query.order_by(CMTEEventType.number).all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)
    sponsor = QuerySelectField('สถาบันฝึกอบรม', query_factory=lambda: CMTEEventSponsor.query.all())
    activity = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventActivity.query.all())


class ParticipantForm(FlaskForm):
    license_number = StringField('License Number')
    score = DecimalField('Score', validators=[NumberRange(min=0)])
    approved_date = DateField('Approved Date', validators=[Optional()])


class IndividualScoreForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord
        only = ['start_date', 'end_date', 'desc']
        date_format = '%d/%m/%Y'
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=5)


class IndividualScoreAdminForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord
        only = ['start_date', 'end_date', 'desc', 'score', 'reason']
        date_format = '%d/%m/%Y'
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=5)
    activity = QuerySelectField('ชนิดกิจกรรม',
                                query_factory=lambda: CMTEEventActivity.query.all(),
                                allow_blank=True,
                                blank_text='กรุณาเลือกชนิดกิจกรรม')


class CMTEEventCodeForm(FlaskForm):
    code = QuerySelectField('Code', query_factory=lambda: CMTEEventCode.query.all(),
                            allow_blank=True, blank_text='เลือกรหัสกิจกรรม')


class CMTEFeePaymentForm(ModelForm):
    class Meta:
        model = CMTEFeePaymentRecord
        datetime_format = '%d/%m/%Y %H:%M'
        only = ['payment_datetime', 'license_number']

    license_number = StringField('License Number')


class MemberCMTEFeePaymentForm(ModelForm):
    class Meta:
        model = CMTEFeePaymentRecord
        exclude = ['start_date', 'end_date']

    payment_datetime = DateTimeField('ชำระเมือ', format='%d/%m/%Y %H:%M')
    doc = FormField(CMTEEventDocForm, default=CMTEEventDocForm)


class CMTESponsorMemberForm(ModelForm):
    class Meta:
        model = CMTESponsorMember

    password = PasswordField('รหัสผ่าน', validators=[DataRequired(), EqualTo('confirm_password', message='รหัสผ่านต้องตรงกัน')])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired()])


class CMTESponsorMemberLoginForm(ModelForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])


class CMTEEventSponsorForm(ModelForm):
    class Meta:
        model = CMTEEventSponsor


class CMTEPaymentForm(FlaskForm):
    upload_file = FormField(CMTEEventDocForm, default=CMTEEventDoc)


class CMTEParticipantFileUploadForm(FlaskForm):
    upload_file = FileField('Participants')


class CMTEAdminEventTypeForm(ModelForm):
    class Meta:
        model = CMTEEventType
        exclude = ['created_at', 'updated_at']

    fee_rates = QuerySelectMultipleField(query_factory=lambda: CMTEEventFeeRate.query.all(),
                                         widget=ListWidget(prefix_label=False),
                                         option_widget=CheckboxInput())