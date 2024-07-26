from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.validators import NumberRange
from wtforms_alchemy import model_form_factory, QuerySelectField
from wtforms import FieldList, FormField, StringField, DecimalField

from app import db
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


class CMTEEventForm(ModelForm):
    class Meta:
        model = CMTEEvent
        datetime_format = '%d/%m/%Y %H:%M'

    event_type = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventType.query.all())
    upload_files = FieldList(FormField(CMTEEventDocForm, default=CMTEEventDoc), min_entries=3)


class ParticipantForm(FlaskForm):
    license_number = StringField('License Number')
    score = DecimalField('Score', validators=[NumberRange(min=0)])