import json
import arrow
import os
from pprint import pprint

import requests
import pandas as pd

from flask import render_template, make_response
from sqlalchemy import create_engine

from app.members import member_blueprint as member
from app.members.forms import MemberSearchForm

INET_API_TOKEN = os.environ.get('INET_API_TOKEN')
# BASE_URL = 'https://mtc.thaijobjob.com/api/user'
BASE_URL = 'https://uat-mtc.thaijobjob.com/api/user'
MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE')

template = '''
<div class="box">
<span class="label">ชื่อ นามสกุล</span> <span>{} {}</span><br>
<span class="label">Name</span> <span>{} {}</span><br>
<span class="label">หมายเลขใบอนุญาต</span> <span>{}</span><br>
<span class="label">วันหมดอายุ</span> <span class="{}">{} ({})</span><br>
<span class="label">สถานะใบอนุญาต</span> <span class="tag {}">{}</span>
</div>
'''

# template = '''
# <div class="box">
# <img src="data:image/png;base64, {}">
# <span class="label">ชื่อ นามสกุล</span> <span>{} {}</span><br>
# <span class="label">Name</span> <span>{} {}</span><br>
# <span class="label">หมายเลขใบอนุญาต</span> <span>{}</span><br>
# <span class="label">วันหมดอายุ</span> <span>{}</span><br>
# <span class="label">สถานะใบอนุญาต</span> <span>{}</span>
# </div>
# '''


def load_from_mtc(firstname=None, lastname=None, license_id=None):
    engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
    engine.connect()
    if firstname and lastname:
        query = f'''
        SELECT member.mem_id, member.fname AS firstnameTH, member.lname AS lastnameTH, member.e_fname AS firstnameEN, member.e_lname AS lastnameEN 
        FROM member WHERE member.fname='{firstname}' AND member.lname='{lastname}';
        '''
        data = pd.read_sql_query(query, con=engine)
        data = data.squeeze().to_dict()

        query = f'''
        SELECT lic_mem.lic_id AS license_no, lic_mem.lic_exp_date AS end_date,lic_mem.lic_b_date,
        lic_status.lic_status_name AS status_license FROM lic_mem
        INNER JOIN lic_status ON lic_mem.lic_status_id=lic_status.lic_status_id
        WHERE lic_mem.mem_id={data['mem_id']}
        '''
        lic_data = pd.read_sql_query(query, con=engine)
        lic_data = lic_data.squeeze().to_dict()
        data.update(lic_data)
    elif license_id:
        query = f'''
        SELECT lic_mem.mem_id, lic_mem.lic_id AS license_no, lic_mem.lic_exp_date AS end_date,lic_mem.lic_b_date,
        lic_status.lic_status_name AS status_license FROM lic_mem
        INNER JOIN lic_status ON lic_mem.lic_status_id=lic_status.lic_status_id
        WHERE lic_mem.lic_id={license_id}
        '''
        lic_data = pd.read_sql_query(query, con=engine)
        data = lic_data.squeeze().to_dict()

        query = f'''
        SELECT member.mem_id, member.fname AS firstnameTH, member.lname AS lastnameTH, member.e_fname AS firstnameEN, member.e_lname AS lastnameEN 
        FROM member WHERE member.mem_id={data['mem_id']};
        '''
        mem_data = pd.read_sql_query(query, con=engine)
        mem_data = mem_data.squeeze().to_dict()
        data.update(mem_data)

    return [data]


def check_license_status(delta, status):
    if status == 'ปกติ' and delta.days > 0:
        return 'ปกติ'
    elif status == 'ปกติ' and delta.days < 0:
        return 'หมดอายุ'
    else:
        return status


