from flask_wtf import FlaskForm
from wtforms_alchemy import model_form_factory

from app import db
from app.members.models import Member

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class MemberInfoAdminForm(ModelForm):
    class Meta:
        model = Member
