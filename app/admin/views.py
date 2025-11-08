from datetime import datetime

import arrow
import pandas as pd
from flask import render_template, request, url_for, make_response, flash, redirect
from flask_login import login_required
from sqlalchemy import or_

from app import db, admin_permission
from app.admin import webadmin
from app.admin.forms import MemberInfoAdminForm, LicenseAdminForm
from app.cmte.models import CMTEFeePaymentRecord
from app.members.forms import MemberInfoForm, MemberUsernamePasswordForm
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
            if license and not pd.isnull(row['renew_end_date']) and not pd.isnull(row['renew_start_date']):
                license.start_date = row['renew_start_date']
                license.end_date = row['renew_end_date']
                license.issue_date = row['renew_start_date']
                db.session.add(license)
                if row['type'] == 'renew_name':
                    member = license.member
                    member.th_firstname = row['firstname']
                    member.th_lastname = row['lastname']
                    db.session.add(member)
        db.session.commit()
        return 'Update completed. <a href="{}">Back</a>'.format(url_for('webadmin.index'))
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/upload/new', methods=['GET', 'POST'])
@login_required
def upload_new():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl', dtype={'telephone_number': str})
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
                cmte_payment_record = member.license.cmte_fee_payment_records.filter_by(
                    start_date=member.license.start_date,
                    end_date=member.license.end_date,
                    license=member.license).first()
                if not cmte_payment_record:
                    cmte_payment_record = CMTEFeePaymentRecord(
                        start_date=member.license.start_date,
                        end_date=member.license.end_date,
                        payment_datetime=row['payment_date'],
                        license=member.license,
                    )
                    db.session.add(cmte_payment_record)
        db.session.commit()
        return 'Upload completed.'
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/update/phones', methods=['GET', 'POST'])
@login_required
def upload_phone_numbers():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl', dtype={'phone_number': str, 'pid_left': str})
        fails = []
        for idx, row in df.iterrows():
            if pd.isna(row['pid_left']) or pd.isna(row['phone_number']):
                continue
            member = Member.query.filter_by(pid=row['pid_left']).first()
            if not member:
                fails.append({'pid': row['pid_left'],
                              'phone_number': row['phone_number'],
                              'firstname': row['th_firstname_left'],
                              'lastname': row['th_lastname_left'],
                              })
            else:
                member.tel = row['phone_number']
                member.updated_at = arrow.now('Asia/Bangkok').datetime
        db.session.commit()
        return pd.DataFrame(fails).to_html()
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/members/<int:member_id>/info', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def edit_member_info(member_id):
    member = Member.query.get(member_id)
    form = MemberInfoAdminForm(obj=member)
    if form.validate_on_submit():
        form.populate_obj(member)
        db.session.add(member)
        db.session.commit()
        flash('บันทึกข้อมูลเรียบร้อย', 'success')
        return redirect(url_for('webadmin.index'))
    else:
        if form.errors:
            flash(f'{form.errors}', 'danger')
    return render_template('webadmin/member_info_form.html', form=form, member=member)


