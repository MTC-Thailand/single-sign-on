from flask import session
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask_principal import identity_loaded, UserNeed, RoleNeed, ActionNeed
import arrow

from app import create_app, admin

app = create_app()

from app.models import *


class ClientAdminView(ModelView):
    column_display_pk = True
    form_columns = ['id', 'name']

    def create_model(self, form):
        client = Client(id=form.id.data, name=form.name.data)
        client.generate_api_key()
        return client


admin.add_view(ModelView(User, db.session))
admin.add_view(ClientAdminView(Client, db.session))
admin.add_view(ModelView(Role, db.session, category='Permissions'))

from app.cmte.models import *

admin.add_view(ModelView(CMTEEvent, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventCategory, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventType, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventFormat, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventSponsor, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventFeeRate, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventCode, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventDoc, db.session, category='CMTE'))
admin.add_view(ModelView(CMTEEventParticipationRecord, db.session, category='CMTE'))

admin.add_view(ModelView(CMTEFeePaymentRecord, db.session, category='Members'))

from app.members.models import Member, License

admin.add_view(ModelView(License, db.session, category='Members'))
admin.add_view(ModelView(Member, db.session, category='Members', endpoint='members_'))


@login_manager.user_loader
def load_user(user_id):
    if session.get('login_as') == 'member':
        return Member.query.get(int(user_id))
    elif session.get('login_as') == 'cmte_sponsor_admin':
        return CMTESponsorMember.query.get(int(user_id))

    return User.query.filter_by(id=user_id, is_activated=True).first()


@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
    # Set the identity user object
    identity.user = current_user

    # Add the UserNeed to the identity
    if hasattr(current_user, 'unique_id'):
        identity.provides.add(UserNeed(current_user.unique_id))

    # Assuming the User model has a list of roles, update the
    # identity with the roles that the user provides
    if isinstance(current_user, User):
        for role in current_user.roles:
            identity.provides.add(RoleNeed(role.role_need))
    elif isinstance(current_user, CMTESponsorMember):
        identity.provides.add(RoleNeed('CMTESponsorAdmin'))
        if current_user.sponsor.expire_date > arrow.now('Asia/Bangkok').date():
            print('sponsor is valid')
            identity.provides.add(ActionNeed('manageEvents'))
