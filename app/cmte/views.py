import io
import re
import time
import os
import uuid
from datetime import timedelta, datetime
from functools import wraps
from io import BytesIO
import pandas as pd

import arrow
import boto3
from flask import render_template, flash, redirect, url_for, make_response, request, send_file, current_app, session, \
    jsonify, abort
from flask_login import login_required, login_user, current_user
from flask_principal import identity_changed, Identity
from flask_wtf.csrf import generate_csrf
from numpy.core import records
from pytz import timezone
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app import db, sponsor_event_management_permission
from app.cmte import cmte_bp as cmte
from app.cmte.forms import *
from app.members.models import License, Member
from app.cmte.models import *
from app import cmte_admin_permission, cmte_sponsor_admin_permission

bangkok = timezone('Asia/Bangkok')


def active_sponsor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.sponsor.expire_date:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


@cmte.route('/aws-s3/download/<key>', methods=['GET'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def download_file(key):
    download_filename = request.args.get('download_filename')
    s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                             aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                             region_name=os.environ.get('BUCKETEER_AWS_REGION'))
    outfile = BytesIO()
    s3_client.download_fileobj(os.environ.get('BUCKETEER_BUCKET_NAME'), key, outfile)
    outfile.seek(0)
    return send_file(outfile, download_name=download_filename, as_attachment=True)


@cmte.get('/')
@login_required
@cmte_sponsor_admin_permission.require()
def cmte_index():
    warning_msg = ''
    if cmte_admin_permission:
        return render_template('cmte/index.html', warning_msg=warning_msg)
    if current_user.sponsor:
        is_request = CMTESponsorRequest.query.filter_by(sponsor=current_user.sponsor, paid_at=None).first()
        if current_user.sponsor.expire_status() == 'inactive':
            if is_request:
                warning_msg = 'กรุณาดำเนินการชำระค่าธรรมเนียม ขออภัยหากท่านชำระแล้ว' if is_request.approved_at else ''
        elif current_user.sponsor.expire_status() == 'expired' or current_user.sponsor.expire_status() == 'nearly_expire':
            if is_request:
                if is_request.approved_at:
                    warning_msg = 'กรุณาดำเนินการชำระค่าธรรมเนียม'
            else:
                warning_msg = 'กรุณาดำเนินการต่ออายุใบรับรองสถาบัน'
    return render_template('cmte/index.html', warning_msg=warning_msg)


@cmte.get('/events/registration')
@active_sponsor_required
@login_required
@cmte_sponsor_admin_permission.require()
def register_event():
    if not sponsor_event_management_permission.can():
        return render_template('errors/sponsor_expired.html')
    form = CMTEEventForm()
    return render_template('cmte/event_registration.html', form=form)


@cmte.get('/events/<int:event_id>/edit')
@login_required
@cmte_sponsor_admin_permission.require()
def edit_event(event_id):
    event = CMTEEvent.query.get(event_id)
    form = CMTEEventForm(obj=event)
    return render_template('cmte/event_registration.html', form=form, event=event)


@cmte.post('/events/registration')
@cmte.post('/events/<int:event_id>/edit')
@login_required
@cmte_sponsor_admin_permission.require()
def create_event(event_id=None):
    form = CMTEEventForm()
    if event_id:
        event = CMTEEvent.query.get(event_id)
    if form.validate_on_submit():
        if not event_id:
            event = CMTEEvent()
        form.populate_obj(event)
        event.start_date = arrow.get(event.start_date, 'Asia/Bangkok').datetime
        event.end_date = arrow.get(event.end_date, 'Asia/Bangkok').datetime
        event.sponsor = current_user.sponsor
        event.submission_due_date = event.end_date + timedelta(days=30)
        s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                 aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                 region_name=os.environ.get('BUCKETEER_AWS_REGION'))
        for doc_form in form.upload_files:
            _file = doc_form.upload_file.data
            if _file:
                filename = _file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTEEventDoc(event=event, key=key, filename=filename)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = doc_form.note.data
                db.session.add(doc)
        db.session.add(event)
        db.session.commit()
        flash('กรุณาตรวจสอบข้อมูลก่อนทำการยื่นขออนุมัติ', 'success')
        return redirect(url_for('cmte.preview_event', event_id=event.id))
    flash('กรุณาตรวจสอบความถูกต้องของข้อมูล', 'warning')
    return render_template('cmte/event_registration.html', form=form, event=event)


@cmte.delete('/events/docs/<int:doc_id>')
@login_required
@cmte_sponsor_admin_permission.require()
def remove_doc(doc_id):
    doc = CMTEEventDoc.query.get(doc_id)
    db.session.delete(doc)
    db.session.commit()
    return ''


@cmte.route('/events/<int:event_id>/venue', methods=['GET', 'POST'])
@active_sponsor_required
@login_required
@cmte_sponsor_admin_permission.require()
def sponsor_edit_venue(event_id):
    event = CMTEEvent.query.get(event_id)

    class WebsiteForm(ModelForm):
        class Meta:
            model = CMTEEvent
            only = ['venue']

    form = WebsiteForm(obj=event)

    if request.method == 'GET':
        return f'''
        <form hx-swap="innerHTML" hx-target="#venue"
            hx-post="{url_for('cmte.sponsor_edit_venue', event_id=event.id)}">
        {form.hidden_tag()}
        <div class="field">
            <div class="control">
            {form.venue(class_="textarea")}
            </div>
        </div>
        <div class="field">
            <div class="control">
                <button class="button is-success" type=submit>บันทึก</button>
            </div>
        </div>
        </form>
        '''
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(event)
            db.session.add(event)
            db.session.commit()
            return event.venue
        else:
            return form.errors


@cmte.route('/events/<int:event_id>/website', methods=['GET', 'POST'])
@active_sponsor_required
@login_required
@cmte_sponsor_admin_permission.require()
def sponsor_edit_website(event_id):
    event = CMTEEvent.query.get(event_id)

    class WebsiteForm(ModelForm):
        class Meta:
            model = CMTEEvent
            only = ['website']

    form = WebsiteForm(obj=event)

    if request.method == 'GET':
        return f'''
        <form hx-swap="innerHTML" hx-target="#website"
            hx-post="{url_for('cmte.sponsor_edit_website', event_id=event.id)}">
        {form.hidden_tag()}
        <div class="field">
            <div class="control">
            {form.website(class_="textarea")}
            </div>
        </div>
        <div class="field">
            <div class="control">
                <button class="button is-success" type=submit>บันทึก</button>
            </div>
        </div>
        </form>
        '''
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(event)
            db.session.add(event)
            db.session.commit()
            return event.website
        else:
            return form.errors


@cmte.post('/event_activites')
@login_required
def get_event_activities():
    event_type_id = request.form.get('event_type', type=int)
    event_id = request.args.get('event_id', type=int)
    if event_id:
        event = CMTEEvent.query.get(event_id)
        activity_id = event.activity_id
    else:
        activity_id = None
    event_type = CMTEEventType.query.get(event_type_id)
    url_ = url_for('cmte.get_fee_rates', event_id=event_id)
    options = f'''<select id="activity-select" name="activity" hx-headers='{{"X-CSRF-Token": "{generate_csrf()}"}}' hx-post="{url_}" hx-trigger="change, load" hx-swap="innerHTML" hx-target="#feeRateSelectField">'''
    for a in event_type.activities:
        selected = 'selected' if activity_id == a.id else ''
        options += f'<option {selected} value="{a.id}">{a.name}</li>'
    options += '</select>'
    return options


@cmte.post('/fee-rates')
@login_required
def get_fee_rates():
    event_id = request.args.get('event_id')
    if event_id:
        event = CMTEEvent.query.get(event_id)
        fee_rate_id = event.fee_rate_id
    else:
        fee_rate_id = None
    activity_id = request.form.get('activity', type=int)
    activity = CMTEEventActivity.query.get(activity_id)
    options = ''
    for rate in activity.fee_rates:
        checked = 'checked' if rate.id == fee_rate_id else ''
        options += f'<label class="radio is-danger"><input type="radio" required {checked} name="fee_rate" value="{rate.id}"/>{rate}</label><br>'
    if activity.fee_rates:
        options += '<p class="help is-danger">โปรดเลือกค่าธรรมเนียมการขออนุมัติคะแนนที่เหมาะสม</p>'
    else:
        options += '<p class="help is-info">ไม่มีค่าธรรมเนียมการขออนุมัติคะแนน</p>'

    return options


