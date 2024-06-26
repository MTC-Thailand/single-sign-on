from flask_wtf import FlaskForm
from wtforms.validators import DataRequired
from wtforms_alchemy import model_form_factory, QuerySelectField
from wtforms import StringField

from app import db
from app.cmte.models import *

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class CMTEEventForm(ModelForm):
    class Meta:
        model = CMTEEvent
        datetime_format = '%d/%m/%Y %H:%M'

    event_type = QuerySelectField('ชนิดกิจกรรม', query_factory=lambda: CMTEEventType.query.all())


class ParticipantForm(ModelForm):
    class Meta:
        model = CMTEEventParticipationRecord