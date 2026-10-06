from datetime import date, datetime

import arrow
import pandas as pd
from dateutil.relativedelta import relativedelta
from flask import render_template, request, url_for, make_response, flash, redirect, abort, jsonify
from flask_login import login_required
from sqlalchemy import func, or_

from app import db, admin_permission
from app.admin import webadmin
from app.admin.forms import MemberInfoAdminForm, LicenseAdminForm, MemberCertificateAdminForm
from app.cmte.models import CMTEEventParticipationRecord, CMTEFeePaymentRecord
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


def _normalize_excel_identifier(value):
    """Return spreadsheet identifiers without numeric formatting artifacts."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    value = str(value).strip()
    if value.endswith('.0') and value[:-2].isdigit():
        return value[:-2]
    return value


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


@webadmin.route('/member-dashboard', methods=['GET'])
@login_required
@admin_permission.require(http_exception=403)
def member_dashboard():
    return render_template('webadmin/member_dashboard.html')


def _build_member_dashboard_payload():
    today = date.today()

    def _calculate_age(dob):
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    total_members = Member.query.count()
    active_member_status_filter = or_(Member.status == 'ปกติ', Member.status.is_(None))
    active_members = Member.query.filter(active_member_status_filter).count()
    active_member_age_counts = {
        '20-30': 0,
        '30-40': 0,
        '40-50': 0,
        '50-60': 0,
        'over60': 0,
    }
    for (dob,) in Member.query.with_entities(Member.dob).filter(
        active_member_status_filter,
        Member.dob.isnot(None),
    ):
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if 20 <= age < 30:
            active_member_age_counts['20-30'] += 1
        elif 30 <= age < 40:
            active_member_age_counts['30-40'] += 1
        elif 40 <= age < 50:
            active_member_age_counts['40-50'] += 1
        elif 50 <= age < 60:
            active_member_age_counts['50-60'] += 1
        elif age >= 60:
            active_member_age_counts['over60'] += 1
    active_member_age_rows = [
        ['20-30', active_member_age_counts['20-30']],
        ['30-40', active_member_age_counts['30-40']],
        ['40-50', active_member_age_counts['40-50']],
        ['50-60', active_member_age_counts['50-60']],
        ['over60', active_member_age_counts['over60']],
    ]
    member_status_counts = {
        'ปกติ': 0,
        'ลาออก': 0,
        'พ้นสมาชิกภาพ': 0,
        'ตาย': 0,
    }
    for status, count in db.session.query(Member.status, func.count(Member.id)).group_by(Member.status):
        member_status_counts[status or 'ปกติ'] = member_status_counts.get(status or 'ปกติ', 0) + count
    member_status_rows = [[status, count] for status, count in member_status_counts.items()]
    total_licenses = License.query.count()
    first_license_issue_year = today.year - 9
    first_licenses_issued_by_year = {
        year: 0 for year in range(first_license_issue_year, today.year + 1)
    }
    for (issue_date,) in Member.query.with_entities(Member.first_license_issue_date).filter(
        Member.first_license_issue_date >= date(first_license_issue_year, 1, 1),
        Member.first_license_issue_date <= today,
    ):
        first_licenses_issued_by_year[issue_date.year] += 1
    first_licenses_issued_by_year_rows = [
        [str(year), first_licenses_issued_by_year[year]]
        for year in range(first_license_issue_year, today.year + 1)
    ]
    active_license_status_filter = or_(License.status == 'ปกติ', License.status.is_(None))
    active_licenses = License.query.filter(
        License.end_date >= today,
        active_license_status_filter,
    ).count()
    expired_licenses = License.query.filter(License.end_date < today).count()

    valid_cmte_scores_subquery = (
        db.session.query(
            CMTEEventParticipationRecord.license_number.label('license_number'),
            func.coalesce(func.sum(CMTEEventParticipationRecord.score), 0).label('valid_cmte_scores'),
        )
        .join(License, CMTEEventParticipationRecord.license_number == License.number)
        .filter(
            CMTEEventParticipationRecord.approved_date.isnot(None),
            CMTEEventParticipationRecord.score_valid_until == License.end_date,
        )
        .group_by(CMTEEventParticipationRecord.license_number)
        .subquery()
    )

    active_license_age_counts = {
        '20-30': 0,
        '30-40': 0,
        '40-50': 0,
        '50-60': 0,
        'over60': 0,
    }
    active_license_rows = (
        db.session.query(
            License.end_date.label('end_date'),
            Member.dob.label('dob'),
            func.coalesce(valid_cmte_scores_subquery.c.valid_cmte_scores, 0).label('valid_cmte_scores'),
        )
        .join(Member)
        .outerjoin(valid_cmte_scores_subquery, valid_cmte_scores_subquery.c.license_number == License.number)
        .filter(
            License.end_date >= today,
            active_license_status_filter,
            Member.dob.isnot(None),
        )
        .all()
    )
    for row in active_license_rows:
        age = _calculate_age(row.dob)
        if 20 <= age < 30:
            active_license_age_counts['20-30'] += 1
        elif 30 <= age < 40:
            active_license_age_counts['30-40'] += 1
        elif 40 <= age < 50:
            active_license_age_counts['40-50'] += 1
        elif 50 <= age < 60:
            active_license_age_counts['50-60'] += 1
        elif age >= 60:
            active_license_age_counts['over60'] += 1

    active_license_age_rows = [
        ['20-30', active_license_age_counts['20-30']],
        ['30-40', active_license_age_counts['30-40']],
        ['40-50', active_license_age_counts['40-50']],
        ['50-60', active_license_age_counts['50-60']],
        ['over60', active_license_age_counts['over60']],
    ]

    active_license_days_counts = {
        '0-0.5y': 0,
        '0.5-1y': 0,
        '1-2y': 0,
        '2-3y': 0,
        '3-4y': 0,
    }
    active_license_eligibility_counts = {
        '0-0.5y': {'eligible': 0, 'not_eligible': 0},
        '0.5-1y': {'eligible': 0, 'not_eligible': 0},
        '1-2y': {'eligible': 0, 'not_eligible': 0},
        '2-3y': {'eligible': 0, 'not_eligible': 0},
        '3-4y': {'eligible': 0, 'not_eligible': 0},
    }
    for row in active_license_rows:
        remaining_days = (row.end_date - today).days
        if remaining_days <= 183:
            remaining_bucket = '0-0.5y'
        elif remaining_days <= 365:
            remaining_bucket = '0.5-1y'
        elif remaining_days <= 730:
            remaining_bucket = '1-2y'
        elif remaining_days <= 1095:
            remaining_bucket = '2-3y'
        else:
            remaining_bucket = '3-4y'

        if remaining_days <= 183:
            active_license_days_counts['0-0.5y'] += 1
        elif remaining_days <= 365:
            active_license_days_counts['0.5-1y'] += 1
        elif remaining_days <= 730:
            active_license_days_counts['1-2y'] += 1
        elif remaining_days <= 1095:
            active_license_days_counts['2-3y'] += 1
        else:
            active_license_days_counts['3-4y'] += 1

        if row.valid_cmte_scores >= 50:
            active_license_eligibility_counts[remaining_bucket]['eligible'] += 1
        else:
            active_license_eligibility_counts[remaining_bucket]['not_eligible'] += 1

    active_license_days_rows = [
        ['0-0.5y', active_license_days_counts['0-0.5y']],
        ['0.5-1y', active_license_days_counts['0.5-1y']],
        ['1-2y', active_license_days_counts['1-2y']],
        ['2-3y', active_license_days_counts['2-3y']],
        ['3-4y', active_license_days_counts['3-4y']],
    ]

    active_license_eligibility_rows = [
        [
            '0-0.5y',
            active_license_eligibility_counts['0-0.5y']['eligible'],
            active_license_eligibility_counts['0-0.5y']['not_eligible'],
        ],
        [
            '0.5-1y',
            active_license_eligibility_counts['0.5-1y']['eligible'],
            active_license_eligibility_counts['0.5-1y']['not_eligible'],
        ],
        [
            '1-2y',
            active_license_eligibility_counts['1-2y']['eligible'],
            active_license_eligibility_counts['1-2y']['not_eligible'],
        ],
        [
            '2-3y',
            active_license_eligibility_counts['2-3y']['eligible'],
            active_license_eligibility_counts['2-3y']['not_eligible'],
        ],
        [
            '3-4y',
            active_license_eligibility_counts['3-4y']['eligible'],
            active_license_eligibility_counts['3-4y']['not_eligible'],
        ],
    ]

    return {
        'total_members': total_members,
        'active_members': active_members,
        'active_member_age_rows': active_member_age_rows,
        'member_status_rows': member_status_rows,
        'total_licenses': total_licenses,
        'active_licenses': active_licenses,
        'expired_licenses': expired_licenses,
        'first_licenses_issued_by_year_rows': first_licenses_issued_by_year_rows,
        'active_license_age_rows': active_license_age_rows,
        'active_license_days_rows': active_license_days_rows,
        'active_license_eligibility_rows': active_license_eligibility_rows,
    }


@webadmin.route('/member-dashboard/data', methods=['GET'])
@login_required
@admin_permission.require(http_exception=403)
def member_dashboard_data():
    return jsonify(_build_member_dashboard_payload())


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
        flash('อัปเดตข้อมูลการต่ออายุใบอนุญาตเรียบร้อยแล้ว', 'success')
        return redirect(url_for('webadmin.upload_renew'))
    return render_template('webadmin/upload_renew.html')


@webadmin.route('/upload/new', methods=['GET', 'POST'])
@login_required
@admin_permission.require(http_exception=403)
def upload_new():
    if request.method == 'POST':
        f = request.files['file']
        df = pd.read_excel(
            f,
            engine='openpyxl',
            dtype={
                'idcardnumber': str,
                'mem_id_txt': str,
                'license_no': str,
                'telephone_number': str,
            },
        )
        skipped_rows = []
        for idx, row in df.iterrows():
            dob = _parse_excel_date(_get_first_row_value(row, 'dob', 'birthday', 'date_of_birth', 'birth_date'))
            has_traditional_fee = _get_row_value(row, 'form_tradition') == 1
            payment_date = _get_row_value(row, 'payment_date')
            license_start_date = _parse_excel_date(_get_row_value(row, 'license_begin_date'))
            license_end_date = _parse_excel_date(_get_row_value(row, 'license_exp_date'))
            license_issue_date = _parse_excel_date(_get_row_value(row, 'approve_date'))
            member_pid = _normalize_excel_identifier(_get_row_value(row, 'idcardnumber'))
            license_number = _normalize_excel_identifier(_get_row_value(row, 'license_no'))
            member = Member.query.filter_by(pid=member_pid).first() if member_pid else None
            if not member:
                required_member_values = {
                    'idcardnumber': member_pid,
                    'mem_id_txt': _normalize_excel_identifier(_get_row_value(row, 'mem_id_txt')),
                    'firstnameTH': _get_row_value(row, 'firstnameTH'),
                    'lastnameTH': _get_row_value(row, 'lastnameTH'),
                }
                missing_member_values = [
                    column for column, value in required_member_values.items()
                    if value is None
                ]
                if missing_member_values:
                    skipped_rows.append(
                        f'row {idx + 2}: new member missing {", ".join(missing_member_values)}'
                    )
                    continue
                member = Member(
                    pid=member_pid,
                    th_title=_get_row_value(row, 'prefix'),
                    th_firstname=_get_row_value(row, 'firstnameTH'),
                    th_lastname=_get_row_value(row, 'lastnameTH'),
                    en_firstname=_get_row_value(row, 'firstnameEN'),
                    en_lastname=_get_row_value(row, 'lastnameEN'),
                    number=_normalize_excel_identifier(_get_row_value(row, 'mem_id_txt')),
                    email=_get_row_value(row, 'email'),
                    tel=_get_row_value(row, 'telephone_number'),
                    dob=dob,
                    first_license_issue_date=license_issue_date,
                )
                db.session.add(member)
                license = License.query.filter_by(number=license_number).first() if license_number else None
                if not license and all((license_issue_date, license_start_date, license_end_date)):
                    license = License(
                        start_date=license_start_date,
                        end_date=license_end_date,
                        issue_date=license_issue_date,
                        number=license_number,
                        member=member,
                    )
                if license:
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
                license = License.query.filter_by(number=license_number).first() if license_number else None
                if license:
                    if license_start_date is not None:
                        license.start_date = license_start_date
                    if license_end_date is not None:
                        license.end_date = license_end_date
                    if license_issue_date is not None:
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
        if skipped_rows:
            return 'Upload completed. Skipped: {}'.format('; '.join(skipped_rows))
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
