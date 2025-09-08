from wtforms import PasswordField, StringField
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, EqualTo
from wtforms_alchemy import model_form_factory


from app import db
from app.models import Client, User

BaseModelForm = model_form_factory(FlaskForm)


class ModelForm(BaseModelForm):
    @classmethod
    def get_session(self):
        return db.session


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class UserRegisterForm(ModelForm):
    class Meta:
        model = User
        only = ['username']
    new_password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('new_password')])


class ClientRegisterForm(ModelForm):
    class Meta:
        model = Client
        only = ['name', 'email', 'company']


class CandidateProfileForm(FlaskForm):
    title = StringField('คำนำหน้า', validators=[DataRequired()])
    firstname = StringField('ชื่อ', validators=[DataRequired()])
    lastname  = StringField('นามสกุล', validators=[DataRequired()])
    policy = StringField('นโยบาย', validators=[DataRequired()])

