from flask import Blueprint

inst = Blueprint('inst', __name__, url_prefix='/institutions')

from . import views