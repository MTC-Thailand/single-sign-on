from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import NumberRange, EqualTo, Email, Optional
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms_alchemy import model_form_factory, QuerySelectField, QuerySelectMultipleField
from wtforms import FieldList, FormField, StringField, DecimalField, TextAreaField, PasswordField, SelectField, \
    RadioField
from wtforms_components import DateField, DateTimeField, TimeField

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
        exclude = ['payment_datetime', 'comment', 'submitted_datetime', 'cancelled_datetime']

    event_type = QuerySelectField('ประเภทกิจกรรม',
                                  query_factory=lambda: CMTEEventType.query.order_by(CMTEEventType.number).all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)
    activity = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventActivity.query.all())
    fee_rate = QuerySelectField('อัตรค่าธรรมเนียม', query_factory=lambda: CMTEEventFeeRate.query.all(),
                                allow_blank=True,
                                widget=ListWidget(prefix_label=False),
                                option_widget=CheckboxInput())


class CMTEAdminEventForm(ModelForm):
    class Meta:
        model = CMTEEvent
        datetime_format = '%d/%m/%Y %H:%M'
        date_format = '%d/%m/%Y'
        exclude = ['payment_datetime', 'comment', 'cancelled_datetime']

    event_type = QuerySelectField('ประเภทกิจกรรม',
                                  query_factory=lambda: CMTEEventType.query.order_by(CMTEEventType.number).all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)
    sponsor = QuerySelectField('สถาบันฝึกอบรม', query_factory=lambda: CMTEEventSponsor.query.all())
    activity = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventActivity.query.all())
    fee_rate = QuerySelectField('อัตรค่าธรรมเนียม', query_factory=lambda: CMTEEventFeeRate.query.all(),
                                allow_blank=True,
                                widget=ListWidget(prefix_label=False),
                                option_widget=CheckboxInput())


class AdminParticipantForm(FlaskForm):
    license_number = StringField('License Number')
    score = DecimalField('Score', validators=[NumberRange(min=0)])
    approved_date = DateField('Approved Date', validators=[Optional()])


class AdminParticipantRecordForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord
        only = ['score', 'score_valid_until', 'approved_date']
        date_format = '%d/%m/%Y'


class ParticipantForm(FlaskForm):
    license_number = StringField('License Number')
    score = DecimalField('Score', validators=[NumberRange(min=0),
                                              DataRequired(message='Please enter a valid score.')])


class IndividualScoreForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord
        only = ['start_date', 'end_date', 'desc']
        date_format = '%d/%m/%Y'

    event_type = QuerySelectField('ประเภทกิจกรรม',
                                  get_label='name',
                                  query_factory=lambda: CMTEEventType.query.filter_by(is_sponsored=False,
                                                                                      deprecated=False).all())
    activity = QuerySelectField('ชนิดกิจกรรม',
                                get_label='name',
                                query_factory=lambda: CMTEEventActivity.query.all())

    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=5)


class IndividualScoreAdminForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord
        only = ['start_date', 'end_date', 'desc', 'score', 'reason']
        date_format = '%d/%m/%Y'

    event_type = QuerySelectField('ประเภทกิจกรรม',
                                  get_label='name',
                                  query_factory=lambda: CMTEEventType.query.filter_by(is_sponsored=False,
                                                                                      deprecated=False).all())
    activity = QuerySelectField('ชนิดกิจกรรม',
                                get_label='name',
                                query_factory=lambda: CMTEEventActivity.query.all())

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


class MemberCMTEFeePaymentForm(ModelForm):
    class Meta:
        model = CMTEFeePaymentRecord
        exclude = ['start_date', 'end_date']

    payment_datetime = DateTimeField('ชำระเมือ', format='%d/%m/%Y %H:%M')
    doc = FormField(CMTEEventDocForm, default=CMTEEventDocForm)


class CMTESponsorMemberForm(ModelForm):
    class Meta:
        model = CMTESponsorMember

    password = PasswordField('รหัสผ่าน',
                             validators=[DataRequired(), EqualTo('confirm_password', message='รหัสผ่านต้องตรงกัน')])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired()])


class CMTESponsorMemberPasswordForm(ModelForm):
    password = PasswordField('รหัสผ่าน',
                             validators=[DataRequired(), EqualTo('confirm_password', message='รหัสผ่านต้องตรงกัน')])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired()])


class CMTEAdminSponsorMemberForm(ModelForm):
    class Meta:
        model = CMTESponsorMember


class CMTESponsorMemberEditForm(ModelForm):
    class Meta:
        model = CMTESponsorMember


class CMTESponsorAdditionalRequestForm(FlaskForm):
    comment = TextAreaField('รายละเอียดที่ต้องการ')


class CMTESponsorRequestForm(FlaskForm):
    comment = TextAreaField('เหตุผล')


class CMTESponsorMemberChangePasswordForm(FlaskForm):
    password = PasswordField('รหัสผ่าน',
                             validators=[DataRequired(), EqualTo('confirm_password', message='รหัสผ่านต้องตรงกัน')])
    confirm_password = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired()])


