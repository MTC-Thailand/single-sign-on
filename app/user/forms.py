from wtforms import PasswordField, StringField, FieldList, TextAreaField, FormField
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, EqualTo
from wtforms_alchemy import model_form_factory


from app import db
from app.models import Client, User
from app.user.models import CandidateProfile, CandidateDegree, CandidateExperience, CandidateVision, \
    CandidateJobPosition

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


class CandidateJobPositionForm(ModelForm):
    class Meta:
        model = CandidateJobPosition


class CandidateDegreeForm(ModelForm):
    class Meta:
        model = CandidateDegree


class CandidateExperienceForm(ModelForm):
    class Meta:
        model = CandidateExperience


class CandidateVisionForm(ModelForm):
    class Meta:
        model = CandidateVision


class CandidateProfileForm(ModelForm):
    class Meta:
        model = CandidateProfile

    job_positions = FieldList(FormField(CandidateJobPositionForm, default=CandidateJobPosition), min_entries=3)
    degrees = FieldList(FormField(CandidateDegreeForm, default=CandidateDegree), min_entries=3)
    experiences = FieldList(FormField(CandidateExperienceForm, default=CandidateExperience), min_entries=3)
    visions = FieldList(FormField(CandidateVisionForm, default=CandidateVision), min_entries=3)

