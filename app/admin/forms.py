from flask_wtf import FlaskForm
from wtforms_alchemy import model_form_factory, ModelFormField

from app import db
from app.members.models import Member, License

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class LicenseAdminForm(ModelForm):
    class Meta:
        model = License
        date_format = '%d/%m/%Y'


class MemberInfoAdminForm(ModelForm):
    class Meta:
        model = Member
        date_format = '%d/%m/%Y'
        exclude = ['number']
    license = ModelFormField(LicenseAdminForm, default=License)