@member.route('/search', methods=['GET', 'POST'])
def search_member():
    form = MemberSearchForm()
    if form.validate_on_submit():
        message = ''
        if form.firstname.data and form.lastname.data:
            try:
                response = requests.get(f'{BASE_URL}/GetdataBylicenseAndfirstnamelastname',
                                         params={'search': f'{form.firstname.data} {form.lastname.data}'},
                                         headers={'Authorization': 'Bearer {}'.format(INET_API_TOKEN)}, stream=True, timeout=99)
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
                resp = make_response(str(e))
            else:
                try:
                    data_ = response.json().get('results', [])
                except requests.exceptions.JSONDecodeError as e:
                    data_ = load_from_mtc(form.firstname.data, form.lastname.data)
                    for rec in data_:
                        exp_date = arrow.get(rec.get('end_date', 'YYYY-MM-DD'))
                        delta = exp_date - arrow.now()
                        license_status = check_license_status(delta, rec.get('status_license'))
                        message += template.format(rec.get('firstnameTH'),
                                                   rec.get('lastnameTH'),
                                                   rec.get('firstnameEN'),
                                                   rec.get('lastnameEN'),
                                                   int(rec.get('license_no')),
                                                   'has-text-info' if delta.days > 0 else 'has-text-danger',
                                                   rec.get('end_date'),
                                                   exp_date.humanize(granularity=['year', 'day'], locale='th'),
                                                   'is-success' if license_status == 'ปกติ' else 'is-danger',
                                                   license_status,
                                                   )

                    resp = make_response(message)
                else:
                    if not data_:
                        data_ = load_from_mtc(form.firstname.data, form.lastname.data)
                    for rec in data_:
                        exp_date = arrow.get(rec.get('end_date', 'YYYY-MM-DD'))
                        delta = exp_date - arrow.now()
                        license_status = check_license_status(delta, rec.get('status_license'))
                        message += template.format(rec.get('firstnameTH'),
                                                   rec.get('lastnameTH'),
                                                   rec.get('firstnameEN'),
                                                   rec.get('lastnameEN'),
                                                   int(rec.get('license_no')),
                                                   'has-text-info' if delta.days > 0 else 'has-text-danger',
                                                   rec.get('end_date'),
                                                   exp_date.humanize(granularity=['year', 'day'], locale='th'),
                                                   'is-success' if license_status == 'ปกติ' else 'is-danger',
                                                   license_status,
                                                   )

                    resp = make_response(message)
        elif form.license_id.data:
            try:
                response = requests.get(f'{BASE_URL}/GetdataBylicenseAndfirstnamelastname',
                                        params={'search': f'{form.license_id.data}'},
                                        headers={'Authorization': 'Bearer {}'.format(INET_API_TOKEN)},
                                        stream=True, timeout=99,
                                        )
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
                resp = make_response(str(e))
            else:
                try:
                    data_ = response.json().get('results', [])
                except requests.exceptions.JSONDecodeError as e:
                    data_ = load_from_mtc(license_id=form.license_id.data)
                    for rec in data_:
                        exp_date = arrow.get(rec.get('end_date', 'YYYY-MM-DD'))
                        delta = exp_date - arrow.now()
                        license_status = check_license_status(delta, rec.get('status_license'))
                        message += template.format(rec.get('firstnameTH'),
                                                   rec.get('lastnameTH'),
                                                   rec.get('firstnameEN'),
                                                   rec.get('lastnameEN'),
                                                   int(rec.get('license_no')),
                                                   'has-text-info' if delta.days > 0 else 'has-text-danger',
                                                   rec.get('end_date'),
                                                   exp_date.humanize(granularity=['year', 'day'], locale='th'),
                                                   'is-success' if license_status == 'ปกติ' else 'is-danger',
                                                   license_status,
                                                   )
                    resp = make_response(message)
                else:
                    if not data_:
                        data_ = load_from_mtc(license_id=form.license_id.data)
                    for rec in data_:
                        exp_date = arrow.get(rec.get('end_date', 'YYYY-MM-DD'))
                        delta = exp_date - arrow.now()
                        license_status = check_license_status(delta, rec.get('status_license'))
                        message += template.format(
                            # rec.get('profile'),
                            rec.get('firstnameTH'),
                            rec.get('lastnameTH'),
                            rec.get('firstnameEN'),
                            rec.get('lastnameEN'),
                            int(rec.get('license_no')),
                            'has-text-info' if delta.days > 0 else 'has-text-danger',
                            rec.get('end_date'),
                            exp_date.humanize(granularity=['year', 'day'], locale='th'),
                            'is-success' if license_status == 'ปกติ' else 'is-danger',
                            license_status,
                        )

                    resp = make_response(message)
        else:
            resp = make_response('Error, no input found.')

        resp.headers['HX-Trigger-After-Swap'] = json.dumps({"stopLoading": "#submit-btn"})

        return resp

    return render_template('members/search_form.html', form=form)
