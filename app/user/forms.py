from wtforms import PasswordField, StringField
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired
from wtforms_alchemy import model_form_factory


from app import db
from app.models import Client

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class ClientRegisterForm(ModelForm):
    class Meta:
        model = Client
        only = ['name', 'email', 'company']