from flask_wtf import FlaskForm
from wtforms_alchemy import model_form_factory, QuerySelectField

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
    fee_rate = QuerySelectField('อัตราค่าธรรมเนียม', query_factory=lambda: CMTEEventFeeRate.query.all())