class CMTESponsorMemberLoginForm(ModelForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])


class CMTESponsorDocForm(ModelForm):
    class Meta:
        model = CMTESponsorDoc
        only = ['note']

    upload_file = FileField('Document Upload')
    note = TextAreaField('คำอธิบาย', render_kw={'class': 'textarea'})


class CMTEEventSponsorForm(ModelForm):
    class Meta:
        model = CMTEEventSponsor
        datetime_format = '%d/%m/%Y %H:%M'
        date_format = '%d/%m/%Y'

    qualifications = QuerySelectMultipleField('หลักฐานแสดงคุณสมบัติขององค์กร',
                                              query_factory=lambda: CMTESponsorQualification.query.all(),
                                              widget=ListWidget(prefix_label=False),
                                              option_widget=CheckboxInput())
    private_sector = SelectField(choices=[('', 'องค์กรรัฐ'), ('private', 'องค์กรเอกชน')], coerce=bool)
    has_med_tech = RadioField(choices=[('True', 'มีนักเทคนิคการแพทย์'), ('False', 'ไม่มีนักเทคนิคการแพทย์')],
                              validators=[DataRequired()])


class CMTESponsorEditForm(ModelForm):
    qualifications = QuerySelectMultipleField('หลักฐานแสดงคุณสมบัติขององค์กร',
                                              query_factory=lambda: CMTESponsorQualification.query.all(),
                                              widget=ListWidget(prefix_label=False),
                                              option_widget=CheckboxInput())
    private_sector = SelectField(choices=[('', 'องค์กรรัฐ'), ('private', 'องค์กรเอกชน')], coerce=bool)
    has_med_tech = RadioField(choices=[('True', 'มีนักเทคนิคการแพทย์'), ('False', 'ไม่มีนักเทคนิคการแพทย์')],
                              validators=[DataRequired()])


class CMTESponsorPaymentForm(FlaskForm):
    class Meta:
        model = CMTEEventSponsor

    name = TextAreaField('name', render_kw={'class': 'textarea'})
    receipt_item = TextAreaField('receipt_item', render_kw={'class': 'textarea'})
    tax_id = TextAreaField('tax_id', render_kw={'class': 'textarea'})
    address = TextAreaField('address', render_kw={'class': 'textarea'})
    shipping_address = TextAreaField('shipping_address', render_kw={'class': 'textarea'})
    paid_date = DateField()
    paid_time = TimeField()
    upload_file = FormField(CMTESponsorDocForm, default=CMTESponsorDoc)


class CMTESponsorReceiptDocForm(ModelForm):
    class Meta:
        model = CMTEReceiptDoc
        only = ['note']

    upload_file = FileField('Slip Upload')
    note = TextAreaField('คำอธิบาย', render_kw={'class': 'textarea'})


class CMTESponsorReceiptForm(FlaskForm):
    upload_file = FormField(CMTESponsorReceiptDocForm, default=CMTEReceiptDoc)


class CMTEPaymentForm(FlaskForm):
    class Meta:
        model = CMTEEventSponsor

    name = TextAreaField('name', render_kw={'class': 'textarea'})
    receipt_item = TextAreaField('receipt_item', render_kw={'class': 'textarea'})
    tax_id = TextAreaField('tax_id', render_kw={'class': 'textarea'})
    address = TextAreaField('address', render_kw={'class': 'textarea'})
    shipping_address = TextAreaField('shipping_address', render_kw={'class': 'textarea'})
    upload_file = FormField(CMTEEventDocForm, default=CMTEEventDoc)


class CMTEParticipantFileUploadForm(FlaskForm):
    upload_file = FileField('ไฟล์รายชื่อผู้เข้าร่วม', validators=[DataRequired(), FileAllowed(['xlsx'])])
    evidence_file = FileField('ไฟล์หลักฐาน', validators=[FileAllowed(['pdf']), DataRequired()])


class CMTEAdminParticipantFileUploadForm(FlaskForm):
    upload_file = FileField('ไฟล์รายชื่อผู้เข้าร่วม', validators=[DataRequired(), FileAllowed(['xlsx'])])
    evidence_file = FileField('ไฟล์หลักฐาน', validators=[FileAllowed(['pdf'])])


class CMTEAdminEventTypeForm(ModelForm):
    class Meta:
        model = CMTEEventType
        exclude = ['created_at', 'updated_at']


class CMTEAdminEventActivityForm(ModelForm):
    class Meta:
        model = CMTEEventActivity
        exclude = ['created_at', 'updated_at']

    event_type = QuerySelectField('ประเภทกิจกรรม', query_factory=lambda: CMTEEventType.query.all())
    fee_rates = QuerySelectMultipleField(query_factory=lambda: CMTEEventFeeRate.query.all(),
                                         allow_blank=True,
                                         widget=ListWidget(prefix_label=False),
                                         option_widget=CheckboxInput())
