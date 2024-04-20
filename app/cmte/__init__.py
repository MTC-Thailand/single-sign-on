from flask import Blueprint

cmte_bp = Blueprint('cmte', __name__, url_prefix='/cmte')

from . import views