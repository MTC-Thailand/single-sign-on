from datetime import date, datetime

import arrow
import pandas as pd
from dateutil.relativedelta import relativedelta
from flask import render_template, request, url_for, make_response, flash, redirect, abort
from flask_login import login_required
from sqlalchemy import or_

from app import db, admin_permission
from app.admin import webadmin
from app.admin.forms import MemberInfoAdminForm, LicenseAdminForm, MemberCertificateAdminForm
from app.cmte.models import CMTEFeePaymentRecord
from app.members.forms import MemberInfoForm, MemberUsernamePasswordForm, LicenseRenewalForm
from app.members.models import License, LicenseRenewal, Member, MemberAddress, MemberCertificate


def _parse_excel_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    if isinstance(value, (int, float)):
        try:
            return pd.to_datetime(value, unit='D', origin='1899-12-30').date()
        except (ValueError, TypeError, OverflowError):
            pass
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
        return value

    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return None
    return parsed.date()


def _get_row_value(row, column_name, default=None):
    if column_name in row.index:
        value = row[column_name]
    else:
        normalized_name = str(column_name).strip().lower()
        matched_column = next(
            (name for name in row.index if str(name).strip().lower() == normalized_name),
            None,
        )
        if matched_column is None:
            return default
        value = row[matched_column]
    if pd.isna(value):
        return default
    return value


def _get_first_row_value(row, *column_names, default=None):
    for column_name in column_names:
        value = _get_row_value(row, column_name, default=None)
        if value is not None:
            return value
    return default


def _apply_license_renewal(member_id, license_number, issue_date, start_date, status='ปกติ'):
    latest_license = License.query.filter_by(member_id=member_id) \
        .order_by(License.end_date.desc()).first()
    end_date = start_date + relativedelta(years=5, days=-1) if start_date else None

    if latest_license and start_date:
        renewal = LicenseRenewal.query.filter_by(
            license=latest_license,
            start_date=start_date,
        ).first()
        if not renewal:
            renewal = LicenseRenewal(license=latest_license)
        renewal.issue_date = issue_date
        renewal.start_date = start_date
        renewal.end_date = end_date
        db.session.add(renewal)

        # Only promote the base license row when the new renewal starts
        # after the currently stored license period ends. Overlapping
        # renewals should remain historical records only.
        if latest_license.end_date and start_date > latest_license.end_date:
            latest_license.number = license_number
            latest_license.issue_date = issue_date
            latest_license.start_date = start_date
            latest_license.end_date = end_date
            latest_license.status = status
            db.session.add(latest_license)
        return latest_license

    if not latest_license:
        latest_license = License(member_id=member_id, number=license_number)
    latest_license.number = license_number
    latest_license.issue_date = issue_date
    latest_license.start_date = start_date
    latest_license.end_date = end_date
    latest_license.status = status
    db.session.add(latest_license)
    return latest_license


@webadmin.route('/')
@login_required
@admin_permission.require(http_exception=403)
def index():
    return render_template('webadmin/index.html')


