import os
import requests

from flask import render_template, make_response

from app.members import member_blueprint as member
from app.members.forms import MemberSearchForm

INET_API_TOKEN = os.environ.get('INET_API_TOKEN')
BASE_URL = 'https://uat-mtc.thaijobjob.com'


@member.route('/search', methods=['GET', 'POST'])
def search_member():
    form = MemberSearchForm()
    if form.validate_on_submit():
        if form.firstname.data and form.lastname.data:
            response = requests.post(f'{BASE_URL}/GetdataBylicenseAndfirstnamelastname',
                                     params={'search': f'{form.firstname.data} {form.lastname.data}'},
                                     headers={'Authorization': 'Bearer {}'.format(INET_API_TOKEN)})
            print(response.text)
            resp = make_response(f'{form.firstname.data} {form.lastname.data}')
        elif form.license_id.data:
            resp = make_response(form.license_id.data)
        else:
            resp = make_response('Error, no input found.')

        return resp

    return render_template('members/search_form.html', form=form)
