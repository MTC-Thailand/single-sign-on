from flask_admin.contrib.sqla import ModelView
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

from app.cmte.models import *

admin.add_view(ModelView(CMTEEvent, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventCategory, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventType, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventFormat, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventSponsor, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventFeeRate, db.session, category='CMTE Events'))
admin.add_view(ModelView(CMTEEventCode, db.session, category='CMTE Events'))

from app.members.models import Member, License

admin.add_view(ModelView(License, db.session, category='Members'))
admin.add_view(ModelView(Member, db.session, category='Members', endpoint='members_'))