@webadmin.route('/upload/renew', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def upload_renew():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl')
        for idx, row in df.iterrows():
            license = License.query.filter_by(number=str(int(row['license_no']))).first()
            renew_start_date = _parse_excel_date(_get_row_value(row, 'renew_start_date'))
            issue_date = _parse_excel_date(_get_row_value(row, 'start_date'))
            if license and renew_start_date and issue_date:
                _apply_license_renewal(
                    member_id=license.member_id,
                    license_number=license.number,
                    issue_date=issue_date,
                    start_date=renew_start_date,
                )
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
@admin_permission.require(http_exception=403)
def upload_new():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(f, engine='openpyxl', dtype={'telephone_number': str})
        for idx, row in df.iterrows():
            dob = _parse_excel_date(_get_first_row_value(row, 'dob', 'birthday', 'date_of_birth', 'birth_date'))
            has_traditional_fee = _get_row_value(row, 'form_tradition') == 1
            payment_date = _get_row_value(row, 'payment_date')
            license_start_date = _parse_excel_date(_get_row_value(row, 'license_begin_date'))
            license_end_date = _parse_excel_date(_get_row_value(row, 'license_exp_date'))
            license_issue_date = _parse_excel_date(_get_row_value(row, 'approve_date'))
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
                                tel=row['telephone_number'],
                                dob=dob,
                                first_license_issue_date=license_issue_date
                                )
                db.session.add(member)
                license = License.query.filter_by(number=str(int(row['license_no']))).first()
                if not license:
                    license = License(start_date=license_start_date,
                                      end_date=license_end_date,
                                      issue_date=license_issue_date,
                                      number=str(row['license_no']),
                                      member=member)
                else:
                    license.start_date = license_start_date
                    license.end_date = license_end_date
                    license.issue_date = license_issue_date
                db.session.add(license)
            else:
                member_updates = {
                    'prefix': 'th_title',
                    'firstnameTH': 'th_firstname',
                    'lastnameTH': 'th_lastname',
                    'firstnameEN': 'en_firstname',
                    'lastnameEN': 'en_lastname',
                    'mem_id_txt': 'number',
                    'email': 'email',
                    'telephone_number': 'tel',
                }
                for column_name, attr_name in member_updates.items():
                    value = _get_row_value(row, column_name)
                    if value is not None:
                        setattr(member, attr_name, value)
                if dob is not None:
                    member.dob = dob
                if member.first_license_issue_date is None and license_issue_date is not None:
                    member.first_license_issue_date = license_issue_date
                db.session.add(member)
                license = License.query.filter_by(number=str(int(row['license_no']))).first()
                if license:
                    license.start_date = license_start_date
                    license.end_date = license_end_date
                    license.issue_date = license_issue_date
                    db.session.add(license)
            # The source spreadsheet uses form_tradition as a fee-paid flag for the traditional fee flow.
            if has_traditional_fee and payment_date is not None:
                cmte_payment_record = member.license.cmte_fee_payment_records.filter_by(
                    start_date=member.license.start_date,
                    end_date=member.license.end_date,
                    license=member.license).first()
                if not cmte_payment_record:
                    cmte_payment_record = CMTEFeePaymentRecord(
                        start_date=member.license.start_date,
                        end_date=member.license.end_date,
                        payment_datetime=payment_date,
                        license=member.license,
                    )
                    db.session.add(cmte_payment_record)
        db.session.commit()
        return 'Upload completed.'
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/update/phones', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
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
    address_sections = (
        (0, 2, 'working'),
        (1, 3, 'home'),
        (2, 1, 'mailing'),
    )
    form = MemberInfoAdminForm()

    if request.method == 'GET':
        form.pid.data = member.pid
        form.th_title.data = member.th_title
        form.th_firstname.data = member.th_firstname
        form.th_lastname.data = member.th_lastname
        form.en_title.data = member.en_title
        form.en_firstname.data = member.en_firstname
        form.en_lastname.data = member.en_lastname
        form.dob.data = member.dob
        form.tel.data = member.tel
        form.email.data = member.email
        form.status.data = member.status
        form.first_license_issue_date.data = member.first_license_issue_date

        if member.license:
            form.license.form.process(obj=member.license)

        for index, address_type, _ in address_sections:
            address = member.get_address(address_type)
            if address:
                form.addresses[index].form.process(obj=address)
            form.addresses[index].address_type.data = address_type

    if form.validate_on_submit():
        member.pid = form.pid.data
        member.th_title = form.th_title.data
        member.th_firstname = form.th_firstname.data
        member.th_lastname = form.th_lastname.data
        member.en_title = form.en_title.data
        member.en_firstname = form.en_firstname.data
        member.en_lastname = form.en_lastname.data
        member.dob = form.dob.data
        member.tel = form.tel.data
        member.email = form.email.data
        member.status = form.status.data
        member.first_license_issue_date = form.first_license_issue_date.data

        if member.license:
            form.license.form.populate_obj(member.license)

        existing_addresses = {}
        duplicate_addresses = []
        for addr in member.addresses:
            if addr.address_type in existing_addresses:
                duplicate_addresses.append(addr)
            else:
                existing_addresses[addr.address_type] = addr

        address_fields = (
            'street_number',
            'alley',
            'street',
            'village',
            'district',
            'city',
            'province',
            'zipcode',
        )

        for index, address_type, _ in address_sections:
            address_form = form.addresses[index]
            has_value = any(address_form[field].data for field in address_fields)
            address = existing_addresses.get(address_type)

            if not has_value:
                if address:
                    db.session.delete(address)
                continue

            if address is None:
                address = MemberAddress(member=member, address_type=address_type)

            address_form.form.populate_obj(address)
            address.address_type = address_type
            db.session.add(address)

        for address in duplicate_addresses:
            db.session.delete(address)

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
        latest_license = License.query.filter_by(member_id=member.id) \
            .order_by(License.end_date.desc()).first()
        license = License(member_id=member.id)
        if latest_license:
            license.number = latest_license.number
            license.status = latest_license.status
        form = LicenseAdminForm(obj=license)
        if request.method == 'POST':
            if form.validate_on_submit():
                _apply_license_renewal(
                    member_id=member.id,
                    license_number=form.number.data,
                    issue_date=form.issue_date.data,
                    start_date=form.start_date.data,
                    status='ปกติ',
                )
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


