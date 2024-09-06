from app.institutions import inst


@inst.route('/institutions')
def index():
    return 'Index page'