@webadmin.route('/members/<int:member_id>/licenses/<license_action>', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def edit_license(member_id, license_action):
    member = Member.query.get(member_id)
    if license_action == 'renew':
        license = License.query.filter_by(member_id=member.id) \
            .order_by(License.end_date.desc()).first()
        form = LicenseAdminForm(obj=license)
        if request.method == 'POST':
            if form.validate_on_submit():
                form.populate_obj(license)
                db.session.add(license)
                db.session.commit()
                flash('ต่ออายุใบอนุญาตแล้ว', 'success')
                resp = make_response()
                resp.headers['HX-Refresh'] = 'true'
                return resp
            else:
                print(form.errors)
    return render_template('webadmin/license_form.html',
                           license_action=license_action,
                           member_id=member_id,
                           form=form)


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
            <div class="notification">
            <p>ชื่อ {license.member.th_fullname}</p>
            <p>หมายเลขโทรศัพท์ {license.member.tel}</p>
            <p>วันเดือนปีเกิด {license.member.dob}</p>
            <p>username: {license.member.username}</p>
            <p>password: {license.member.password}</p>
            </div>
            <a class="button" hx-swap="innerHTML"
                hx-target="#password-text"
                hx-get="{url_for('webadmin.edit_member_password', member_id=license.member.id)}">
                <span class="icon">
                    <i class="fas fa-pencil-alt"></i>
                </span>
                <span>Edit</span>
            </a>
            '''
    return render_template('webadmin/password_view.html')


@webadmin.route('/members/<int:member_id>/password-view/edit', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def edit_member_password(member_id):
    member = Member.query.get(member_id)
    form = MemberUsernamePasswordForm(obj=member)
    if request.method == 'GET':
        return render_template('webadmin/partials/edit_password_form.html', form=form, member=member)
    if form.validate_on_submit():
        form.populate_obj(member)
        db.session.add(member)
        db.session.commit()
        return f'''
        <p>หมายเลขโทรศัพท์ {member.tel}</p>
        <p>วันเดือนปีเกิด {member.dob}</p>
        <p>username: {member.username}</p>
        <p>password: {member.password}</p>
        <a class="button" hx-swap="innerHTML"
            hx-target="#password-text"
            hx-get="{url_for('webadmin.edit_member_password', member_id=member_id)}">
            <span class="icon">
                <i class="fas fa-pencil-alt"></i>
            </span>
            <span>Edit</span>
        </a>
        '''
    else:
        print(form.errors)


@webadmin.route('/api/members/search', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def search_member():
    query = request.args.get('query')
    if query:
        template = '''<table class="table is-fullwidth is-striped">'''
        template += '''
        <thead><th>Name</th><th>License No.</th><th>License Date</th><th>License Status</th><th>Phone</th><th colspan="2">Valid CMTE</th></thead>
        <tbody>
        '''
        licenses = [(license.member.license, license.member) for license in License.query.filter_by(number=query)]
        if not licenses:
            members = Member.query.filter(or_(Member.th_firstname.like(f'%{query}%'),
                                              Member.th_lastname.like(f'%{query}%'),
                                              Member.tel.like(f'%{query}%')))
            licenses = [(member.license, member) for member in members]
        for lic, member in licenses:
            url = url_for('webadmin.edit_member_info', member_id=member.id)
            status_tag = '<span class="tag {}">{}</span>'
            if lic.is_expired:
                lic_status = status_tag.format('is-danger', 'หมดอายุ')
            elif lic.status:
                if lic.status == 'ปกติ':
                    lic_status = status_tag.format('is-success', lic.status)
                else:
                    lic_status = status_tag.format('is-warning', lic.status)
            else:
                lic_status = status_tag.format('is-success', 'ปกติ')
            if lic:
                template += f'''<tr><td>{member.th_fullname}</td><td>{lic.number}</td><td>{lic.dates}</td><td>{lic_status}</td><td>{lic.member.tel}</td><td><a href="{url_for('cmte.admin_check_member_cmte_scores', member_id=lic.member_id)}">{lic.valid_cmte_scores}</a></td><td><a href={url}>แก้ไขข้อมูล</a></td></tr>'''
            else:
                lic = License.query.filter_by(member_id=member.id).first()
                template += f'''<tr><td>{member.th_fullname}</td><td>{lic.number}</td><td>{lic.dates}</td><td>{lic_status}</td><td>{lic.member.tel}</td><<td><a href="{url_for('cmte.admin_check_member_cmte_scores', member_id=lic.member_id)}">{lic.valid_cmte_scores}</a></td><td><a href={url}>แก้ไขข้อมูล</a></td></tr>'''
        template += '</tbody></table>'
        return make_response(template)
    return 'Waiting for a search query...'
