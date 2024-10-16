from flask import Blueprint

webadmin = Blueprint('webadmin', __name__, url_prefix='/webadmin')

from . import views