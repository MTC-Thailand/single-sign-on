import pandas as pd
from flask import render_template, request
from flask_login import login_required

from app import db
from app.admin import webadmin
from app.members.models import License


@webadmin.route('/')
@login_required
def index():
    return render_template('webadmin/index.html')


@webadmin.route('/upload/renew', methods=['GET', 'POST'])
@login_required
def upload_renew():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl')
        for idx, row in df.iterrows():
            license = License.query.filter_by(number=str(int(row['license_no']))).first()
            if license:
                license.start_date = start_date=row['renew_start_date']
                license.end_date = end_date=row['renew_end_date']
                license.issue_date = row['renew_start_date']
                db.session.add(license)
                if row['type'] == 'renew_name':
                    member = license.member
                    member.th_firstname = row['firstname']
                    member.th_lastname = row['lastname']
                    db.session.add(member)
            db.session.commit()
            return 'Update completed.'
    return render_template('webadmin/upload_renew.html')