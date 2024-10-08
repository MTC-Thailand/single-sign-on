from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask_principal import identity_loaded, UserNeed

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

admin.add_view(ModelView(CMTEEvent, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventCategory, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventType, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventFormat, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventSponsor, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventFeeRate, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventCode, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEFeePaymentRecord, db.session, category='Members'))

from app.members.models import Member, License

admin.add_view(ModelView(License, db.session, category='Members'))
admin.add_view(ModelView(Member, db.session, category='Members', endpoint='members_'))


@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
    # Set the identity user object
    identity.user = current_user

    # Add the UserNeed to the identity
    if hasattr(current_user, 'id'):
        identity.provides.add(UserNeed(current_user.id))

    # Assuming the User model has a list of roles, update the
    # identity with the roles that the user provides
    if hasattr(current_user, 'roles'):
        for role in current_user.roles:
            identity.provides.add(role.to_tuple())


@login_manager.user_loader
def load_user(user_id):
    if request.blueprint == 'member':
        return Member.query.get(int(user_id))

    return User.query.filter_by(id=user_id, is_activated=True).first()


from app.roles import init_roles

init_roles(app)