@cmte.get('/events/<int:event_id>/preview')
@login_required
@cmte_sponsor_admin_permission.require()
def preview_event(event_id):
    form = CMTEParticipantFileUploadForm()
    event = CMTEEvent.query.get(event_id)
    next_url = request.args.get('next_url')
    return render_template('cmte/event_preview.html', event=event, next_url=next_url, form=form)


@cmte.post('/events/<int:event_id>/participants/upload')
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def add_participants(event_id):
    errors = []
    form = CMTEParticipantFileUploadForm()
    event = CMTEEvent.query.get(event_id)
    _file = form.upload_file.data
    if _file:
        df = pd.read_excel(_file, sheet_name='Sheet1')
        for idx, row in df.iterrows():
            license_number = str(row['license_number'])
            score = float(row['score'])
            license = License.query.filter_by(number=license_number).first()
            if not license:
                errors.append({
                    'name': row['name'],
                    'license_number': row['license_number'],
                    'score': row['score'],
                    'note': 'License not found.'
                })
                continue

            rec = CMTEEventParticipationRecord.query.filter_by(
                license_number=license_number,
                event_id=event_id).first()
            if not rec:
                rec = CMTEEventParticipationRecord()
                rec.license_number = license_number
                rec.event_id = event_id
            rec.create_datetime = arrow.now('Asia/Bangkok').datetime
            rec.score = event.cmte_points if score > event.cmte_points else score
            rec.submitted_name = row['name']
            db.session.add(rec)
            db.session.commit()
        flash('เพิ่มรายชื่อผู้เข้าร่วมแล้ว', 'success')
    else:
        flash('ไม่พบ file ข้อมูล', 'danger')
    if errors:
        df_ = pd.DataFrame(errors)
        return render_template('cmte/admin/upload_errors.html', errors=df_.to_html(classes=['table is-striped']),
                               event=event)
    if request.args.get('source') == 'admin':
        return redirect(url_for('cmte.admin_preview_event', event_id=event_id))
    return redirect(url_for('cmte.preview_event', event_id=event_id))


@cmte.get('/api/event/<int:event_id>/participants')
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def get_event_participants(event_id):
    search = request.args.get('search[value]')
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    query = CMTEEventParticipationRecord.query.filter_by(event_id=event_id)
    col_idx = request.args.get('order[0][column]')
    direction = request.args.get('order[0][dir]')
    col_name = request.args.get('columns[{}][data]'.format(col_idx))
    if col_name:
        try:
            column = getattr(CMTEEventParticipationRecord, col_name)
        except AttributeError:
            print(f'{col_name} not found.')
        else:
            if direction == 'desc':
                column = column.desc()
            query = query.order_by(column)

    if search:
        query = (query.join(License).join(Member, aliased=True)
                 .filter(or_(Member.th_firstname.contains(search),
                             Member.th_lastname.contains(search),
                             Member.en_firstname.contains(search),
                             Member.en_lastname.contains(search),
                             License.number.contains(search))))
    total_filtered = query.count()
    query = query.order_by(CMTEEventParticipationRecord.license_number).offset(start).limit(length)

    data = []
    for record in query:
        _data = record.to_dict()
        _data['action'] = render_template('cmte/partials/event_record_edit_template.html', record=record)
        data.append(_data)
    print(data)
    return jsonify(data=data,
                   recordsFiltered=total_filtered,
                   recordsTotal=query.count(),
                   draw=request.args.get('draw', type=int))


@cmte.get('/events/participants/template-file')
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def get_participants_template_file():
    df = pd.DataFrame({'name': [], 'license_number': [], 'score': []})
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name=f'cmte_point_template.xlsx')


@cmte.route('/admin/events/<int:event_id>/preview', methods=('GET', 'POST'))
@login_required
@cmte_admin_permission.require()
def admin_preview_event(event_id):
    event = CMTEEvent.query.get(event_id)
    next_url = request.args.get('next_url')
    form = CMTEEventCodeForm()
    participant_form = CMTEParticipantFileUploadForm()
    return render_template('cmte/admin/event_preview.html',
                           event=event,
                           next_url=next_url,
                           form=form,
                           participant_form=participant_form)


@cmte.route('/admin/events/<int:event_id>/request_info', methods=('GET', 'POST'))
@login_required
@cmte_admin_permission.require()
def admin_request_info(event_id):
    event = CMTEEvent.query.get(event_id)
    if request.method == 'POST':
        message = request.form.get('request_info_message')
        if message:
            event.info_request = message
            event.is_pending = True
            db.session.add(event)
            db.session.commit()
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp

    csrf_token = f'{{"X-CSRF-Token": "{generate_csrf()}" }}'
    template = f'''
    <form>
    <div class="field">
        <div class="control">
            <textarea class="textarea" name="request_info_message">{event.info_request or ""}</textarea>
        </div>
    </div>
    <div class="field">
        <div class="control">
            <button class="button is-success"
                hx-post="{url_for('cmte.admin_request_info', event_id=event_id)}"
                hx-headers='{csrf_token}'
                hx-target="#request-message"
                hx-swap="innerHTML"
                hx-indicator="this"
            >
                <span>Send Request</span>
            </button>
        </div>
    </div>
    </form>
    '''
    return template


@cmte.route('/api/events/<int:event_id>/participants', methods=('GET', 'POST'))
@login_required
@cmte_admin_permission.require()
def admin_preview_event_participants(event_id):
    query = CMTEEventParticipationRecord.query.filter_by(event_id=event_id)
    records_total = query.count()
    search = request.args.get('search[value]')
    col_idx = request.args.get('order[0][column]')
    direction = request.args.get('order[0][dir]')
    col_name = request.args.get('columns[{}][data]'.format(col_idx))
    if col_name:
        try:
            column = getattr(CMTEEventParticipationRecord, col_name)
        except AttributeError:
            print(f'{col_name} not found.')
        else:
            if direction == 'desc':
                column = column.desc()
            query = query.order_by(column)

    if search:
        query = (query.join(License).join(Member, aliased=True)
                 .filter(or_(Member.th_firstname.contains(search),
                             Member.th_lastname.contains(search),
                             Member.en_firstname.contains(search),
                             Member.en_lastname.contains(search),
                             License.number.contains(search))))
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    total_filtered = query.count()
    query = query.offset(start).limit(length)
    participants = []
    for record in query:
        rec_dict = record.to_dict()
        rec_dict['actions'] = render_template('cmte/partials/event_record_edit_template.html', record=record)
        participants.append(rec_dict)
    return jsonify({'data': participants,
                    'recordsFiltered': total_filtered,
                    'recordsTotal': records_total,
                    'draw': request.args.get('draw', type=int)})


@cmte.route('/admin/events/<int:event_id>/code', methods=('GET', 'POST'))
@login_required
@cmte_admin_permission.require()
def admin_edit_event_code(event_id):
    event = CMTEEvent.query.get(event_id)
    form = CMTEEventCodeForm()
    if request.method == 'GET':
        template = f'''
            <form hx-confirm="คุณต้องการใช้รหัสนี้สำหรับกิจกรรมหรือไม่"
                  hx-headers='{{"X-CSRF-Token": "{generate_csrf()}" }}'
                  hx-indicator="#submit-btn"
                  hx-post="{url_for('cmte.admin_edit_event_code', event_id=event.id)}"
                  hx-target="#event-code"
                  hx-swap="innerHTML"
            >
                <div class="field has-addons">
                    <div class="control">
                        <div class="select">
                            {form.code()}
                        </div>
                        <p class="help is-danger">เมื่อบันทึกรหัสจะอัพเดตอัตโนมัติ</p>
                    </div>
                    <div class="control">
                        <button type="submit" id="submit-btn" class="button is-success">
                            <span class="icon">
                                <i class="fa-solid fa-floppy-disk"></i>
                            </span>
                            <span>บันทึก</span>
                        </button>
                    </div>
                </div>
            </form>
        '''
        return template
    elif request.method == 'POST':
        if form.validate_on_submit():
            event_code = form.code.data
            event.event_code = str(event_code)
            event_code.increment()
            db.session.add(event_code)
            db.session.commit()
        else:
            return str(form.errors)
    template = f'''
    {str(event.event_code)}
    <a class="button is-light" hx-swap-oob="true" hx-target="#event-code-form" hx-swap="innerHTML" hx-get="{url_for('cmte.admin_edit_event_code', event_id)}">
        <span class="icon"><i class="fa-solid fa-pencil"></i></span>
        <span>แก้ไข</span>
    </a>
    '''
    return template


