from flask_principal import Permission
from sqlalchemy.exc import ProgrammingError

from app.models import Role

admin_permission = Permission()
cmte_admin_permission = Permission()
cmte_org_admin_permission = Permission()


def init_roles(app):
    with app.app_context():
        try:
            admin_role = Role.query.filter_by(role_need='Admin', action_need=None, resource_id=None).first()
            cmte_admin_role = Role.query.filter_by(role_need='CMTEAdmin', action_need=None, resource_id=None).first()
            cmte_org_admin_role = Role.query.filter_by(role_need='CMTEOrgAdmin', action_need=None, resource_id=None).first()
        except ProgrammingError:
            pass
        else:
            global admin_permission
            global cmte_admin_permission
            global cmte_org_admin_permission

            if admin_role:
                admin_permission = Permission(admin_role.to_tuple())
            if cmte_admin_role:
                cmte_admin_permission = Permission(cmte_admin_role.to_tuple())
            if cmte_org_admin_role:
                cmte_org_admin_permission = Permission(cmte_org_admin_role.to_tuple())
