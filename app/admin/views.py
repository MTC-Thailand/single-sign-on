import pandas as pd
from flask import render_template, request
from flask_login import login_required

from app import db, admin_permission
from app.admin import webadmin
from app.admin.forms import MemberInfoAdminForm
from app.cmte.models import CMTEFeePaymentRecord
from app.members.forms import MemberInfoForm
from app.members.models import License, Member


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


@webadmin.route('/upload/new', methods=['GET', 'POST'])
@login_required
def upload_new():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl')
        for idx, row in df.iterrows():
            member = Member.query.filter_by(pid=str(int(row['idcardnumber']))).first()
            if not member:
                member = Member(pid=str(row['idcardnumber']),
                                th_title=row['prefix'],
                                th_firstname=row['firstnameTH'],
                                th_lastname=row['lastnameTH'],
                                en_firstname=row['firstnameEN'],
                                en_lastname=row['lastnameEN'],
                                number=row['mem_id_txt'],
                                email=row['email'],
                                tel=row['telephone_number']
                                )
                db.session.add(member)
                print('adding new member: {}'.format(member.number))
                license = License.query.filter_by(number=str(int(row['license_no']))).first()
                if not license:
                    license = License(start_date=row['license_begin_date'],
                                      end_date=row['license_exp_date'],
                                      issue_date=row['approve_date'],
                                      number=str(row['license_no']),
                                      member=member)
                else:
                    license.start_date = row['license_begin_date']
                    license.end_date = row['license_exp_date']
                    license.issue_date = row['approve_date']
                db.session.add(license)
            if row['form_tradition'] == 1 and not pd.isna(row['payment_date']):
                cmte_payment_record = license.cmte_fee_payment_records.filter_by(
                    start_date=license.start_date,
                    end_date=license.end_date,
                    license=license).first()
                if not cmte_payment_record:
                    cmte_payment_record = CMTEFeePaymentRecord(
                        start_date=license.start_date,
                        end_date=license.end_date,
                        payment_datetime=row['payment_date'],
                        license=license,
                    )
                    db.session.add(cmte_payment_record)
        db.session.commit()
        return 'Upload completed.'
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/members/<int:member_id>/info', methods=['GET'])
@login_required
@admin_permission.require(http_exception=403)
def edit_member_info(member_id):
    member = Member.query.get(member_id)
    form = MemberInfoAdminForm(obj=member)
    return render_template('webadmin/member_info_form.html', form=form)


@webadmin.route('/members/password-view', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def view_member_password():
    if request.method == 'POST':
        license_no = request.form.get('license_no')
        license = License.query.filter_by(number=license_no).one()
        if not license:
            return 'No license found.'
        else:
            return f'''
            <p>หมายเลขโทรศัพท์ {license.member.tel}</p>
            <p>วันเดือนปีเกิด {license.member.dob}</p>
            <p>username: {license.member.username}</p>
            <p>password: {license.member.password}</p>
            '''
    return render_template('webadmin/password_view.html')




    member = Member.query.get()
    form = MemberInfoAdminForm(obj=member)
    return render_template('webadmin/member_info_form.html', form=form)