@cmte.route('/admin/event-types', methods=('GET', 'POST'))
@login_required
@cmte_admin_permission.require()
def admin_edit_event_types():
    event_types = CMTEEventType.query
    return render_template('cmte/admin/event_types.html', event_types=event_types)


@cmte.post('/events/<int:event_id>/submission')
@login_required
@cmte_sponsor_admin_permission.require()
def submit_event(event_id):
    event = CMTEEvent.query.get(event_id)
    if not event.submitted_datetime:
        event.submitted_datetime = arrow.now('Asia/Bangkok').datetime
        db.session.add(event)
        db.session.commit()
        flash('ยื่นขออนุมัติเรียบร้อยแล้ว', 'success')
    elif event.is_pending:
        event.is_pending = False
        db.session.add(event)
        db.session.commit()
        flash('ยื่นขออนุมัติเรียบร้อยแล้ว', 'success')
    else:
        flash('รายการนี้ได้ยื่นขออนุมัติแล้ว', 'warning')
    resp = make_response()
    resp.headers['HX-Refresh'] = 'true'
    # resp.headers['HX-Redirect'] = request.args.get('next') or url_for('cmte.cmte_index')
    return resp


@cmte.route('/events/<int:event_id>/payment', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def process_payment(event_id):
    pay_amount = request.args.get('pay_amount', None)
    form = CMTEPaymentForm()
    event = CMTEEvent.query.get(event_id)
    if request.method == 'POST':
        if form.validate_on_submit():
            doc = CMTEEventDoc.query.filter_by(event_id=event_id, is_payment_slip=True).first()
            if doc:
                db.session.delete(doc)
                db.session.commit()
            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            _file = form.upload_file.upload_file.data
            if _file:  # a file is required
                filename = _file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTEEventDoc(event=event, key=key, filename=filename)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = form.upload_file.note.data
                doc.is_payment_slip = True
                db.session.add(doc)
                event.payment_datetime = arrow.now('Asia/Bangkok').datetime
                db.session.add(event)
                db.session.commit()
                flash('ชำระค่าธรรมเนียมเรียบร้อยแล้ว', 'success')
                return redirect(url_for('cmte.preview_event', event_id=event_id))
            else:
                flash('กรุณาแนบสลิปหลักฐานการโอนเงิน', 'danger')
    return render_template('cmte/event_payment_form.html', event=event, form=form, pay_amount=pay_amount)


@cmte.route('/events/<int:event_id>/participants', methods=['GET', 'POST'])
@cmte.route('/events/<int:event_id>/participants/<int:rec_id>', methods=['GET', 'DELETE', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def edit_participants(event_id: int = None, rec_id: int = None):
    event = CMTEEvent.query.get(event_id)
    if cmte_admin_permission.can():
        form = AdminParticipantForm(data={'approved_date': arrow.now('Asia/Bangkok').date()})
        is_admin = True
    else:
        form = ParticipantForm()
        is_admin = False

    resp = make_response()
    if request.method == 'GET':
        license = None
        if rec_id:
            rec = CMTEEventParticipationRecord.query.get(rec_id)
            if rec:
                if rec.approved_date:
                    form.approved_date.data = rec.approved_date
                form.license_number.data = rec.license_number
                form.score.data = rec.score
                license = rec.license
        return render_template('cmte/modals/participant_form.html',
                               is_admin=is_admin,
                               form=form,
                               event_id=event_id,
                               license=license,
                               rec_id=rec_id)

    if request.method == 'DELETE':
        rec = CMTEEventParticipationRecord.query.get(rec_id)
        db.session.delete(rec)
        db.session.commit()
        resp.headers['HX-Trigger-After-Swap'] = 'reloadAjax'
        return resp
    if form.validate_on_submit():
        if rec_id:
            rec = CMTEEventParticipationRecord.query.get(rec_id)
            if not rec or form.score.data > event.cmte_points:
                resp.headers['HX-Trigger'] = 'closeModal, alertError'
            else:
                rec.score = form.score.data
                rec.create_datetime = arrow.now('Asia/Bangkok').datetime
                if cmte_admin_permission.can() and form.approved_date.data:
                    rec.approved_date = form.approved_date.data
                    rec.set_score_valid_date()

                if not cmte_admin_permission.can():
                    event.participant_updated_at = rec.create_datetime

                db.session.add(event)
                db.session.add(rec)
                db.session.commit()

        else:
            rec = CMTEEventParticipationRecord.query.filter_by(license_number=form.license_number.data,
                                                               event_id=event_id).first()
            if rec or form.score.data > event.cmte_points:
                resp.headers['HX-Trigger'] = 'alertError'
                return resp
            else:
                rec = CMTEEventParticipationRecord(event_id=event_id, license_number=form.license_number.data,
                                                   score=form.score.data)
                rec.create_datetime = arrow.now('Asia/Bangkok').datetime
                db.session.add(rec)
                db.session.commit()
                if cmte_admin_permission.can() and form.approved_date.data:
                    rec.approved_date = form.approved_date.data
                    rec.set_score_valid_date()

                if not cmte_admin_permission.can():
                    event.participant_updated_at = rec.create_datetime
                db.session.add(event)
                db.session.add(rec)
                db.session.commit()
        resp.headers['HX-Trigger-After-Swap'] = 'reloadAjax, closeModal'
        return resp
    else:
        resp.headers['HX-Trigger'] = 'alertError'
        return resp


@cmte.route('/events/<int:event_id>/participants/approve', methods=['POST', 'DELETE'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def approve_event_participation_records(event_id):
    event = CMTEEvent.query.get(event_id)
    if request.method == 'POST':
        for rec in event.participants:
            rec.approved_date = arrow.now('Asia/Bangkok').datetime.date()
            rec.score_valid_until = rec.license.end_date
            rec.set_score_valid_date()
            db.session.add(rec)
        db.session.commit()
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp
    if request.method == 'DELETE':
        for rec in event.participants:
            rec.approved_date = None
            db.session.add(rec)
        db.session.commit()
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp


@cmte.get('/admin/events/pending')
@login_required
@cmte_admin_permission.require()
def admin_pending_events():
    return render_template('cmte/admin/approved_events.html', _type='pending')


@cmte.get('/admin/events/approved')
@login_required
@cmte_admin_permission.require()
def admin_approved_events():
    return render_template('cmte/admin/approved_events.html', _type='approved')


@cmte.get('/api/events')
def get_events():
    orderable_columns = {
        1: CMTEEvent.start_date,
        2: CMTEEvent.end_date,
        4: CMTEEvent.submitted_datetime,
        5: CMTEEvent.payment_datetime,
        6: CMTEEvent.payment_approved_at,
        7: CMTEEvent.approved_datetime,
        8: CMTEEvent.participant_updated_at,
        9: CMTEEvent.num_pending_participants,
    }
    search = request.args.get('search[value]')
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    _type = request.args.get('_type', 'pending')
    new_only = request.args.get('new_only', 'false')
    query = CMTEEvent.query.filter(db.or_(CMTEEvent.title.like(f'%{search}%')))
    if _type == 'approved':
        query = query.filter(CMTEEvent.approved_datetime != None)
    elif _type == 'pending':
        query = query.filter(CMTEEvent.approved_datetime == None,
                             CMTEEvent.submitted_datetime != None)
    if new_only == 'true':
        query = query.filter(CMTEEvent.start_date >= datetime.today())
    total_filtered = query.count()
    r_dir = re.compile('order\[\d\]\[dir\]')
    r_column = re.compile('order\[(\d)\]\[column\]')
    order_dir = ''.join((filter(r_dir.match, request.args.keys())))
    order_column = ''.join((filter(r_column.match, request.args.keys())))
    if order_column and order_dir:
        dir_ = request.args.get(order_dir)
        col_idx = request.args.get(order_column)
        if int(col_idx) in orderable_columns:
            if dir_ == 'desc':
                query = query.order_by(orderable_columns[int(col_idx)].desc())
            else:
                query = query.order_by(orderable_columns[int(col_idx)])

    query = query.order_by(CMTEEvent.submitted_datetime).offset(start).limit(length)
    data = []
    for event in query:
        _data = event.to_dict()
        _data['link'] = url_for('cmte.admin_preview_event', event_id=event.id)
        data.append(_data)
    return jsonify(data=data,
                   recordsFiltered=total_filtered,
                   recordsTotal=query.count(),
                   draw=request.args.get('draw', type=int))


@cmte.get('/admin/api/events')
@login_required
@cmte_sponsor_admin_permission.require()
def load_pending_events():
    type_ = request.args.get('type_')
    query = CMTEEvent.query.filter_by(sponsor_id=current_user.sponsor_id)
    records_total = query.count()
    if type_ == 'drafting':
        query = query.filter_by(submitted_datetime=None, approved_datetime=None)
    elif type_ == 'pending':
        query = query.filter(CMTEEvent.submitted_datetime != None,
                                       CMTEEvent.approved_datetime == None)
    else:
        query = query.filter(CMTEEvent.approved_datetime != None,
                             CMTEEvent.submitted_datetime != None)
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    total_filtered = query.count()
    query = query.offset(start).limit(length)
    data = []
    for event in query:
        event_dict = event.to_dict()
        event_dict['link'] = url_for('cmte.preview_event', event_id=event.id)
        data.append(event_dict)
    return jsonify({'data': data,
                    'recordsFiltered': total_filtered,
                    'recordsTotal': records_total,
                    'draw': request.args.get('draw', type=int)})


@cmte.post('/admin/events/<int:event_id>/approve')
@login_required
@cmte_admin_permission.require()
def approve_event(event_id):
    event = CMTEEvent.query.get(event_id)
    event.approved_datetime = arrow.now('Asia/Bangkok').datetime
    event.submission_due_date = event.approved_datetime + timedelta(days=event.event_type.submission_due)
    cmte_points = request.form.get('cmte_points', type=float)
    event.cmte_points = cmte_points
    event.is_pending = False
    db.session.add(event)
    db.session.commit()
    flash('อนุมัติกิจกรรมเรียบร้อย', 'success')
    resp = make_response()
    resp.headers['HX-Refresh'] = "true"
    return resp


@cmte.delete('/admin/events/<int:event_id>/unapprove')
@login_required
@cmte_admin_permission.require()
def unapprove_event(event_id):
    event = CMTEEvent.query.get(event_id)
    event.approved_datetime = None
    event.submission_due_date = None
    event.is_pending = False
    event.is_approved = None
    event.cmte_points = None
    db.session.add(event)
    db.session.commit()
    resp = make_response()
    resp.headers['HX-Refresh'] = 'true'
    return resp


@cmte.post('/admin/events/<int:event_id>/edit-cmte-points')
@login_required
@cmte_admin_permission.require()
def edit_cmte_points(event_id):
    event = CMTEEvent.query.get(event_id)
    cmte_points = request.form.get('cmte_points', type=float)
    event.cmte_points = cmte_points
    db.session.add(event)
    db.session.commit()
    template = f'''<h1 class="title is-size-3">{event.cmte_points} คะแนน</h1>'''
    return template


@cmte.get('/admin/events/<int:event_id>/edit-cmte-points')
@login_required
@cmte_admin_permission.require()
def get_cmte_point_input(event_id):
    event = CMTEEvent.query.get(event_id)
    template = f'''
    <form method="post" hx-post="{url_for('cmte.edit_cmte_points', event_id=event_id)}"
        hx-headers='{{ "X-CSRF-Token": "{generate_csrf()}" }}'
        hx-target="#cmtePointInput"
        hx-swap="innerHTML"
        hx-indicator="#submit-btn"
    >
        <div class="field has-addons">
            <div class="control">
                <input type="number" value={event.cmte_points} step="0.1" name="cmte_points" required class="input" />
            </div>
            <div class="control">
                <button type="submit" id="submit-btn" class="button is-primary">Save</button>
            </div>
        </div>
    </form>
    '''
    return template


@cmte.get('/events/drafts')
@active_sponsor_required
@login_required
@cmte_sponsor_admin_permission.require()
def show_draft_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter_by(submitted_datetime=None, sponsor=current_user.sponsor)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.load_pending_events', page_no=events.next_num) if events.has_next else None
    return render_template('cmte/draft_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/events/submitted')
@login_required
@cmte_sponsor_admin_permission.require()
def show_submitted_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.submitted_datetime != None)\
        .filter(CMTEEvent.approved_datetime == None)\
        .filter_by(sponsor=current_user.sponsor)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/submitted_events.html', events=events.items, next_url=next_url)


@cmte.get('/events/approved')
@login_required
@cmte_sponsor_admin_permission.require()
def show_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None)\
        .filter_by(sponsor=current_user.sponsor).order_by(CMTEEvent.start_date)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.load_pending_events', page_no=events.next_num) if events.has_next else None
    return render_template('cmte/approved_events.html', events=events.items, next_url=next_url)


@cmte.delete('/admin/events/<int:event_id>/cancel')
@login_required
@cmte_sponsor_admin_permission.require()
def cancel_event(event_id):
    time.sleep(3)
    event = CMTEEvent.query.get(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('อนุมัติกิจกรรมเรียบร้อย', 'success')
    resp = make_response()
    resp.headers['HX-Redirect'] = request.args.get('next') or url_for('cmte.show_draft_events')
    return resp


@cmte.get('/search-license')
@login_required
def search_license():
    license_number = request.args.get('license_number')
    event_id = request.args.get('event_id')
    today = arrow.now('Asia/Bangkok').date()
    license = License.query.filter_by(number=license_number) \
        .filter(License.end_date >= today).first()
    if cmte_admin_permission.can():
        form = AdminParticipantForm(data={'license_number': license_number, 'approved_date': arrow.now('Asia/Bangkok').date()})
        is_admin = True
    else:
        form = ParticipantForm(data={'license_number': license_number})
        is_admin = False
    if license:
        return render_template('cmte/modals/participant_form.html',
                               is_admin=is_admin,
                               license=license,
                               event_id=event_id,
                               form=form,
                               rec_id=None)
    else:
        return render_template('cmte/modals/participant_form.html',
                               is_admin=is_admin,
                               not_found=True,
                               event_id=event_id,
                               form=form,
                               rec_id=None)


@cmte.route('/admin/fee-payment-record-form', methods=['GET', 'POST'])
@cmte.route('/admin/fee-payment-record-form/<int:record_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_edit_fee_payment_record(record_id=None):
    if record_id:
        record = CMTEFeePaymentRecord.query.get(record_id)
        form = CMTEFeePaymentForm(obj=record)
    else:
        record = None
        form = CMTEFeePaymentForm()
    today = datetime.today()
    active_payments = CMTEFeePaymentRecord.query.filter(CMTEFeePaymentRecord.end_date >= today).all()
    pending_payments = CMTEFeePaymentRecord.query.filter(CMTEFeePaymentRecord.payment_datetime == None).all()
    if request.method == 'DELETE':
        db.session.delete(record)
        db.session.commit()
        resp = make_response()
        resp.headers['HX-Redirect'] = url_for('cmte.admin_edit_fee_payment_record')
        return resp
    if request.method == 'POST':
        if form.validate_on_submit():
            if not record:
                license = License.query.filter_by(number=form.license_number.data).one()
                if license:
                    if license.get_active_cmte_fee_payment():
                        flash('Fee payment has been recorded and active.', 'warning')
                        return redirect(url_for('member.admin_index'))
                    else:
                        flash('Fee payment record update failed. No license number found.', 'danger')
                record = CMTEFeePaymentRecord()
                record.start_date = license.start_date
                record.end_date = license.end_date
                record.license_number = license.number

            form.populate_obj(record)
            db.session.add(record)
            db.session.commit()
            flash('Fee payment record has been created/approved.', 'success')
            next = request.args.get('next')
            return redirect(next or url_for('cmte.admin_edit_fee_payment_record'))
        else:
            print('form is not valid')
            flash('Error updating fee payment record form.', 'danger')
    return render_template('cmte/admin/fee_payment_form.html',
                           form=form, active_payments=active_payments, record=record,
                           pending_payments=pending_payments)


@cmte.route('/sponsors/members/login', methods=['GET', 'POST'])
def sponsor_member_login():
    form = CMTESponsorMemberLoginForm()
    if form.validate_on_submit():
        user = CMTESponsorMember.query.filter_by(email=form.email.data).first()
        if user:
            if user.verify_password(form.password.data):
                session['login_as'] = 'cmte_sponsor_admin'
                login_user(user, remember=False)
                identity = Identity(user.unique_id)
                identity_changed.send(current_app._get_current_object(), identity=identity)
                flash('Logged in successfully', 'success')
                if request.args.get('next'):
                    return redirect(request.args.get('next'))
                else:
                    return redirect(url_for('cmte.cmte_index'))
            else:
                flash('Wrong password.', 'danger')
        else:
            flash('Your account is not registered.', 'danger')
    return render_template('cmte/sponsor/login_form.html', form=form)


@cmte.route('/sponsors/members/register', methods=['GET', 'POST'])
@cmte.route('/sponsors/members/register/add-member/<int:sponsor_id>', methods=['GET', 'POST'])
def register_sponsor_member(sponsor_id=None):
    if sponsor_id:
        all_members = CMTESponsorMember.query.filter_by(sponsor_id=sponsor_id) \
            .filter(CMTESponsorMember.is_valid != False).count()
        if all_members >= 10:
            flash(f'ไม่สามารถเพิ่มข้อมูลใหม่ได้ เนื่องจากจำนวนผู้ประสานงานมีมากกว่าที่กำหนด', 'danger')
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
    form = CMTESponsorMemberForm()
    if form.validate_on_submit():
        member = CMTESponsorMember.query.filter_by(email=form.email.data).first()
        if not member:
            member = CMTESponsorMember()
            form.populate_obj(member)
            member.password = form.password.data
            member.is_valid = True
            db.session.add(member)
            db.session.commit()
            if sponsor_id:
                member.sponsor_id = sponsor_id
                db.session.add(member)
                db.session.commit()
                flash(f'เพิ่มผู้ประสานงานเรียบร้อยแล้ว', 'success')
                # is_admin = True if cmte_admin_permission else False
                # if not is_admin:
                #     print('send notification to admin of CMTE')
                return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
            else:
                flash(f'ลงทะเบียนเรียบร้อยแล้ว กรุณาลงชื่อเข้าใช้งาน', 'success')
                return redirect(url_for('cmte.sponsor_member_login'))
        else:
            flash(f'{form.email.data} มีการลงทะเบียนแล้ว หากลืมรหัสผ่านกรุณาติดต่อเจ้าหน้าที่', 'warning')
    return render_template('cmte/sponsor/member_form.html', form=form)


@cmte.route('/sponsors/member/manage/<int:member_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def manage_member(member_id):
    member = CMTESponsorMember.query.filter_by(id=member_id).first()
    form = CMTESponsorMemberEditForm(obj=member)
    if form.validate_on_submit():
        member = CMTESponsorMember.query.get(member_id)
        form.populate_obj(member)
        db.session.add(member)
        db.session.commit()
        flash('อัพเดทข้อมูลเรียบร้อยแล้ว', 'success')
        # is_admin = True if cmte_admin_permission else False
        # if not is_admin:
        #     print('send notification to admin of CMTE')
    else:
        for er in form.errors:
            flash("{}:{}".format(er, form.errors[er]), 'danger')
    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp
    return render_template('cmte/sponsor/view_each_member.html', member=member)


@cmte.route('/sponsors/member/modal/<int:member_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def member_modal(member_id):
    if member_id:
        member = CMTESponsorMember.query.get(member_id)
        form = CMTESponsorMemberEditForm(obj=member)
    is_admin = True if cmte_admin_permission else False
    return render_template('cmte/sponsor/member_modal.html', form=form, member=member, is_admin=is_admin)


@cmte.route('/sponsors/member/del/<int:sponsor_id>/<int:member_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def del_member(sponsor_id, member_id):
    member = CMTESponsorMember.query.get(member_id)
    if member.is_coordinator:
        flash('{}เป็นผู้ประสานงานหลัก หากต้องการลบบัญชีนี้ กรุณาแก้ไขสถานะผู้ประสานงานหลักก่อน'.format(member),
              'warning')
    else:
        member.is_valid = False
        db.session.add(member)
        db.session.commit()
        flash('ยกเลิกบัญชี {} เรียบร้อยแล้ว'.format(member), 'warning')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/request/change-coordinator/<int:sponsor_id>/<int:member_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def request_change_coordinator_member(sponsor_id, member_id):
    member = CMTESponsorMember.query.get(member_id)
    create_request = CMTESponsorRequest(
        sponsor_id=sponsor_id,
        created_at=arrow.now('Asia/Bangkok').datetime,
        type='change',
        comment='Change Lead coordinator to be ' + member.email,
        member=member
    )
    db.session.add(create_request)
    db.session.commit()
    flash('ส่งคำขอเป็นผู้ประสานงานหลัก เรียบร้อยแล้ว', 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/request/change-coordinator/<int:sponsor_id>/<int:request_id>/cancel', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def cancel_request_change_coordinator_member(sponsor_id, request_id):
    request = CMTESponsorRequest.query.get(request_id)
    request.cancelled_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(request)
    db.session.commit()
    flash('ยกเลิกคำขอเรียบร้อยแล้ว', 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/change-coordinator/<int:sponsor_id>/<int:member_id>/<int:request_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def change_coordinator_member(sponsor_id, member_id, request_id):
    all_member = CMTESponsorMember.query.filter_by(sponsor_id=sponsor_id).all()
    for member in all_member:
        member.is_coordinator = False
    member = CMTESponsorMember.query.get(member_id)
    member.is_coordinator = True
    db.session.add(member)
    request = CMTESponsorRequest.query.get(request_id)
    request.approved_at = arrow.now('Asia/Bangkok').datetime
    db.session.commit()
    flash('{}เป็นผู้ประสานงานหลัก เรียบร้อยแล้ว'.format(member), 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/register', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def register_sponsor():
    if not cmte_admin_permission:
        if current_user.sponsor:
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=current_user.sponsor_id))
    form = CMTEEventSponsorForm()
    is_admin = True if cmte_admin_permission else False
    if request.method == 'POST':
        if form.validate_on_submit():
            sponsor = CMTEEventSponsor.query.filter_by(name=form.name.data).first()
            if not sponsor:
                sponsor = CMTEEventSponsor()
                form.populate_obj(sponsor)
                db.session.add(sponsor)
                db.session.commit()

                s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                         aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                         region_name=os.environ.get('BUCKETEER_AWS_REGION'))
                for field, _file in request.files.items():
                    filename = _file.filename
                    key = uuid.uuid4()
                    s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                    doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename)
                    doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                    doc.note = request.form.get(field + '_note')
                    db.session.add(doc)
                if not cmte_admin_permission:
                    sponsor.members.append(current_user)
                    db.session.add(sponsor)
                    member = CMTESponsorMember.query.filter_by(id=current_user.id).first()
                    member.is_coordinator = True
                    db.session.add(member)
                    db.session.commit()

                    create_request = CMTESponsorRequest(
                        sponsor=sponsor,
                        created_at=arrow.now('Asia/Bangkok').datetime,
                        type='new'
                    )
                    db.session.add(create_request)
                    db.session.commit()
                    flash(f'ลงทะเบียนเรียบร้อย', 'success')
                    return redirect(url_for('cmte.cmte_index'))
                else:
                    flash(f'เพิ่มสถาบันใหม่เรียบร้อย', 'success')
                    return redirect(url_for('cmte.all_sponsors'))
            else:
                flash(f'{form.name.data} มีการลงทะเบียนแล้ว กรุณาติดต่อเจ้าหน้าที่', 'warning')
        else:
            flash(f'Errors: {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_form.html', form=form, is_admin=is_admin)


@cmte.route('/sponsors/request-org', methods=['GET', 'POST'])
@cmte.route('/sponsors/request-org/<int:sponsor_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def get_org_type(sponsor_id=None):
    org_type = request.args.get('type', type=str)
    if org_type == 'เป็นสถาบันการศึกษา(คณะ/ภาควิชา/หน่วยงานที่มีฐานะเทียบเท่าคณะหรือภาควิชาที่ผลิตบัณฑิตเทคนิคการแพทย์)':
        detail = 'โปรดระบุจำนวนอาจารย์เทคนิคการแพทย์ในสังกัด(คน)'
    elif org_type == 'เป็นสถาบันการศึกษา(คณะ/ภาควิชา/หน่วยงานที่มีฐานะเทียบเท่าคณะหรือภาควิชา)':
        detail = 'โปรดระบุ คณะ/ภาควิชา/หน่วยงานที่มีฐานะเทียบเท่าคณะหรือภาควิชา'
    elif org_type == 'เป็นสถานพยาบาล':
        detail = 'โปรดระบุ 1.ประเภทสถานพยาบาล 2.จํานวนเตียงรับผู้ป่วย(เตียง) 3.จํานวนเทคนิคการแพทย์ในสังกัด(คน)'
    elif org_type == 'เป็นหน่วยงาน/องค์กรตามที่สภาเทคนิคการแพทย์ประกาศกําหนด':
        detail = 'โปรดระบุ'
    elif org_type == 'เป็นหน่วยงาน/องค์กรของรัฐหรือเอกชน':
        detail = 'โปรดระบุ'
    if sponsor_id:
        sponsor = CMTEEventSponsor.query.get(sponsor_id)
        type_detail = f'''{detail}<textarea name="type_detail" class="textarea" rows="1">{sponsor.type_detail}</textarea>'''
    else:
        type_detail = f'''{detail}<textarea name="type_detail" class="textarea" rows="1"></textarea>'''
    resp = make_response(type_detail)
    resp.headers['HX-Trigger-After-Swap'] = 'initSelect2'
    return resp


@cmte.route('/sponsors/get_qualifications', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def get_qualifications():
    private_sector = request.args.get('private_sector')
    if private_sector == 'private':
        qualifications = CMTESponsorQualification.query.all()
    else:
        qualifications = CMTESponsorQualification.query.filter_by(private_sector=False).all()
    qualification_html = ""
    for i, qualification in enumerate(qualifications, start=1):
        qualification_html += f'''
                <div class="field">
                    <label class="label">{qualification}</label>
                    <input type="file" name="file_qualification_{i}">
                </div>
                <div class="field">
                    <textarea name="file_qualification_{i}_note" rows="2" class="textarea" placeholder='คำอธิบายเพิ่มเติม (ถ้ามี)'></textarea>
                </div>
            '''
    resp = make_response(qualification_html)
    resp.headers['HX-Trigger-After-Swap'] = 'initSelect2'
    return resp


@cmte.route('/sponsors/<int:sponsor_id>/edit-request', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def request_edit_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    form = CMTEEventSponsorForm(obj=sponsor)
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(sponsor)
            db.session.add(sponsor)

            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            for field, _file in request.files.items():
                filename = _file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = request.form.get(field + '_note')
                if filename:
                    db.session.add(doc)
            db.session.commit()
            version_index = sponsor.versions.count() - 1
            create_request = CMTESponsorEditRequest(
                sponsor=sponsor,
                created_at=arrow.now('Asia/Bangkok').datetime,
                member=current_user,
                version_index=version_index,
                status='pending'
            )
            db.session.add(create_request)
            db.session.commit()
            flash(f'ส่งขอแก้ไขข้อมูลเรียบร้อย', 'success')
            # send email to admin
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Errors: {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_request_form.html', form=form, sponsor=sponsor)


@cmte.route('/sponsors/<int:sponsor_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def manage_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    form = CMTEEventSponsorForm(obj=sponsor)
    pending_request = CMTESponsorRequest.query.filter_by(sponsor_id=sponsor_id,
                                                         expired_sponsor_date=sponsor.expire_date).first()
    edit_requests = CMTESponsorEditRequest.query.filter_by(sponsor_id=sponsor_id).all()
    if form.validate_on_submit():
        event_sponsor = CMTEEventSponsor.query.get(sponsor_id)
        form.populate_obj(event_sponsor)

        db.session.add(event_sponsor)
        db.session.commit()

        flash('อัพเดทข้อมูลเรียบร้อยแล้ว', 'success')
        for version in event_sponsor.versions:
            print(version.changeset)
        # is_admin = True if cmte_admin_permission else False
        # if not is_admin:
        #     print('send notification to admin of CMTE')
    else:
        for er in form.errors:
            flash("{}:{}".format(er, form.errors[er]), 'danger')
    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp
    is_admin = True if cmte_admin_permission else False
    return render_template('cmte/sponsor/view_sponsor.html', sponsor=sponsor, is_admin=is_admin,
                           edit_requests=edit_requests, pending_request=pending_request)


@cmte.route('/sponsors/<int:sponsor_id>/<int:request_id>/payment', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def sponsor_payment(sponsor_id, request_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    form = CMTESponsorPaymentForm(obj=sponsor)
    if request.method == 'POST':
        if form.validate_on_submit():
            doc = CMTESponsorDoc.query.filter_by(sponsor_id=sponsor_id, is_payment_slip=True,
                                                 request_id=request_id).first()
            if doc:
                db.session.delete(doc)
                db.session.commit()
            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            _file = form.upload_file.upload_file.data
            if _file:
                filename = _file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename, request_id=request_id)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = form.upload_file.note.data
                doc.is_payment_slip = True
                doc.request_id = request_id
                db.session.add(doc)
                flash('ชำระค่าธรรมเนียมเรียบร้อยแล้ว', 'success')
            else:
                flash('ไม่พบ slip ที่อัพโหลด กรุณาดำเนินการใหม่อีกครั้ง', 'danger')
                return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))

            req = CMTESponsorRequest.query.get(request_id)
            dt = '{} {}'.format(form.paid_date.data, form.paid_time.data)
            paid_datetime = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            req.paid_at = paid_datetime
            db.session.add(req)

            is_receive = CMTEReceiptDetail.query.filter_by(sponsor_id=sponsor_id).first()
            if is_receive:
                db.session.delete(is_receive)
                db.session.commit()

            create_receipt = CMTEReceiptDetail(
                sponsor_id=sponsor_id,
                name=form.name.data,
                receipt_item=form.receipt_item.data if form.receipt_item.data else '',
                tax_id=form.tax_id.data if form.tax_id.data else '',
                address=form.address.data,
                zipcode=form.zipcode.data
            )
            db.session.add(create_receipt)
            db.session.commit()
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_payment_form.html', sponsor=sponsor, form=form)


@cmte.route('/sponsors/<int:sponsor_id>/renew', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def request_renew_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    is_request = CMTESponsorRequest.query.filter_by(sponsor_id=sponsor_id, paid_at=None).first()
    if not is_request:
        create_request = CMTESponsorRequest(
            sponsor_id=sponsor_id,
            created_at=arrow.now('Asia/Bangkok').datetime,
            expired_sponsor_date=sponsor.expire_date,
            type='renew',
            member=current_user
        )
        db.session.add(create_request)
        db.session.commit()
        flash('ส่งคำขอต่ออายุสถาบันเรียบร้อยแล้ว', 'success')
    else:
        flash('มีการส่งคำขอต่ออายุสถาบันแล้ว', 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/modal/<int:sponsor_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def sponsor_modal(sponsor_id):
    if sponsor_id:
        sponsor = CMTEEventSponsor.query.get(sponsor_id)
        form = CMTEEventSponsorForm(obj=sponsor)
    is_admin = True if cmte_admin_permission else False
    return render_template('cmte/sponsor/sponsor_modal.html', form=form, sponsor=sponsor, is_admin=is_admin)


@cmte.get('/admin/requests')
@login_required
@cmte_admin_permission.require()
def all_requests():
    tab = request.args.get('tab')
    pending_new = CMTESponsorRequest.query.filter_by(type='new', approved_at=None).count()
    pending_renew = CMTESponsorRequest.query.filter_by(type='renew').count()
    pending_paid = CMTESponsorRequest.query.filter_by(verified_at=None).filter(
        CMTESponsorRequest.paid_at != None).count()
    pending_edit = CMTESponsorEditRequest.query.filter_by(status='pending').count()
    pending_change = CMTESponsorRequest.query.filter_by(type='change', cancelled_at=None, approved_at=None).count()
    if tab == 'new':
        requests = CMTESponsorRequest.query.filter_by(type='new', approved_at=None).all()
    elif tab == 'renew':
        requests = CMTESponsorRequest.query.filter_by(type='renew').all()
    elif tab == 'paid':
        requests = CMTESponsorRequest.query.filter_by(verified_at=None).filter(CMTESponsorRequest.paid_at != None).all()
    elif tab == 'edit':
        requests = CMTESponsorEditRequest.query.filter_by(status='pending').all()
    elif tab == 'change':
        requests = CMTESponsorRequest.query.filter_by(type='change', cancelled_at=None, approved_at=None).all()
    else:
        all_request = CMTESponsorRequest.query.all()
        edit_request = CMTESponsorEditRequest.query.all()
        requests = all_request + edit_request
    return render_template('cmte/admin/sponsor_registration.html', requests=requests, tab=tab,
                           pending_new=pending_new, pending_renew=pending_renew, pending_paid=pending_paid,
                           pending_edit=pending_edit, pending_change=pending_change)


@cmte.get('/admin/sponsors')
@login_required
@cmte_admin_permission.require()
def all_sponsors():
    sponsors = CMTEEventSponsor.query.all()
    return render_template('cmte/admin/all_sponsors.html', sponsors=sponsors)


@cmte.get('/admin/sponsors/<int:sponsor_id>/disable')
@login_required
@cmte_admin_permission.require()
def disable_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    sponsor.disable_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(sponsor)
    db.session.commit()
    flash('ยกเลิกบัญชี {} เรียบร้อยแล้ว'.format(sponsor.name), 'warning')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.get('/admin/sponsors/<int:sponsor_id>/enable')
@login_required
@cmte_admin_permission.require()
def enable_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    sponsor.disable_at = None
    db.session.add(sponsor)
    db.session.commit()
    flash('เปิดบัญชี {} เรียบร้อยแล้ว'.format(sponsor.name), 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/<int:request_id>/approved-renew', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def approved_renew_sponsor(request_id):
    # need to keep old expired_date?
    renew_request = CMTESponsorRequest.query.get(request_id)
    renew_request.approved_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(renew_request)
    db.session.commit()
    flash('อนุมัติคำขอต่ออายุสถาบันแล้ว สถาบันได้รับการแจ้งเตือนเรียบร้อยแล้ว', 'success')
    # send email to sponsor member
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=renew_request.sponsor_id))


@cmte.route('/sponsors-edit/<int:request_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def manage_edit_sponsor(request_id):
    edit_request = CMTESponsorEditRequest.query.get(request_id)
    current_version = edit_request.sponsor.versions[edit_request.version_index]
    previous_version = current_version.previous
    return render_template('cmte/admin/edit_sponsor.html', current_version=current_version,
                           previous_version=previous_version,
                           edit_request=edit_request)


@cmte.route('/sponsors/<int:request_id>/approved-edit', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def approved_edit_sponsor(request_id):
    edit_request = CMTESponsorEditRequest.query.get(request_id)
    status = request.args.get("status")
    edit_request.status = status
    edit_request.updated_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(edit_request)

    if status == 'reject':
        current_version_index = edit_request.version_index
        current_version = edit_request.sponsor.versions[current_version_index]
        current_version.revert()
        db.session.commit()
        # if previous_version:
        #     for column in edit_request.sponsor.__table__.columns:
        #         field_name = column.name
        #         if hasattr(previous_version, field_name):
        #             setattr(edit_request.sponsor, field_name, getattr(previous_version, field_name))

    db.session.commit()
    flash('บันทึกข้อมูลเรียบร้อยแล้ว **อย่าลืมลบเอกสารแนบที่ถูกแก้ไข** สถาบันได้รับการแจ้งเตือนแล้ว',
          'warning')
    # send email to sponsor member
    return redirect(url_for('cmte.manage_edit_sponsor', request_id=request_id))


@cmte.route('/sponsors/reject-modal/<int:sponsor_id>/<int:request_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def sponsor_reject_modal(sponsor_id, request_id):
    sponsor_request = CMTESponsorRequest.query.get(request_id)
    form = CMTESponsorRequestForm(obj=sponsor_request)
    return render_template('cmte/admin/sponsor_reject_modal.html', form=form,
                           request_id=request_id, sponsor_id=sponsor_id)


@cmte.route('/sponsors/reject-modal/<int:sponsor_id>/<int:request_id>/submit', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def reject_sponsor(sponsor_id, request_id):
    sponsor_request = CMTESponsorRequest.query.get(request_id)
    form = CMTESponsorRequestForm(obj=sponsor_request)
    if form.validate_on_submit():
        sponsor_request.comment = request.form.get('comment')
        sponsor_request.rejected_at = arrow.now('Asia/Bangkok').datetime
        db.session.add(sponsor_request)

        sponsor = CMTEEventSponsor.query.get(sponsor_id)
        sponsor.disable_at = arrow.now('Asia/Bangkok').datetime
        db.session.add(sponsor)
        db.session.commit()
        # send email to sponsor member
        return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
    else:
        for er in form.errors:
            flash("{}:{}".format(er, form.errors[er]), 'danger')
    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp


@cmte.route('/sponsors/<int:sponsor_id>/delete-doc/<int:doc_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def admin_delete_doc(sponsor_id, doc_id):
    doc = CMTESponsorDoc.query.get(doc_id)
    db.session.delete(doc)
    db.session.commit()
    flash('ลบไฟล์เรียบร้อยแล้ว', 'success')
    # send email to sponsor member
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/<int:request_id>/verified-payment', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def verified_payment_sponsor(request_id):
    payment_request = CMTESponsorRequest.query.get(request_id)
    payment_request.verified_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(payment_request)
    db.session.commit()

    sponsor = CMTEEventSponsor.query.filter_by(id=payment_request.sponsor_id).first()
    if sponsor.expire_date:
        old_expire_date = sponsor.expire_date + timedelta(days=1)
        sponsor.registered_datetime = old_expire_date
        expire_date = old_expire_date.replace(year=old_expire_date.year + 5)
        sponsor.expire_date = expire_date - timedelta(days=1)
    else:
        today = arrow.now('Asia/Bangkok').datetime
        sponsor.registered_datetime = today
        expire_date = today.replace(year=today.year + 5)
        sponsor.expire_date = expire_date - timedelta(days=1)
    db.session.add(sponsor)
    db.session.commit()
    flash('ตรวจสอบการชำระเงินเรียบร้อยแล้ว สถาบันได้รับการแจ้งเตือนเรียบร้อยแล้ว', 'success')
    # send email to sponsor member
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=payment_request.sponsor_id))


@cmte.route('/sponsors/<int:sponsor_id>/<int:request_id>/upload-receipt', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def sponsor_upload_receipt(sponsor_id, request_id):
    form = CMTESponsorReceiptForm()
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    if request.method == 'POST':
        if form.validate_on_submit():
            doc = CMTEReceiptDoc.query.filter_by(request_id=request_id).first()
            if doc:
                db.session.delete(doc)
                db.session.commit()
            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            _file = form.upload_file.upload_file.data
            if _file:
                filename = _file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTEReceiptDoc(key=key, filename=filename, request_id=request_id)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = form.upload_file.note.data
                db.session.add(doc)
                db.session.commit()
                flash('upload ใบเสร็จเรียบร้อยแล้ว', 'success')
            else:
                flash('ไม่พบใบเสร็จที่อัพโหลด กรุณาดำเนินการใหม่อีกครั้ง', 'danger')
                return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))

            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/admin/upload_slip.html', sponsor=sponsor, form=form)


@cmte.route('/admin/events', methods=['GET', 'POST'])
@cmte.route('/admin/events/<int:event_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_event_edit(event_id=None):
    if event_id:
        event = CMTEEvent.query.get(event_id)
        form = CMTEAdminEventForm(obj=event)
    else:
        event = None
        form = CMTEAdminEventForm()
    if request.method == 'DELETE':
        db.session.delete(event)
        db.session.commit()
        resp = make_response()
        flash('ลบกิจกรรมเรียบร้อยแล้ว', 'success')
        resp.headers['HX-Redirect'] = url_for('users.cmte_admin_index')
        return resp
    if request.method == 'POST':
        if form.validate_on_submit():
            if not event:
                event = CMTEEvent()
            form.populate_obj(event)
            if event.approved_datetime:
                event.submission_due_date = event.approved_datetime + timedelta(days=30)
            db.session.add(event)
            db.session.commit()
            flash('เพิ่มกิจกรรมเรียบร้อย', 'success')
            return redirect(url_for('cmte.admin_preview_event', event_id=event.id))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/admin/admin_event_form.html', form=form, event=event)


@cmte.route('/upcoming-events')
def upcoming_events():
    return render_template('members/cmte/upcoming_events.html')


@cmte.route('/events/<int:event_id>/info')
def show_event_detail_modal(event_id):
    event = CMTEEvent.query.get(event_id)
    return render_template('members/cmte/event_info_modal.html', event=event)


@cmte.route('/events/individuals/index')
@login_required
@cmte_admin_permission.require()
def admin_individual_score_index():
    records = CMTEEventParticipationRecord.query.filter_by(individual=True,
                                                           approved_date=None,
                                                           closed_date=None)
    return render_template('cmte/admin/individual_scores.html', records=records)


@cmte.route('/events/individuals/<int:record_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_individual_score_detail(record_id):
    record = CMTEEventParticipationRecord.query.get(record_id)
    form = IndividualScoreAdminForm(obj=record)
    if request.method == 'POST':
        approved = request.form.get('approved')
        if approved == 'true':
            if form.score.data and form.score.data > 0.0:
                form.populate_obj(record)
                record.approved_date = arrow.now('Asia/Bangkok').date()
                record.set_score_valid_date()
                db.session.add(record)
                db.session.commit()
                flash('อนุมัติคะแนนเรียบร้อย', 'success')
                return redirect(url_for('cmte.admin_individual_score_index'))
            else:
                flash('กรุณาตรวจสอบคะแนนอีกครั้ง', 'warning')
        else:
            form.populate_obj(record)
            record.closed_date = arrow.now('Asia/Bangkok').date()
            db.session.add(record)
            db.session.commit()
            flash('บันทึกข้อมูลเรียบร้อย', 'success')
            return redirect(url_for('cmte.admin_individual_score_index'))
    return render_template('cmte/admin/individual_score_detail.html', record=record, form=form)


@cmte.route('/events/individuals/docs/<int:doc_id>', methods=['DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_delete_upload_file(doc_id: int):
    doc = CMTEEventDoc.query.get(doc_id)
    if doc:
        db.session.delete(doc)
        db.session.commit()
        flash('The document has been deleted.', 'success')
        resp = make_response(render_template('messages.html'))
        return resp


@cmte.route('/events/individuals/<int:record_id>/edit', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_individual_score_edit(record_id):
    record = CMTEEventParticipationRecord.query.get(record_id)
    form = IndividualScoreAdminForm(obj=record)
    if request.method == 'DELETE':
        db.session.delete(record)
        db.session.commit()
        resp = make_response()
        resp.headers['HX-Redirect'] = url_for('cmte.admin_individual_score_index')
        return resp
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(record)
            record.create_datetime = arrow.now('Asia/Bangkok').datetime
            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            for doc_form in form.upload_files:
                _file = doc_form.upload_file.data
                if _file:
                    filename = _file.filename
                    key = uuid.uuid4()
                    s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                    doc = CMTEEventDoc(record=record, key=key, filename=filename)
                    doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                    doc.note = doc_form.note.data
                    record.docs.append(doc)
                    db.session.add(doc)
            db.session.add(record)
            db.session.commit()
            flash('ดำเนินการบันทึกข้อมูลเรียบร้อย โปรดรอการอนุมัติคะแนน', 'success')
            return redirect(url_for('cmte.admin_individual_score_detail', record_id=record_id))
    return render_template('cmte/admin/individual_score_form.html', form=form, record=record)


@cmte.route('/payments/<int:record_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_approve_individual_score_payment(record_id):
    pass


@cmte.route('/events/<int:event_id>/payment-confirm', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_confirm_payment(event_id):
    event = CMTEEvent.query.get(event_id)
    event.payment_approved_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(event)
    db.session.commit()
    template = f'''
    <span class='tag is-rounded is-small is-success'>{event.payment_approved_at.strftime('%d/%m/%Y %H:%M')}</span>
    '''
    return template


@cmte.route('/admin/events/management', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_manage_events():
    event_types = CMTEEventType.query.order_by(CMTEEventType.number)
    return render_template('cmte/admin/event_management_index.html', event_types=event_types)


@cmte.route('/admin/event-types/add', methods=['GET', 'POST'])
@cmte.route('/admin/event-types/<int:event_type_id>/management', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def admin_manage_event_type(event_type_id=None):
    if event_type_id:
        event_type = CMTEEventType.query.get(event_type_id)
        form = CMTEAdminEventTypeForm(obj=event_type)
    else:
        form = CMTEAdminEventTypeForm()
    if form.validate_on_submit():
        if not event_type_id:
            existing_event_type = CMTEEventType.query.filter_by(name=form.name.data) \
                .filter(CMTEEventType.deprecated != True).first()
            if not existing_event_type:
                event_type = CMTEEventType()
                event_type.created_at = arrow.now('Asia/Bangkok').datetime
        else:
            event_type.updated_at = arrow.now('Asia/Bangkok').datetime
        form.populate_obj(event_type)
        db.session.add(event_type)
        db.session.commit()
        flash('บันทึกข้อมูลแล้ว', 'success')
        return redirect(url_for('cmte.admin_manage_events'))
    else:
        if form.errors:
            flash(form.errors, 'danger')
    return render_template('cmte/admin/event_type_form.html', form=form)


@cmte.route('/admin/event-types/<int:event_type_id>/event-activities/management')
@login_required
@cmte_admin_permission.require()
def admin_manage_event_activity(event_type_id):
    event_type = CMTEEventType.query.get(event_type_id)
    return render_template('cmte/admin/event_activity_management_index.html',
                           event_type=event_type)


@cmte.route('/admin/event-types/<int:event_type_id>/event-activities/edit',
            methods=['GET', 'POST'])
@cmte.route('/admin/event-types/<int:event_type_id>/event-activities/<int:event_activity_id>/edit',
            methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def admin_edit_event_activity(event_type_id, event_activity_id=None):
    event_type = CMTEEventType.query.get(event_type_id)
    if event_activity_id:
        event_activity = CMTEEventActivity.query.get(event_activity_id)
        form = CMTEAdminEventActivityForm(obj=event_activity)
    else:
        form = CMTEAdminEventActivityForm(data={'event_type': event_type})
    if form.validate_on_submit():
        if not event_activity_id:
            event_activity = CMTEEventActivity(type_id=event_type_id)
            event_activity.created_at = arrow.now('Asia/Bangkok').datetime
        else:
            event_activity.updated_at = arrow.now('Asia/Bangkok').datetime

        form.populate_obj(event_activity)
        db.session.add(event_activity)
        db.session.commit()
        flash('บันทึกชนิดกิจกรรมแล้ว', 'success')
        return redirect(url_for('cmte.admin_manage_event_activity', event_type_id=event_type_id))
    return render_template('cmte/admin/event_activity_form.html',
                           form=form, event_type_id=event_type_id)