@webadmin.route('/members/<int:member_id>/certificates/new', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def create_member_certificate(member_id):
    member = Member.query.get(member_id)
    if not member:
        abort(404)

    certificate = MemberCertificate(member=member)
    form = MemberCertificateAdminForm(obj=certificate)

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(certificate)
            certificate.member = member
            db.session.add(certificate)
            db.session.commit()
            flash('เพิ่มประกาศนียบัตรเรียบร้อย', 'success')
            resp = make_response()
            resp.headers['HX-Refresh'] = 'true'
            return resp
        else:
            print(form.errors)

    return render_template(
        'webadmin/certificate_form.html',
        member=member,
        member_id=member_id,
        form=form,
        form_action=url_for('webadmin.create_member_certificate', member_id=member_id),
        modal_title='New Certificate',
    )


@webadmin.route('/members/<int:member_id>/certificates/<int:certificate_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def edit_member_certificate(member_id, certificate_id):
    member = Member.query.get(member_id)
    certificate = MemberCertificate.query.get(certificate_id)
    if not member or not certificate or certificate.member_id != member.id:
        abort(404)

    form = MemberCertificateAdminForm(obj=certificate)

    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(certificate)
            certificate.member = member
            db.session.add(certificate)
            db.session.commit()
            flash('แก้ไขประกาศนียบัตรเรียบร้อย', 'success')
            resp = make_response()
            resp.headers['HX-Refresh'] = 'true'
            return resp
        else:
            print(form.errors)

    return render_template(
        'webadmin/certificate_form.html',
        member=member,
        member_id=member_id,
        form=form,
        form_action=url_for('webadmin.edit_member_certificate', member_id=member_id, certificate_id=certificate_id),
        modal_title='Edit Certificate',
    )


@webadmin.route('/members/<int:member_id>/renewals', methods=['GET'])
@login_required
@admin_permission.require(http_exception=403)
def renewal_history(member_id):
    member = Member.query.get(member_id)
    renewals = member.license.renews if member and member.license else []
    return render_template('webadmin/renewal_history.html', member=member, renewals=renewals)


@webadmin.route('/members/<int:member_id>/renewals/<int:renewal_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def edit_renewal(member_id, renewal_id):
    member = Member.query.get(member_id)
    renewal = LicenseRenewal.query.get(renewal_id)
    if not member or not renewal or renewal.license.member_id != member.id:
        abort(404)
    form = LicenseRenewalForm(obj=renewal)
    if form.validate_on_submit():
        form.populate_obj(renewal)
        db.session.add(renewal)
        db.session.commit()
        flash('บันทึกข้อมูลการต่ออายุเรียบร้อยแล้ว', 'success')
        return redirect(url_for('webadmin.renewal_history', member_id=member.id))
    return render_template('webadmin/renewal_form.html', form=form, renewal=renewal, member=member)


@webadmin.route('/members/<int:member_id>/renewals/<int:renewal_id>/delete', methods=['POST'])
@login_required
@admin_permission.require(http_exception=403)
def delete_renewal(member_id, renewal_id):
    member = Member.query.get(member_id)
    renewal = LicenseRenewal.query.get(renewal_id)
    if not member or not renewal or renewal.license.member_id != member.id:
        abort(404)
    db.session.delete(renewal)
    db.session.commit()
    flash('ลบข้อมูลการต่ออายุเรียบร้อยแล้ว', 'success')
    return redirect(url_for('webadmin.renewal_history', member_id=member.id))


@webadmin.route('/members/password-view', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def view_member_password():
    if request.method == 'POST':
        license_no = request.form.get('license_no')
        license = License.query.filter_by(number=license_no).first()
        if not license:
            return 'No license found.'
        else:
            return render_template('webadmin/partials/member_password_summary.html', member=license.member)
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
        return render_template('webadmin/partials/member_password_summary.html', member=member)
    else:
        print(form.errors)


@webadmin.route('/api/members/search', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def search_member():
    query = request.args.get('query')
    if query:
        licenses = [(license.member.license, license.member) for license in License.query.filter_by(number=query)]
        if not licenses:
            members = Member.query.filter(or_(Member.th_firstname.like(f'%{query}%'),
                                              Member.th_lastname.like(f'%{query}%'),
                                              Member.tel.like(f'%{query}%')))
            licenses = [(member.license, member) for member in members]
        rows = []
        for lic, member in licenses:
            if not lic:
                continue
            if lic.is_expired:
                status_class = 'is-danger'
                status_text = 'หมดอายุ'
            elif lic.status:
                if lic.status == 'ปกติ':
                    status_class = 'is-success'
                else:
                    status_class = 'is-warning'
                status_text = lic.status
            else:
                status_class = 'is-success'
                status_text = 'ปกติ'
            rows.append({
                'member': member,
                'license': lic,
                'status_class': status_class,
                'status_text': status_text,
                'edit_url': url_for('webadmin.edit_member_info', member_id=member.id),
                'scores_url': url_for('cmte.admin_check_member_cmte_scores', member_id=lic.member_id),
            })
        return render_template('webadmin/partials/member_search_results.html', rows=rows)
    return 'Waiting for a search query...'
