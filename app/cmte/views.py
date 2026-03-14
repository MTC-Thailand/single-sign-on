import io
import re
import time
import os
import uuid
import calendar
from functools import wraps
from io import BytesIO
from pprint import pprint

import pandas as pd
import arrow
import boto3
from flask import (render_template, flash, redirect,
                   url_for, make_response, request, send_file,
                   current_app, session, jsonify, abort)
from flask_login import login_required, login_user, current_user
from flask_principal import identity_changed, Identity
from flask_wtf.csrf import generate_csrf
from itsdangerous import TimedJSONWebSignatureSerializer
from sqlalchemy import or_, func, and_, case

from app import sponsor_event_management_permission, send_mail
from app.cmte import cmte_bp as cmte
from app.cmte.forms import *
from app.members.models import Member
from app.cmte.models import *
from app import cmte_admin_permission, cmte_sponsor_admin_permission

bangkok = timezone('Asia/Bangkok')


@cmte.route('/sponsor-expiration/notification')
def notify_sponsor_expiration():
    today = datetime.now().date()
    for sponsor in CMTEEventSponsor.query\
            .filter(CMTEEventSponsor.expire_date != None).filter(CMTEEventSponsor.disable_at == None):
        if (sponsor.expire_date - today).days == 90:
            mails = []
            all_members = CMTESponsorMember.query.filter_by(sponsor=sponsor).all()
            for member in all_members:
                mails.append(member.email)

            url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
            message = f'''
                          เรียน ผู้ประสานงาน

                          {sponsor.name} จะหมดอายุการรับรองในอีก 3 เดือน
                          \n
                          ท่านสามารถดำเนินการส่งคำขอต่ออายุได้ที่ {url}
                          \n\n
                          หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                          \n
                          ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                          '''
            send_mail(mails, 'MTC-CMTE แจ้งเตือนการต่ออายุสถาบัน', message)
        elif (sponsor.expire_date - today).days == 30:
            mails = []
            all_members = CMTESponsorMember.query.filter_by(sponsor=sponsor).all()
            for member in all_members:
                mails.append(member.email)

            url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
            message = f'''
                                      เรียน ผู้ประสานงาน

                                      {sponsor.name} จะหมดอายุการรับรองในอีก 1 เดือน
                                      \n
                                      ท่านสามารถดำเนินการส่งคำขอต่ออายุได้ที่ {url}
                                      \n\n
                                      หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                                      \n
                          ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                                      '''
            send_mail(mails, 'MTC-CMTE แจ้งเตือนการต่ออายุสถาบัน', message)


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
    sponsor_member_add_pending_requests = current_user.get_pending_sponsor_requests()
    print(sponsor_member_add_pending_requests.all())
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
    return render_template('cmte/index.html', warning_msg=warning_msg,
                           sponsor_member_add_pending_requests=sponsor_member_add_pending_requests)


@cmte.get('/events/registration')
@active_sponsor_required
@login_required
@cmte_sponsor_admin_permission.require()
def register_event():
    if not sponsor_event_management_permission.can():
        return render_template('errors/sponsor_expired.html')
    form = CMTEEventForm(data={
        'coord_name': str(current_user),
        'coord_email': current_user.email,
        'coord_phone': current_user.mobile_phone,
    })
    return render_template('cmte/event_registration.html', form=form)


@cmte.get('/events/<int:event_id>/edit')
@login_required
@cmte_sponsor_admin_permission.require()
def edit_event(event_id):
    event = CMTEEvent.query.get(event_id)
    form = CMTEEventForm(obj=event)
    form.start_date.data = arrow.get(event.start_date).to('Asia/Bangkok')
    form.end_date.data = arrow.get(event.end_date).to('Asia/Bangkok')
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
    source = request.args.get('source')
    if request.args.get('source') == 'admin':
        form = CMTEAdminParticipantFileUploadForm()
    else:
        form = CMTEParticipantFileUploadForm()
    event = CMTEEvent.query.get(event_id)
    if form.validate_on_submit():
        score_file = form.upload_file.data
        if score_file:
            df = pd.read_excel(score_file, sheet_name='Sheet1')
            for idx, row in df.iterrows():
                if not pd.isna(row['license_number']):
                    license_number = str(int(row['license_number']))
                    score = float(row['score'])
                    license = License.query.filter_by(number=license_number).first()
                else:
                    license = None

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
            event.participant_updated_at = arrow.now('Asia/Bangkok').datetime
            db.session.add(event)
            db.session.commit()
            flash('เพิ่มรายชื่อผู้เข้าร่วมแล้ว', 'success')

            evidence_file = form.evidence_file.data
            if evidence_file:
                s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                         aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                         region_name=os.environ.get('BUCKETEER_AWS_REGION'))
                filename = evidence_file.filename
                key = uuid.uuid4()
                s3_client.upload_fileobj(evidence_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                doc = CMTEEventDoc(event=event, key=key, filename=filename)
                doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                doc.note = 'ไฟล์หลักฐานการเข้าร่วมกิจกรรม'
                db.session.add(doc)
                event.payment_datetime = arrow.now('Asia/Bangkok').datetime
                db.session.add(event)
                db.session.commit()
        if errors:
            df_ = pd.DataFrame(errors)
            return render_template('cmte/sponsor/score_upload_errors.html',
                                   errors=df_.to_html(classes=['table is-fullwidth is-striped']),
                                   event=event,
                                   source=source)
    else:
        flash(f'{form.errors}', 'danger')
    if source == 'admin':
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
    participant_form = CMTEAdminParticipantFileUploadForm()
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
    event = CMTEEvent.query.get(event_id)
    form = CMTEPaymentForm(obj=event.sponsor)
    form.address.data = f"{event.sponsor.address} {event.sponsor.zipcode}"
    form.shipping_address.data = f"{event.sponsor.address} {event.sponsor.zipcode}"
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
                doc.bill_name = request.form.get('name')
                doc.receipt_item = request.form.get('receipt_item')
                doc.tax_id = request.form.get('tax_id')
                doc.address = request.form.get('address')
                doc.shipping_address = request.form.get('shipping_address')
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
    query = '''SELECT e.id as event_id, e.title as title, e.participant_updated_at as participant_updated_at, s.name as sponsor, count(*) as number FROM cmte_event_participation_records AS r
    INNER JOIN cmte_events AS e ON r.event_id = e.id
    INNER JOIN cmte_event_sponsors AS s ON e.sponsor_id = s.id
    WHERE e.participant_updated_at is not null AND e.approved_datetime is not null AND r.approved_date is null
    GROUP BY e.id, e.title, s.name, e.participant_updated_at ORDER BY e.participant_updated_at DESC
    '''
    df = pd.read_sql_query(query, con=db.engine)
    return render_template('cmte/admin/approved_events.html',
                           _type='pending',
                           pendings=df)


@cmte.get('/admin/events/approved')
@login_required
@cmte_admin_permission.require()
def admin_approved_events():
    query = '''SELECT e.id as event_id, e.title as title, e.participant_updated_at as participant_updated_at, s.name as sponsor, count(*) as number FROM cmte_event_participation_records AS r
    INNER JOIN cmte_events AS e ON r.event_id = e.id
    INNER JOIN cmte_event_sponsors AS s ON e.sponsor_id = s.id
    WHERE e.participant_updated_at is not null AND e.approved_datetime is not null AND r.approved_date is null
    GROUP BY e.id, e.title, s.name, e.participant_updated_at ORDER BY e.participant_updated_at DESC
    '''
    df = pd.read_sql_query(query, con=db.engine)
    return render_template('cmte/admin/approved_events.html',
                           _type='approved',
                           pendings=df)


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
    event.submission_due_date = event.end_date + timedelta(days=event.event_type.submission_due)
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
    query = CMTEEvent.query.filter(CMTEEvent.submitted_datetime != None) \
        .filter(CMTEEvent.approved_datetime == None) \
        .filter_by(sponsor=current_user.sponsor)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/submitted_events.html', events=events.items, next_url=next_url)


@cmte.get('/events/approved')
@login_required
@cmte_sponsor_admin_permission.require()
def show_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None) \
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
        form = AdminParticipantForm(
            data={'license_number': license_number, 'approved_date': arrow.now('Asia/Bangkok').date()})
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
                           form=form,
                           record=record,
                           pending_payments=pending_payments)


@cmte.route('/api/cmte-individual-fee-payment/active-records')
@login_required
@cmte_admin_permission.require()
def get_cmte_individual_fee_payment_records():
    today = datetime.today()
    query = CMTEFeePaymentRecord.query.filter(CMTEFeePaymentRecord.end_date >= today)
    data = []
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    search = request.args.get('search[value]')

    total = query.count()

    if search:
        query = query.filter(CMTEFeePaymentRecord.license_number.like(f'%{search}%'))

    total_filtered = query.count()
    query = query.offset(start).limit(length)
    for record in query:
        data.append(record.to_dict())

    return jsonify({'data': data,
                    'draw': request.args.get('draw', type=int),
                    'recordsTotal': total,
                    'recordsFiltered': total_filtered,
                    })


@cmte.route('/sponsors/members/login', methods=['GET', 'POST'])
def sponsor_member_login():
    form = CMTESponsorMemberLoginForm()
    if form.validate_on_submit():
        user = CMTESponsorMember.query.filter_by(email=form.email.data).first()
        if user:
            if user.is_valid:
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
                return '<h1>Email has not been validated.</h1><p>กรุณาคลิก link ที่ส่งให้ทางอีเมลเพื่อทำการยืนยันอีเมลก่อนเข้าใช้งานระบบ</p>'
        else:
            flash('Your account is not registered.', 'danger')
    return render_template('cmte/sponsor/login_form.html', form=form)


@cmte.route('/members/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token')
    email = request.args.get('email')
    serializer = TimedJSONWebSignatureSerializer(current_app.config.get('SECRET_KEY'))
    try:
        token_data = serializer.loads(token)
    except Exception as e:
        return '<h1>Bad JSON Web token. You need a valid token.</h1>' + str(e)
    else:
        if token_data.get('email') != email:
            return '<h1>Invalid JSON Web token.</h1>'

        member = CMTESponsorMember.query.filter_by(email=email).first()
        if not member:
            return '<h1>Account not found.</h1>'
        else:
            form = CMTESponsorMemberPasswordForm()
            if form.validate_on_submit():
                member.password = request.form.get('password')
                db.session.add(member)
                db.session.commit()
                return redirect(url_for('cmte.sponsor_member_login'))
            return render_template('cmte/sponsor/reset_password_form.html', form=form)


@cmte.route('/members/forget-password', methods=['GET', 'POST'])
def forget_password():
    if request.method == 'POST':
        email = request.form.get('email')
        print(email)
        member = CMTESponsorMember.query.filter_by(email=email).first()
        if member:
            serializer = TimedJSONWebSignatureSerializer(current_app.config.get('SECRET_KEY'))
            token = serializer.dumps({'email': email})
            url = url_for('cmte.reset_password', token=token, email=email, _external=True)
            if not current_app.debug:
                message = f'''
                เรียน ท่านเจ้าของอีเมล
                \n
                กรุณาคลิกที่ลิงค์เพื่อยืนยันการแก้ไขรหัสผ่าน {url}
                \n\n
                หากไม่ได้ดำเนินการกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                '''
                send_mail([email], 'MTC-CMTE Email validation', message)
                return redirect(url_for('cmte.sponsor_member_login'))

    return render_template('cmte/sponsor/forget_password_form.html')


@cmte.route('/validate-email', methods=['GET'])
def validate_email():
    token = request.args.get('token')
    email = request.args.get('email')
    serializer = TimedJSONWebSignatureSerializer(current_app.config.get('SECRET_KEY'))
    try:
        token_data = serializer.loads(token)
    except Exception as e:
        return '<h1>Bad JSON Web token. You need a valid token.</h1>' + str(e)
    else:
        if token_data.get('email') != email:
            return '<h1>Invalid JSON Web token.</h1>'

        member = CMTESponsorMember.query.filter_by(email=email).first()
        if not member:
            return '<h1>Account not found.</h1>'
        else:
            member.is_valid = True
            db.session.add(member)
            db.session.commit()
            flash('ยืนยัน email เรียบร้อยแล้ว', 'success')
            return redirect(url_for('cmte.sponsor_member_login'))


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
            member.is_valid = False
            serializer = TimedJSONWebSignatureSerializer(current_app.config.get('SECRET_KEY'))
            token = serializer.dumps({'email': form.email.data})
            url = url_for('cmte.validate_email', token=token, email=form.email.data, _external=True)
            if sponsor_id:
                member.sponsor_id = sponsor_id
                db.session.add(member)
                db.session.commit()
                sponsor = CMTEEventSponsor.query.get(sponsor_id)
                if not current_app.debug:
                    message = f'''
                    เรียน ท่านเจ้าของอีเมล
                    
                    บัญชีอีเมลของท่านได้รับการลงทะเบียนเป็นผู้ประสานงานของสถาบันจัดการฝึกอบรมการศึกษาต่อเนื่องเทคนิคการแพทย์ของหน่วยงาน {sponsor.name}
                    \n
                    กรุณาคลิกที่ลิงค์เพื่อยืนยัน {url}
                    \n\n
                    หากไม่ได้ดำเนินการกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                    \n
                    ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                    '''
                    send_mail([member.email], 'MTC-CMTE Email validation', message)
                else:
                    print(member.email)
                flash(f'เพิ่มผู้ประสานงานเรียบร้อยแล้ว', 'success')
                return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
            else:
                db.session.add(member)
                db.session.commit()
                if not current_app.debug:
                    message = f'''
                    เรียน ท่านเจ้าของอีเมล
    
                    บัญชีอีเมลของท่านได้รับการลงทะเบียนเป็นผู้ประสานงานหลักของสถาบันจัดการฝึกอบรมการศึกษาต่อเนื่องเทคนิคการแพทย์
                    \n
                    กรุณาคลิกที่ลิงค์เพื่อยืนยัน {url}
                    \n\n
                    หากไม่ได้ดำเนินการกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                    \n
                    ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                    '''
                    send_mail([member.email], 'MTC-CMTE Email validation', message)
                else:
                    print(member.email)
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

    url = url_for('cmte.manage_sponsor', sponsor_id=sponsor_id, _external=True)
    topic_name = member.sponsor.name[:30]+'...' if len(member.sponsor.name) > 30 else member.sponsor.name
    topic = 'MTC-CMTE คำขอเปลี่ยนผู้ประสานงานหลักจาก '+topic_name
    message = f'''
                 เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                 สถาบัน {member.sponsor.name} ส่งคำขอเปลี่ยนผู้ประสานงานหลัก
                 \n
                 สามารถดูรายละเอียดได้ที่ {url}
                 \n\n
                 ระบบ MTC-CMTE
                 '''
    if not current_app.debug:
        send_mail(['cmtethailand@gmail.com'], topic, message)
    else:
        print(topic, message)
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
                sponsor.has_med_tech = form.has_med_tech.data == 'True'
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
                        type='new',
                        member=current_user
                    )
                    db.session.add(create_request)
                    db.session.commit()
                    flash(f'ลงทะเบียนเรียบร้อย', 'success')

                    url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
                    topic_name = member.sponsor.name[:30] + '...' if len(member.sponsor.name) > 30 else member.sponsor.name
                    topic = 'MTC-CMTE คำขอขึ้นทะเบียนสถาบันจาก ' + topic_name
                    message = f'''
                                     เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                                     สถาบัน {member.sponsor.name} ส่งคำขอขึ้นทะเบียนสถาบัน
                                     \n
                                     สามารถดูรายละเอียดได้ที่ {url}
                                     \n\n
                                     ระบบ MTC-CMTE
                                     '''
                    if not current_app.debug:
                        send_mail(['cmtethailand@gmail.com'], topic, message)
                    else:
                        print(message)
                    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor.id))
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
    detail = 'โปรดระบุ'
    if sponsor_id:
        sponsor = CMTEEventSponsor.query.get(sponsor_id)
        if sponsor.type_detail:
            type_detail = f'''{detail}<textarea name="type_detail" class="textarea" rows="1">{sponsor.type_detail}</textarea>'''
        elif org_type == 'หน่วยงานอื่นๆ':
            type_detail = f'''{detail}<textarea name="type_detail" class="textarea" rows="1"></textarea>'''
        else:
            type_detail = ''
    else:
        if org_type == 'หน่วยงานอื่นๆ':
            type_detail = f'''{detail}<textarea name="type_detail" class="textarea" rows="1"></textarea>'''
        else:
            type_detail = ''
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
            sponsor.has_med_tech = form.has_med_tech.data == 'True'
            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            for field, _file in request.files.items():
                filename = _file.filename
                if filename:
                    key = uuid.uuid4()
                    s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                    doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename)
                    doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                    doc.note = request.form.get(field + '_note')
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

            url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
            topic_name = sponsor.name[:30] + '...' if len(sponsor.name) > 30 else sponsor.name
            topic = 'MTC-CMTE คำขอแก้ไขข้อมูลสถาบันจาก ' + topic_name
            message = f'''
                         เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                         สถาบัน {sponsor.name} ส่งคำขอแก้ไขแก้ไขมูล
                         \n
                         สามารถดูรายละเอียดได้ที่ {url}
                         \n\n
                         ระบบ MTC-CMTE
                         '''
            if not current_app.debug:
                send_mail(['cmtethailand@gmail.com'], topic, message)
            else:
                print(message)
            flash(f'ส่งขอแก้ไขข้อมูลเรียบร้อย', 'success')
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
    form.address.data = f"{sponsor.address} {sponsor.zipcode}"
    form.shipping_address.data = f"{sponsor.address} {sponsor.zipcode}"
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
                flash('แนบ slip ชำระค่าธรรมเนียมเรียบร้อยแล้ว', 'success')
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
                shipping_address=form.shipping_address.data
            )
            db.session.add(create_receipt)
            db.session.commit()

            url = url_for('cmte.manage_sponsor', sponsor_id=sponsor_id, _external=True)
            topic_name = sponsor.name[:30] + '...' if len(sponsor.name) > 30 else sponsor.name
            topic = 'MTC-CMTE หลักฐานการชำระเงินจาก ' + topic_name
            message = f'''
                             เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                             สถาบัน {sponsor.name} แนบหลักฐานการชำระเงินแล้ว
                             \n
                             สามารถดูรายละเอียดได้ที่ {url}
                             \n\n
                             ระบบ MTC-CMTE
                             '''
            if not current_app.debug:
                send_mail(['cmtethailand@gmail.com'], topic, message)
            else:
                print(message)
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_payment_form.html', sponsor=sponsor, form=form)


@cmte.route('/sponsors/<int:sponsor_id>/renew', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def request_renew_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    is_request = CMTESponsorRequest.query.filter_by(sponsor_id=sponsor_id, type='renew',paid_at=None).first()
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

        url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
        topic_name = sponsor.name[:30] + '...' if len(sponsor.name) > 30 else sponsor.name
        topic = 'MTC-CMTE คำขอต่ออายุสถาบันจาก ' + topic_name
        message = f'''
                     เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                     สถาบัน {sponsor.name} ส่งคำขอต่ออายุสถาบัน
                     \n
                     สามารถดูรายละเอียดได้ที่ {url}
                     \n\n
                     ระบบ MTC-CMTE
                     '''
        if not current_app.debug:
            send_mail(['cmtethailand@gmail.com'], topic, message)
        else:
            print(message)
    else:
        flash('มีการส่งคำขอต่ออายุสถาบันแล้ว', 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))


@cmte.route('/sponsors/modal/<int:sponsor_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def sponsor_modal(sponsor_id):
    # delete this function
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

    mails = []
    all_members = CMTESponsorMember.query.filter_by(sponsor=renew_request.sponsor).all()
    for member in all_members:
        mails.append(member.email)

    url = url_for('cmte.manage_sponsor', sponsor_id=renew_request.sponsor.id, _external=True)

    if renew_request.type == 'new':
        message = f'''
                            เรียน ผู้ประสานงาน 

                            คำขอขึ้นทะเบียนสถาบันฝึกอบรมการศึกษาต่อเนื่องของ {renew_request.sponsor.name} ผ่านการอนุมัติแล้ว กรุณาดำเนินการชำระค่าธรรมเนียม
                            \n
                            และกรุณาดำเนินการแนบ slip ที่ {url}
                            \n\n
                            หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                            \n
                            ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                            '''
        topic = 'MTC-CMTE อนุมัติการขึ้นทะเบียนสถาบัน กรุณาชำระค่าธรรมเนียม'

        flash('อนุมัติคำขอขึ้นทะเบียนสถาบันแล้ว', 'success')
    elif renew_request.type == 'renew':
        message = f'''
                            เรียน ผู้ประสานงาน 

                            คำขอต่ออายุสถาบันฝึกอบรมการศึกษาต่อเนื่องของ {renew_request.sponsor.name} ผ่านการอนุมัติแล้ว กรุณาดำเนินการชำระค่าธรรมเนียม
                            \n
                            และกรุณาดำเนินการแนบ slip ที่ {url}
                            \n\n
                            หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                            \n
                            ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                            '''
        topic = 'MTC-CMTE อนุมัติการต่อทะเบียนสถาบัน กรุณาชำระค่าธรรมเนียม'

        flash('อนุมัติคำขอต่ออายุสถาบันแล้ว', 'success')
    else:
        flash('เกิดข้อผิดพลาดจากระบบ ไม่สามารถดำเนินการส่งอีเมลไปยังสถาบันได้', 'danger')

    if not current_app.debug:
        if message:
            if mails:
                send_mail(mails, topic, message)
            else:
                flash('เกิดข้อผิดพลาด ไม่สามารถส่งอีเมลไปยังสถาบันได้', 'danger')
    else:
        print(mails, message)
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=renew_request.sponsor_id))


@cmte.route('/sponsors/<int:sponsor_id>/edit', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def edit_sponsor(sponsor_id):
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
                if filename:
                    key = uuid.uuid4()
                    s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                    doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename)
                    doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                    doc.note = request.form.get(field + '_note')
                    db.session.add(doc)
            sponsor.has_med_tech = form.has_med_tech.data == 'True'
            db.session.commit()
            flash(f'แก้ไขข้อมูลเรียบร้อย', 'success')
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Errors: {form.errors}', 'danger')
    return render_template('cmte/admin/edit_sponsor_info.html', form=form, sponsor=sponsor)


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
    edit_request.sponsor.updated_at = arrow.now('Asia/Bangkok').datetime
    db.session.add(edit_request)

    if status == 'reject':
        current_version_index = edit_request.version_index
        current_version = edit_request.sponsor.versions[current_version_index]
        current_version.revert()
        db.session.commit()
        topic = 'MTC-CMTE สถานะการขอแก้ไขข้อมูลสถาบัน:ไม่อนุมัติการแก้ไข'
        # if previous_version:
        #     for column in edit_request.sponsor.__table__.columns:
        #         field_name = column.name
        #         if hasattr(previous_version, field_name):
        #             setattr(edit_request.sponsor, field_name, getattr(previous_version, field_name))
    elif status == 'approved':
        topic = 'MTC-CMTE สถานะการขอแก้ไขข้อมูลสถาบัน:อนุมัติการแก้ไข'
    db.session.commit()
    flash('บันทึกข้อมูลเรียบร้อยแล้ว สถาบันได้รับการแจ้งเตือนแล้ว',
          'warning')

    mails = []
    all_members = CMTESponsorMember.query.filter_by(sponsor=edit_request.sponsor).all()
    for member in all_members:
        mails.append(member.email)
    url = url_for('cmte.manage_sponsor', sponsor_id=edit_request.sponsor.id, _external=True)
    message = f'''
                    เรียน ผู้ประสานงาน 

                    คำขอแก้ไขข้อมูลสถาบัน {edit_request.sponsor.name} ถูกอัพเดทสถานะแล้ว 
                    \n
                    สามารถตรวจสอบรายละเอียดได้ที่ {url}
                    \n\n
                    หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                    \n
                    ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                    '''
    if not current_app.debug:
        send_mail(mails, topic, message)
    else:
        print(mails, message)
    return redirect(url_for('cmte.manage_edit_sponsor', request_id=request_id))


@cmte.route('/sponsors/additional-request-modal/<int:sponsor_id>/<int:request_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def sponsor_additional_request_modal(sponsor_id, request_id):
    sponsor_request = CMTESponsorRequest.query.get(request_id)
    form = CMTESponsorAdditionalRequestForm(obj=sponsor_request)
    return render_template('cmte/admin/sponsor_additional_request_modal.html', form=form,
                           request_id=request_id, sponsor_id=sponsor_id)


@cmte.route('/sponsors/additional-request-modal/<int:sponsor_id>/<int:request_id>/submit', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def additional_request_sponsor(sponsor_id, request_id):
    sponsor_request = CMTESponsorRequest.query.get(request_id)
    form = CMTESponsorRequestForm(obj=sponsor_request)
    if form.validate_on_submit():
        sponsor_request.comment = request.form.get('comment')
        db.session.add(sponsor_request)
        db.session.commit()
        sponsor = CMTEEventSponsor.query.get(sponsor_id)

        member = CMTESponsorMember.query.filter_by(sponsor_id=sponsor_id).first()
        url = url_for('cmte.manage_sponsor', sponsor_id=sponsor_id, _external=True)
        message = f'''
                      เรียน ท่านเจ้าของอีเมล

                      คำขอของหน่วยงาน {sponsor.name} มีการขอเอกสารเพิ่มเติมเพื่อประกอบการอนุมัติ
                      \n
                      กรุณาคลิกที่ลิงค์เพื่อดำเนินการต่อ {url}
                  '''
        if not current_app.debug:
            send_mail([member.email], 'MTC-CMTE Additional Request', message)
        else:
            print(url, sponsor.name ,member.email, message)
        flash('ส่งขอข้อมูลเอกสารเพิ่มเติม ไปยังสถาบันเรียบร้อยแล้ว', 'success')
        return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
    else:
        for er in form.errors:
            flash("{}:{}".format(er, form.errors[er]), 'danger')
    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp


@cmte.route('/sponsors/additional-request/<int:sponsor_id>/<int:request_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def sponsor_send_additional_info(sponsor_id, request_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    form = CMTEEventSponsorForm(obj=sponsor)
    if request.method == 'POST':
        if form.validate_on_submit():

            s3_client = boto3.client('s3', aws_access_key_id=os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID'),
                                     aws_secret_access_key=os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY'),
                                     region_name=os.environ.get('BUCKETEER_AWS_REGION'))
            for field, _file in request.files.items():
                filename = _file.filename
                if filename:
                    key = uuid.uuid4()
                    s3_client.upload_fileobj(_file, os.environ.get('BUCKETEER_BUCKET_NAME'), str(key))
                    doc = CMTESponsorDoc(sponsor=sponsor, key=key, filename=filename)
                    doc.upload_datetime = arrow.now('Asia/Bangkok').datetime
                    doc.note = request.form.get(field + '_note')
                    db.session.add(doc)

            req = CMTESponsorRequest.query.get(request_id)
            req.updated_at = arrow.now('Asia/Bangkok').datetime
            db.session.add(req)
            db.session.commit()
            flash(f'ส่งข้อมูลเรียบร้อยแล้ว รอเจ้าหน้าที่ตรวจสอบข้อมูล และรอการอนุมัติ', 'success')

            url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
            topic_name = sponsor.name[:30] + '...' if len(sponsor.name) > 30 else sponsor.name
            topic = 'MTC-CMTE เอกสารเพิ่มเติมจาก ' + topic_name
            message = f'''
                         เรียน เจ้าหน้าที่สภาเทคนิคการแพทย์

                         สถาบัน {sponsor.name} ดำเนินการแก้ไขเอกสาร เพื่อขอขึ้นทะเบียนเรียบร้อยแล้ว
                         \n
                         สามารถดูรายละเอียดได้ที่ {url}
                         \n\n
                         ระบบ MTC-CMTE
                         '''
            if not current_app.debug:
                send_mail(['cmtethailand@gmail.com'], topic, message)
            else:
                print(message)
            return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))
        else:
            flash(f'Errors: {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_additional_info.html', form=form, sponsor=sponsor)


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

        mails = []
        all_members = CMTESponsorMember.query.filter_by(sponsor=sponsor).all()
        for member in all_members:
            mails.append(member.email)

        url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
        message = f'''
                        เรียน ผู้ประสานงาน 

                        คำขอขึ้นทะเบียนสถาบัน {sponsor.name} ถูกปฏิเสธ
                        \n
                        สามารถตรวจสอบรายละเอียดได้ที่ {url}
                        \n\n
                        หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                        \n
                        ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                        '''
        if not current_app.debug:
            send_mail(mails, 'MTC-CMTE ปฏิเสธการขึ้นทะเบียน', message)
        else:
            print(mails, message)
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
    url = url_for('cmte.manage_sponsor', sponsor_id=sponsor.id, _external=True)
    if sponsor.expire_date:
        old_expire_date = sponsor.expire_date + timedelta(days=1)
        sponsor.registered_datetime = old_expire_date
        expire_date = old_expire_date.replace(year=old_expire_date.year + 5)
        sponsor.expire_date = expire_date - timedelta(days=1)
        topic = 'MTC-CMTE อนุมัติการต่ออายุทะเบียน'
        message = f'''
                        เรียน ผู้ประสานงาน 

                        คำขอต่ออายุทะเบียนสถาบัน {sponsor.name} ผ่านการอนุมัติแล้ว 
                        \n
                        สามารถตรวจสอบวันขึ้นทะเบียนและวันอายุสถาบันได้ที่ {url}
                        \n\n
                        หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                        \n
                        ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                        '''
    else:
        today = arrow.now('Asia/Bangkok').datetime
        sponsor.registered_datetime = today
        expire_date = today.replace(year=today.year + 5)
        sponsor.expire_date = expire_date - timedelta(days=1)
        topic = 'MTC-CMTE อนุมัติการขึ้นทะเบียน'
        message = f'''
                        เรียน ผู้ประสานงาน 

                        คำขอขึ้นทะเบียนสถาบัน {sponsor.name} ผ่านการอนุมัติแล้ว 
                        \n
                        สามารถตรวจสอบวันขึ้นทะเบียนและวันอายุสถาบันได้ที่ {url}
                        \n\n
                        หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
                        \n
                        ▼อีเมลนี้ใช้สำหรับส่งออกเท่านั้น โปรดทราบว่าหากท่านตอบกลับมายังอีเมลนี้ ทางเราจะไม่สามารถตอบกลับได้
                        '''
    db.session.add(sponsor)
    db.session.commit()

    mails = []
    all_members = CMTESponsorMember.query.filter_by(sponsor=sponsor).all()
    for member in all_members:
        mails.append(member.email)
    if not current_app.debug:
        send_mail(mails, topic, message)
    else:
        print(mails, message)
    flash('ตรวจสอบการชำระเงินเรียบร้อยแล้ว สถาบันได้รับการแจ้งเตือนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor.id))


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

    if request.method == 'GET':
        form.start_date.data = arrow.get(event.start_date).to('Asia/Bangkok') if form.start_date.data else None
        form.end_date.data = arrow.get(event.end_date).to('Asia/Bangkok') if form.end_date.data else None
        form.submitted_datetime.data = arrow.get(event.submitted_datetime).to('Asia/Bangkok') if form.submitted_datetime.data else None
        form.approved_datetime.data = arrow.get(event.approved_datetime).to('Asia/Bangkok') if form.approved_datetime.data else None

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
                event.submission_due_date = event.end_date + timedelta(days=30)
            event.start_date = arrow.get(event.start_date, 'Asia/Bangkok').datetime if event.start_date else None
            event.end_date = arrow.get(event.end_date, 'Asia/Bangkok').datetime if event.end_date else None
            event.submitted_datetime = arrow.get(event.submitted_datetime, 'Asia/Bangkok').datetime if event.submitted_datetime else None
            event.approved_datetime = arrow.get(event.approved_datetime, 'Asia/Bangkok').datetime if event.approved_datetime else None
            db.session.add(event)
            db.session.commit()
            flash('บันทึกการแก้ไขกิจกรรมเรียบร้อย', 'success')
            return redirect(url_for('cmte.admin_preview_event', event_id=event.id))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/admin/admin_event_form.html',
                           form=form, event=event, bangkok=bangkok)


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
    status = request.args.get('status', 'pending')
    records = CMTEEventParticipationRecord.query.filter_by(individual=True,
                                                           approved_date=None,
                                                           closed_date=None)
    return render_template('cmte/admin/individual_scores.html',
                           status=status,
                           records=records)


@cmte.route('/events/group-individuals/index')
@login_required
@cmte_admin_permission.require()
def admin_group_individual_score_index():
    status = request.args.get('status', 'pending')
    return render_template('cmte/admin/group_individual_scores.html', status=status)


@cmte.route('/api/events/group-individual-score-records/')
@login_required
@cmte_admin_permission.require()
def admin_get_group_individual_score_records():
    status = request.args.get('status', 'pending')
    search = request.args.get('search[value]')
    col_idx = request.args.get('order[0][column]')
    direction = request.args.get('order[0][dir]')
    col_name = request.args.get('columns[{}][data]'.format(col_idx))
    query = CMTEEventGroupParticipationRecord.query \
        .filter(CMTEEventGroupParticipationRecord.create_datetime!=None) \
        .order_by(CMTEEventGroupParticipationRecord.create_datetime.desc())
    if status == 'pending':
        query = query.filter_by(approved_date=None, closed_date=None)
    elif status == 'approved':
        query = query.filter(CMTEEventGroupParticipationRecord.approved_date != None)
    elif status == 'rejected':
        query = query.filter(CMTEEventGroupParticipationRecord.closed_date != None)
    elif status == 'waiting':
        query = query.filter(CMTEEventGroupParticipationRecord.approved_date == None) \
            .filter(CMTEEventGroupParticipationRecord.closed_date == None) \
            .join(CMTEParticipationRecordRequest) \
            .group_by(CMTEEventGroupParticipationRecord.id) \
            .having(func.count(CMTEEventGroupParticipationRecord.id) > 0)
    records_total = query.count()
    if col_name:
        try:
            column = getattr(CMTEEventGroupParticipationRecord, col_name)
        except AttributeError:
            print(f'{col_name} not found.')
        else:
            if direction == 'desc':
                column = column.desc()
            query = query.order_by(column)

    if search:
        query = query.join(License).join(Member).join(CMTEEventParticipationRecord) \
            .filter(or_(Member.th_firstname.contains(search),
                        Member.th_lastname.contains(search),
                        CMTEEventParticipationRecord.desc.contains(search),
                        License.number.contains(search),
        ))
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    total_filtered = query.count()
    query = query.offset(start).limit(length)
    data = []
    for record in query:
        _dict = record.to_dict()
        _dict['url'] = url_for('cmte.admin_group_individual_score_detail', record_id=record.id)
        data.append(_dict)
    return jsonify({'data': data,
                    'recordsFiltered': total_filtered,
                    'recordsTotal': records_total,
                    'draw': request.args.get('draw', type=int)})


@cmte.route('/api/events/individual-score-records/')
@login_required
@cmte_admin_permission.require()
def admin_get_individual_score_records():
    status = request.args.get('status', 'pending')
    search = request.args.get('search[value]')
    col_idx = request.args.get('order[0][column]')
    direction = request.args.get('order[0][dir]')
    col_name = request.args.get('columns[{}][data]'.format(col_idx))
    query = CMTEEventParticipationRecord.query.filter_by(individual=True)\
        .filter(CMTEEventParticipationRecord.create_datetime!=None)\
        .order_by(CMTEEventParticipationRecord.create_datetime.desc())
    records_total = query.count()

    if status == 'pending':
        query = query.filter(CMTEEventParticipationRecord.approved_date==None) \
            .filter(CMTEEventParticipationRecord.closed_date==None)
    elif status == 'approved':
        query = query.filter(CMTEEventParticipationRecord.approved_date!=None) \
            .order_by(CMTEEventParticipationRecord.approved_date.desc())
    elif status == 'rejected':
        query = query.filter(CMTEEventParticipationRecord.closed_date!=None)
    elif status == 'waiting':
        query = query.filter(CMTEEventParticipationRecord.approved_date==None)\
            .filter(CMTEEventParticipationRecord.closed_date==None)\
            .join(CMTEParticipationRecordRequest)\
            .group_by(CMTEEventParticipationRecord.id)\
            .having(func.count(CMTEEventParticipationRecord.id) > 0)

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
        query = query.join(License).join(Member).filter(or_(
            Member.th_firstname.contains(search),
            Member.th_lastname.contains(search),
            CMTEEventParticipationRecord.desc.contains(search),
            CMTEEventParticipationRecord.license_number.contains(search),

        ))
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    total_filtered = query.count()
    query = query.offset(start).limit(length)
    data = []
    for record in query:
        _dict = record.individual_score_to_dict()
        _dict['url'] = url_for('cmte.admin_individual_score_detail', record_id=record.id)
        if status == 'pending':
            if not record.info_requests:
                data.append(_dict)
        else:
            data.append(_dict)
    return jsonify({'data': data,
                    'recordsFiltered': total_filtered,
                    'recordsTotal': records_total,
                    'draw': request.args.get('draw', type=int)})


@cmte.route('/events/individuals/<int:record_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_individual_score_detail(record_id):
    record = CMTEEventParticipationRecord.query.get(record_id)
    form = IndividualScoreAdminForm(obj=record)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'approve':
            if form.score.data and form.score.data > 0.0:
                form.populate_obj(record)
                record.approved_date = arrow.now('Asia/Bangkok').date()
                record.closed_date = None
                record.set_score_valid_date()
                for req in record.info_requests:
                    req.closed_at = arrow.now('Asia/Bangkok').datetime
                    db.session.add(req)
                db.session.add(record)
                db.session.commit()
                flash('อนุมัติคะแนนเรียบร้อย', 'success')
                return redirect(url_for('cmte.admin_individual_score_index'))
            else:
                flash('กรุณาตรวจสอบคะแนนอีกครั้ง', 'warning')
        elif action == 'info_request':
            info_request = CMTEParticipationRecordRequest(detail=request.form.get('detail'),
                                                          record=record)
            info_request.created_at = arrow.now('Asia/Bangkok').date()
            info_request.requester = current_user
            db.session.add(info_request)
            db.session.commit()
            if not current_app.debug:
                message = f'''
                เรียน สมาชิกสภาเทคนิคการแพทย์
                
                กรุณาตรวจสอบคำขอรายละเอียดเพิ่มเติมเพื่อการอนุมัติคะแนนส่วนบุคคลในระบบสารสนเทศสมาชิก

                \n\n
                อีเมลนี้เป็นระบบอัตโนมัติกรุณาอย่าตอบกลับ
                '''
                send_mail([record.license.member.email], 'MTC-CMTE Email validation', message)
            else:
                print(f'Sending an email to {record.license.member.email}')
            flash('ส่งคำขอเรียบร้อยแล้ว', 'success')
            return redirect(url_for('cmte.admin_individual_score_index'))
        else:
            form.populate_obj(record)
            record.closed_date = arrow.now('Asia/Bangkok').date()
            record.approved_date = None
            db.session.add(record)
            db.session.commit()
            flash('บันทึกข้อมูลเรียบร้อย', 'success')
            return redirect(url_for('cmte.admin_individual_score_index'))
    return render_template('cmte/admin/individual_score_detail.html', record=record, form=form)


@cmte.route('/events/group-individuals/<int:record_id>', methods=['GET', 'POST', 'DELETE'])
@login_required
@cmte_admin_permission.require()
def admin_group_individual_score_detail(record_id):
    group_record = CMTEEventGroupParticipationRecord.query.get(record_id)
    form = IndividualScoreGroupForm(obj=group_record)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'approve':
            score = request.form.get('score', type=float)
            for record in group_record.records:
                record.score = score
                record.set_score_valid_date()
                record.approved_date = arrow.now('Asia/Bangkok').date()
                db.session.add(record)
                group_record.approved_date = arrow.now('Asia/Bangkok').date()
            db.session.add(group_record)
            db.session.commit()
            flash(f'อนุมัติคะแนนเรียบร้อยแล้ว', 'success')
            return redirect(url_for('cmte.admin_group_individual_score_index'))
        elif action == 'info_request':
            _request = CMTEParticipationRecordRequest(group_record=group_record)
            _request.created_at = arrow.now('Asia/Bangkok').datetime
            _request.requester = current_user
            _request.detail = request.form.get('detail')
            db.session.add(_request)
            db.session.commit()
            flash(f'ส่งคำขอข้อมูลเพิ่มเติมเรียบร้อยแล้ว', 'success')
            return redirect(url_for('cmte.admin_group_individual_score_index'))

    return render_template('cmte/admin/group_individual_score_detail.html',
                           group_record=group_record, form=form)


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
        else:
            flash(f'{form.errors}', 'danger')
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
    resp = make_response(template)
    resp.headers['HX-Refresh'] = 'true'
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


@login_required
@cmte_admin_permission.require()
@cmte.route('/admin/sponsors/members')
def admin_list_sponsor_members():
    members = CMTESponsorMember.query.all()
    return render_template('cmte/admin/sponsor_members.html', members=members)


@login_required
@cmte_admin_permission.require()
@cmte.route('/admin/sponsors/members/<int:member_id>/edit', methods=['GET', 'POST'])
def admin_edit_sponsor_member(member_id):
    member = CMTESponsorMember.query.get(member_id)
    form = CMTEAdminSponsorMemberForm(obj=member)
    if form.validate_on_submit():
        email = form.email.data
        _member = CMTESponsorMember.query.filter_by(email=email).first()
        if _member and _member.id == member.id:
            flash(f'Email นี้มีการลงทะเบียนใช้งานแล้ว', 'danger')
            return render_template('cmte/admin/sponsor_member_form.html', form=form)
        form.populate_obj(member)
        db.session.add(member)
        db.session.commit()
        flash(f'แก้ไขข้อมูลผู้ประสานงานแล้ว', 'success')
        return redirect(url_for('cmte.admin_list_sponsor_members'))
    else:
        if form.errors:
            flash(f'{form.errors}', 'danger')
    return render_template('cmte/admin/sponsor_member_form.html', form=form)


@login_required
@cmte_admin_permission.require()
@cmte.route('/admin/sponsors/members/<int:member_id>/send-verification', methods=['GET', 'POST'])
def admin_send_email_verification(member_id):
    member = CMTESponsorMember.query.get(member_id)
    serializer = TimedJSONWebSignatureSerializer(current_app.config.get('SECRET_KEY'))
    token = serializer.dumps({'email': member.email})
    url = url_for('cmte.validate_email', token=token, email=member.email, _external=True)
    message = f'''
    เรียน ท่านเจ้าของอีเมล

    บัญชีอีเมลของท่านได้รับการลงทะเบียนเป็นผู้ประสานงานของสถาบันจัดการฝึกอบรมการศึกษาต่อเนื่องเทคนิคการแพทย์
    \n
    กรุณาคลิกที่ลิงค์เพื่อยืนยัน {url}
    \n\n
    หากไม่ได้ดำเนินการกรุณาติดต่อเจ้าหน้าที่สภาเทคนิคการแพทย์
    '''
    send_mail([member.email], 'MTC-CMTE Email validation', message)
    resp = make_response()
    return resp


@login_required
@cmte_admin_permission.union(cmte_sponsor_admin_permission).require()
@cmte.route('/sponsors/<int:sponsor_id>/members/add', methods=['GET', 'POST'])
def add_sponsor_members(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    if request.method == 'POST':
        members = request.form.getlist('sponsor_members')
        for member_id in members:
            member = CMTESponsorMember.query.get(member_id)
            req = CMTESponsorMemberAddRequest(to_sponsor_id=int(sponsor_id),
                                              member=member,
                                              requested_at=arrow.now('Asia/Bangkok').datetime,
                                              )
            db.session.add(req)
            db.session.commit()
            if not current_app.debug:
                message = f'''
                เรียน ท่านเจ้าของอีเมล
                \n
                กรุณาเข้าสู่ระบบสารสนเทศของสภาเทคนิคการแพทย์และดำเนินการเพื่อยืนยันการเข้าร่วมเป็นผู้ประสานงานของ {member.sponsor}
                '''
                send_mail([member.email], 'MTC-CMTE แจ้งการขอเพิ่มชื่อผู้ประสานงาน', message)
        flash(f'ดำเนินการแจ้งเจ้าของบัญชีเรียบร้อยแล้ว', 'success')
        return redirect(url_for('cmte.manage_sponsor', sponsor_id=sponsor_id))

    return render_template('cmte/sponsor/add_sponsor_member.html', sponsor=sponsor)


@login_required
@cmte_admin_permission.union(cmte_sponsor_admin_permission).require()
@cmte.route('/sponsors/members/add/<int:req_id>/confirm', methods=['DELETE', 'POST'])
def confirm_add_sponsor_members(req_id):
    req = CMTESponsorMemberAddRequest.query.get(req_id)
    if request.method == 'POST':
        req.accepted_at = arrow.now('Asia/Bangkok').datetime
        req.member.sponsor = req.to_sponsor
        db.session.add(req)
        db.session.commit()
        flash(f'ดำเนินการเรียบร้อย', 'success')
    if request.method == 'DELETE':
        req.cancelled_at = arrow.now('Asia/Bangkok').datetime
        db.session.add(req)
        db.session.commit()
        flash(f'ยกเลิกการดำเนินการเรียบร้อย', 'success')

    resp = make_response()
    resp.headers['HX-Refresh'] = 'true'
    return resp


@login_required
@cmte_admin_permission.union(cmte_sponsor_admin_permission).require()
@cmte.route('/api/sponsors/members/')
def get_sponsor_members():
    search_term = request.args.get('term', '')
    results = []
    for member in CMTESponsorMember.query:
        if search_term in str(member) or search_term in (member.email if member.email else ''):
            index_ = member.id
            results.append({
                "id": index_,
                "text": f'{str(member)}, {member.email}'
            })
    return jsonify({'results': results})


@cmte_admin_permission.require()
@login_required
@cmte.route('/admin/members/scores/')
def admin_search_members():
    return render_template('cmte/admin/member_cmte_scores.html')


@cmte_admin_permission.require()
@login_required
@cmte.route('/admin/members/<int:member_id>/scores/')
def admin_check_member_cmte_scores(member_id):
    member = Member.query.get(member_id)
    records = CMTEEventParticipationRecord.query.filter_by(license_number=member.license.number)\
        .filter(CMTEEventParticipationRecord.score.isnot(None))\
        .order_by(CMTEEventParticipationRecord.approved_date.desc())
    return render_template('cmte/admin/member_cmte_score_records.html',
                           records=records, member=member)


@cmte_admin_permission.require()
@login_required
@cmte.route('/admin/members/scores/<int:record_id>', methods=['POST', 'GET'])
def admin_update_cmte_score_valid_date(record_id):
    record = CMTEEventParticipationRecord.query.get(record_id)
    if request.headers.get('HX-Request') == 'true':
        record.set_score_valid_date()
        db.session.add(record)
        db.session.commit()
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp
    form = AdminParticipantRecordForm(obj=record)
    if request.method == 'GET':
        return render_template('cmte/admin/edit_participant_record_form.html',
                               form=form, record=record)
    if request.method == 'POST':
        if form.validate_on_submit():
            form.populate_obj(record)
            db.session.add(record)
            db.session.commit()
        else:
            flash(f'{form.errors}', 'danger')
        return redirect(url_for('cmte.admin_check_member_cmte_scores', member_id=record.license.member_id))


@cmte_admin_permission.require()
@login_required
@cmte.route('/admin/members/scores/<int:record_id>/delete', methods=['DELETE'])
def admin_delete_cmte_score_record(record_id):
    record = CMTEEventParticipationRecord.query.get(record_id)
    db.session.delete(record)
    db.session.commit()
    resp = make_response()
    return resp


@cmte.route('/members/events')
@login_required
def list_event_types():
    event_types = CMTEEventType.query.filter_by(deprecated=False).order_by(CMTEEventType.number)
    return render_template('cmte/event_list.html', event_types=event_types)


# @cmte.route('/report/sponsors', methods=['GET', 'POST'])
# @login_required
# @cmte_admin_permission.require()
# def report_sponsors():
#     today = datetime.now().date()
#     start_of_year = datetime(today.year, 1, 1).date()
#     all_sponsor = CMTEEventSponsor.query.filter(CMTEEventSponsor.expire_date >= today).count()
#     sponsors = CMTEEventSponsor.query.filter(
#         func.date(CMTEEventSponsor.registered_datetime) <= today,
#         CMTEEventSponsor.expire_date >= start_of_year
#     ).count()
#     expire_sponsor = db.session.query(CMTEEventSponsor).filter(
#         CMTEEventSponsor.expire_date.between(today, today + timedelta(days=90))
#     )
#     fifth_expire_sponsor = expire_sponsor.order_by(CMTEEventSponsor.expire_date).limit(5).all()
#     expire_count = expire_sponsor.count()
#
#     # sponsor_requests = (
#     #     CMTESponsorRequest.query.filter(
#     #         CMTESponsorRequest.approved_at != None,
#     #         CMTESponsorRequest.cancelled_at == None,
#     #         CMTESponsorRequest.type != 'change')
#     #     .distinct(CMTESponsorRequest.sponsor_id)
#     #     .all()
#     # )
#     # sponsor_requests_count = len(sponsor_requests)
#
#     selected_dates = None
#     if request.method == 'POST':
#         form = request.form
#         selected_dates = request.form.get('dates', None)
#         start_d, end_d = form.get('dates').split(' - ')
#         start = datetime.strptime(start_d, '%d/%m/%Y')
#         end = datetime.strptime(end_d, '%d/%m/%Y')
#         query = CMTEEventSponsor.query
#         if start:
#             query = query.filter(
#                 and_(
#                     func.date(CMTEEventSponsor.registered_datetime) >= start.date(),
#                     CMTEEventSponsor.expire_date >= end.date()
#                 )
#             )
#         sponsors = query.count()
#         expire_count = query.filter(
#             CMTEEventSponsor.expire_date.between(end, end+ timedelta(days=90))
#         ).count()
#         # sponsor_requests = (
#         #     CMTESponsorRequest.query.filter(
#         #         CMTESponsorRequest.approved_at != None,
#         #         CMTESponsorRequest.cancelled_at == None,
#         #         CMTESponsorRequest.type != 'change')
#         #     .filter(CMTESponsorRequest.approved_at.between(start, end))
#         #     .distinct(CMTESponsorRequest.sponsor_id)
#         #     .all()
#         # )
#         # sponsor_requests_count = len(sponsor_requests)
#
#
#     return render_template('cmte/admin/report_sponsors_index.html', all_sponsor=all_sponsor
#                            ,sponsors=sponsors, expire_count=expire_count,
#                            selected_dates=selected_dates, fifth_expire_sponsor=fifth_expire_sponsor)


@cmte.route('/report/sponsors', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def report_sponsors_index():
    _, _, selected_dates, selected_type = _get_sponsor_dashboard_filters(request.args)
    sponsor_types = [row[0] for row in db.session.query(CMTEEventSponsor.type)
                     .filter(CMTEEventSponsor.type != None)
                     .distinct()
                     .order_by(CMTEEventSponsor.type)
                     .all()]
    assumptions = [
        'สถิติภาพรวมอ้างอิงตามสถาบันที่อยู่ในระบบทั้งหมด โดยสามารถกรองตามช่วงวันที่ขึ้นทะเบียนและประเภทองค์กรได้',
        'จำนวนสถาบันใหม่อ้างอิงจากคำขอขึ้นทะเบียนหรือต่ออายุที่อนุมัติแล้วและไม่ถูกยกเลิกภายในช่วงวันที่เลือก',
        'จำนวนสถาบันที่จะหมดอายุคำนวณจากวันหมดอายุที่อยู่ภายใน 90 วันนับจากวันสิ้นสุดของช่วงวันที่เลือก',
        'ตารางสรุปแสดงจำนวนผู้ประสานงานและกิจกรรมที่อนุมัติแล้วต่อสถาบัน โดยใช้การแบ่งหน้าแบบ AJAX',
    ]
    return render_template('cmte/admin/report_sponsors_index.html',
                           selected_dates=selected_dates,
                           selected_type=selected_type,
                           sponsor_types=sponsor_types,
                           assumptions=assumptions)


def _get_sponsor_dashboard_filters(source_args):
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    dates_value = source_args.get('dates')
    if dates_value:
        start_d, end_d = dates_value.split(' - ')
        start_date = datetime.strptime(start_d, '%d/%m/%Y').date()
        end_date = datetime.strptime(end_d, '%d/%m/%Y').date()
    else:
        start_date = default_start
        end_date = today
        dates_value = f'{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}'
    selected_type = source_args.get('sponsor_type', '')
    return start_date, end_date, dates_value, selected_type


def _get_sponsor_dashboard_base_query(start_date, end_date, selected_type=''):
    query = db.session.query(
        CMTEEventSponsor.id.label('sponsor_id'),
        CMTEEventSponsor.name.label('sponsor_name'),
        CMTEEventSponsor.type.label('sponsor_type'),
        CMTEEventSponsor.affiliation.label('affiliation'),
        CMTEEventSponsor.registered_datetime.label('registered_datetime'),
        CMTEEventSponsor.expire_date.label('expire_date'),
    )

    query = query.filter(
        or_(CMTEEventSponsor.registered_datetime == None,
            func.date(CMTEEventSponsor.registered_datetime) >= start_date)
    ).filter(
        or_(CMTEEventSponsor.registered_datetime == None,
            func.date(CMTEEventSponsor.registered_datetime) <= end_date)
    )

    if selected_type:
        query = query.filter(CMTEEventSponsor.type == selected_type)

    return query.subquery()


@cmte.get('/report/sponsors/summary')
@login_required
@cmte_admin_permission.require()
def report_sponsors_summary():
    start_date, end_date, _, selected_type = _get_sponsor_dashboard_filters(request.args)
    sponsor_base = _get_sponsor_dashboard_base_query(start_date, end_date, selected_type)
    cutoff_date = end_date + timedelta(days=90)

    active_case = case(
        (and_(sponsor_base.c.expire_date != None, sponsor_base.c.expire_date >= end_date), 1),
        else_=0
    )
    expiring_case = case(
        (and_(sponsor_base.c.expire_date != None,
              sponsor_base.c.expire_date >= end_date,
              sponsor_base.c.expire_date <= cutoff_date), 1),
        else_=0
    )

    kpi_row = db.session.query(
        func.count(sponsor_base.c.sponsor_id).label('total_sponsors'),
        func.coalesce(func.sum(active_case), 0).label('active_sponsors'),
        func.coalesce(func.sum(expiring_case), 0).label('expiring_soon'),
    ).one()

    new_sponsors_count = (
        db.session.query(func.count(func.distinct(CMTESponsorRequest.sponsor_id)))
        .join(CMTEEventSponsor, CMTEEventSponsor.id == CMTESponsorRequest.sponsor_id)
        .filter(CMTESponsorRequest.approved_at != None,
                CMTESponsorRequest.cancelled_at == None,
                CMTESponsorRequest.type != 'change')
        .filter(func.date(CMTESponsorRequest.approved_at) >= start_date,
                func.date(CMTESponsorRequest.approved_at) <= end_date)
    )
    if selected_type:
        new_sponsors_count = new_sponsors_count.filter(CMTEEventSponsor.type == selected_type)
    new_sponsors_count = new_sponsors_count.scalar() or 0

    monthly_rows = db.session.query(
        func.extract('year', sponsor_base.c.registered_datetime).label('year'),
        func.extract('month', sponsor_base.c.registered_datetime).label('month'),
        func.count(sponsor_base.c.sponsor_id).label('registered_count'),
    ).filter(sponsor_base.c.registered_datetime != None)\
        .group_by(func.extract('year', sponsor_base.c.registered_datetime),
                  func.extract('month', sponsor_base.c.registered_datetime))\
        .order_by(func.extract('year', sponsor_base.c.registered_datetime),
                  func.extract('month', sponsor_base.c.registered_datetime)).all()

    sponsor_type_label = func.coalesce(sponsor_base.c.sponsor_type, 'ไม่ระบุประเภท')
    type_count = func.count(sponsor_base.c.sponsor_id)
    type_rows = db.session.query(
        sponsor_type_label.label('label'),
        type_count.label('count'),
    ).group_by(sponsor_type_label)\
        .order_by(type_count.desc(), sponsor_type_label.asc())\
        .limit(8).all()

    status_label = case(
        (sponsor_base.c.expire_date == None, 'ยังไม่ระบุวันหมดอายุ'),
        (sponsor_base.c.expire_date < end_date, 'หมดอายุแล้ว'),
        (sponsor_base.c.expire_date <= cutoff_date, 'ใกล้หมดอายุภายใน 90 วัน'),
        else_='ใช้งานอยู่'
    )
    status_count = func.count(sponsor_base.c.sponsor_id)
    status_rows = db.session.query(
        status_label.label('status_label'),
        status_count.label('count'),
    ).group_by(status_label).order_by(status_count.desc()).all()

    registered_rows = []
    for row in monthly_rows:
        year = int(row.year)
        month = int(row.month)
        registered_rows.append([f'{calendar.month_abbr[month]} {year}', int(row.registered_count or 0)])

    type_chart_rows = [[row.label, int(row.count or 0)] for row in type_rows]
    status_chart_rows = [[row.status_label, int(row.count or 0)] for row in status_rows]

    return jsonify({
        'kpi': {
            'total_sponsors': int(kpi_row.total_sponsors or 0),
            'active_sponsors': int(kpi_row.active_sponsors or 0),
            'new_sponsors': int(new_sponsors_count),
            'expiring_soon': int(kpi_row.expiring_soon or 0),
        },
        'registered_rows': registered_rows,
        'type_chart_rows': type_chart_rows,
        'status_chart_rows': status_chart_rows,
    })


@cmte.get('/report/sponsors/breakdown')
@login_required
@cmte_admin_permission.require()
def report_sponsors_breakdown():
    start_date, end_date, _, selected_type = _get_sponsor_dashboard_filters(request.args)
    search = request.args.get('search[value]', '')
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=10)
    draw = request.args.get('draw', type=int)

    sponsor_base = _get_sponsor_dashboard_base_query(start_date, end_date, selected_type)

    member_counts = db.session.query(
        CMTESponsorMember.sponsor_id.label('sponsor_id'),
        func.count(CMTESponsorMember.id).label('member_count'),
    ).group_by(CMTESponsorMember.sponsor_id).subquery()

    event_counts = db.session.query(
        CMTEEvent.sponsor_id.label('sponsor_id'),
        func.count(CMTEEvent.id).label('approved_event_count'),
    ).filter(CMTEEvent.approved_datetime != None,
             CMTEEvent.cancelled_datetime == None)\
        .group_by(CMTEEvent.sponsor_id).subquery()

    query = db.session.query(
        sponsor_base.c.sponsor_id,
        sponsor_base.c.sponsor_name,
        sponsor_base.c.sponsor_type,
        sponsor_base.c.affiliation,
        sponsor_base.c.registered_datetime,
        sponsor_base.c.expire_date,
        func.coalesce(member_counts.c.member_count, 0).label('member_count'),
        func.coalesce(event_counts.c.approved_event_count, 0).label('approved_event_count'),
    ).outerjoin(member_counts, member_counts.c.sponsor_id == sponsor_base.c.sponsor_id)\
     .outerjoin(event_counts, event_counts.c.sponsor_id == sponsor_base.c.sponsor_id)

    if search:
        query = query.filter(or_(
            sponsor_base.c.sponsor_name.ilike(f'%{search}%'),
            sponsor_base.c.sponsor_type.ilike(f'%{search}%'),
            sponsor_base.c.affiliation.ilike(f'%{search}%'),
        ))

    records_filtered = query.count()
    records_total = db.session.query(func.count()).select_from(sponsor_base).scalar()

    orderable_columns = {
        0: sponsor_base.c.sponsor_name,
        1: sponsor_base.c.sponsor_type,
        2: sponsor_base.c.registered_datetime,
        3: sponsor_base.c.expire_date,
        4: member_counts.c.member_count,
        5: event_counts.c.approved_event_count,
    }
    col_idx = request.args.get('order[0][column]', type=int)
    direction = request.args.get('order[0][dir]', default='asc')
    if col_idx in orderable_columns:
        order_column = orderable_columns[col_idx]
        query = query.order_by(order_column.desc() if direction == 'desc' else order_column.asc())
    else:
        query = query.order_by(sponsor_base.c.sponsor_name.asc())

    rows = query.offset(start).limit(length).all()
    data = [{
        'name': row.sponsor_name,
        'type': row.sponsor_type or '-',
        'affiliation': row.affiliation or '-',
        'registered_datetime': row.registered_datetime.isoformat() if row.registered_datetime else None,
        'expire_date': row.expire_date.isoformat() if row.expire_date else None,
        'member_count': int(row.member_count or 0),
        'approved_event_count': int(row.approved_event_count or 0),
        'status': ('ยังไม่ระบุวันหมดอายุ' if row.expire_date is None else
                   'หมดอายุแล้ว' if row.expire_date < end_date else
                   'ใกล้หมดอายุภายใน 90 วัน' if row.expire_date <= end_date + timedelta(days=90) else
                   'ใช้งานอยู่'),
        'url': url_for('cmte.manage_sponsor', sponsor_id=row.sponsor_id),
    } for row in rows]

    return jsonify({
        'data': data,
        'recordsFiltered': records_filtered,
        'recordsTotal': records_total,
        'draw': draw,
    })


def _get_event_type_dashboard_filters(source_args):
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    dates_value = source_args.get('dates')
    if dates_value:
        start_d, end_d = dates_value.split(' - ')
        start_date = datetime.strptime(start_d, '%d/%m/%Y').date()
        end_date = datetime.strptime(end_d, '%d/%m/%Y').date()
    else:
        start_date = default_start
        end_date = today
        dates_value = f'{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}'
    return start_date, end_date, dates_value


@cmte.get('/report/event-types/dashboard')
@login_required
@cmte_admin_permission.require()
def report_event_types_dashboard():
    _, _, selected_dates = _get_event_type_dashboard_filters(request.args)
    assumptions = [
        'สรุปนี้อ้างอิงจากประเภทกิจกรรม CMTE ทั้งหมดในระบบ และนับเฉพาะกิจกรรมที่อนุมัติแล้วและไม่ถูกยกเลิกในช่วงวันที่เลือก',
        'จำนวนชนิดกิจกรรมคำนวณจากความสัมพันธ์ระหว่างประเภทกิจกรรมและชนิดกิจกรรมในระบบปัจจุบัน',
        'ตารางสรุปใช้การแบ่งหน้าแบบ AJAX เพื่อหลีกเลี่ยงการโหลดข้อมูลทั้งหมดในครั้งเดียว',
    ]
    return render_template('cmte/admin/report_event_types_dashboard.html',
                           selected_dates=selected_dates,
                           assumptions=assumptions)


@cmte.get('/report/event-types/dashboard/summary')
@login_required
@cmte_admin_permission.require()
def report_event_types_dashboard_summary():
    start_date, end_date, _ = _get_event_type_dashboard_filters(request.args)

    type_activity_counts = db.session.query(
        CMTEEventType.id.label('type_id'),
        func.count(func.distinct(CMTEEventActivity.id)).label('activity_count'),
    ).outerjoin(CMTEEventActivity, CMTEEventActivity.type_id == CMTEEventType.id)\
        .group_by(CMTEEventType.id).subquery()

    event_counts = db.session.query(
        CMTEEvent.event_type_id.label('type_id'),
        func.count(CMTEEvent.id).label('approved_event_count'),
    ).filter(CMTEEvent.approved_datetime != None,
             CMTEEvent.cancelled_datetime == None,
             func.date(CMTEEvent.approved_datetime) >= start_date,
             func.date(CMTEEvent.approved_datetime) <= end_date)\
        .group_by(CMTEEvent.event_type_id).subquery()

    summary_rows = db.session.query(
        CMTEEventType.id,
        CMTEEventType.name,
        func.coalesce(type_activity_counts.c.activity_count, 0).label('activity_count'),
        func.coalesce(event_counts.c.approved_event_count, 0).label('approved_event_count'),
    ).outerjoin(type_activity_counts, type_activity_counts.c.type_id == CMTEEventType.id)\
        .outerjoin(event_counts, event_counts.c.type_id == CMTEEventType.id).all()

    kpi = {
        'total_event_types': len(summary_rows),
        'active_event_types': sum(1 for row in summary_rows if (row.approved_event_count or 0) > 0),
        'total_activities': sum(int(row.activity_count or 0) for row in summary_rows),
        'approved_events': sum(int(row.approved_event_count or 0) for row in summary_rows),
    }

    type_chart_rows = [[row.name, int(row.approved_event_count or 0)] for row in summary_rows if (row.approved_event_count or 0) > 0]
    activity_chart_rows = [[row.name, int(row.activity_count or 0)] for row in summary_rows if (row.activity_count or 0) > 0]

    return jsonify({
        'kpi': kpi,
        'type_chart_rows': type_chart_rows[:8],
        'activity_chart_rows': activity_chart_rows[:8],
    })


@cmte.get('/report/event-types/dashboard/breakdown')
@login_required
@cmte_admin_permission.require()
def report_event_types_dashboard_breakdown():
    start_date, end_date, _ = _get_event_type_dashboard_filters(request.args)
    search = request.args.get('search[value]', '')
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=10)
    draw = request.args.get('draw', type=int)

    activity_counts = db.session.query(
        CMTEEventActivity.type_id.label('type_id'),
        func.count(CMTEEventActivity.id).label('activity_count'),
    ).group_by(CMTEEventActivity.type_id).subquery()

    event_counts = db.session.query(
        CMTEEvent.event_type_id.label('type_id'),
        func.count(CMTEEvent.id).label('approved_event_count'),
    ).filter(CMTEEvent.approved_datetime != None,
             CMTEEvent.cancelled_datetime == None,
             func.date(CMTEEvent.approved_datetime) >= start_date,
             func.date(CMTEEvent.approved_datetime) <= end_date)\
        .group_by(CMTEEvent.event_type_id).subquery()

    query = db.session.query(
        CMTEEventType.id,
        CMTEEventType.name,
        CMTEEventType.number,
        CMTEEventType.for_group,
        CMTEEventType.is_sponsored,
        func.coalesce(activity_counts.c.activity_count, 0).label('activity_count'),
        func.coalesce(event_counts.c.approved_event_count, 0).label('approved_event_count'),
    ).outerjoin(activity_counts, activity_counts.c.type_id == CMTEEventType.id)\
     .outerjoin(event_counts, event_counts.c.type_id == CMTEEventType.id)

    if search:
        query = query.filter(CMTEEventType.name.ilike(f'%{search}%'))

    records_filtered = query.count()
    records_total = db.session.query(func.count(CMTEEventType.id)).scalar()

    orderable_columns = {
        0: CMTEEventType.number,
        1: CMTEEventType.name,
        2: activity_counts.c.activity_count,
        3: event_counts.c.approved_event_count,
    }
    col_idx = request.args.get('order[0][column]', type=int)
    direction = request.args.get('order[0][dir]', default='asc')
    if col_idx in orderable_columns:
        order_column = orderable_columns[col_idx]
        query = query.order_by(order_column.desc() if direction == 'desc' else order_column.asc())
    else:
        query = query.order_by(CMTEEventType.number.asc(), CMTEEventType.name.asc())

    rows = query.offset(start).limit(length).all()
    data = [{
        'number': row.number,
        'name': row.name,
        'activity_count': int(row.activity_count or 0),
        'approved_event_count': int(row.approved_event_count or 0),
        'for_group': 'ได้' if row.for_group else 'ไม่ได้',
        'is_sponsored': 'ใช่' if row.is_sponsored else 'ไม่ใช่',
    } for row in rows]

    return jsonify({
        'data': data,
        'recordsFiltered': records_filtered,
        'recordsTotal': records_total,
        'draw': draw,
    })


def _get_participant_record_filters(source_args):
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    dates_value = source_args.get('dates')
    if dates_value:
        start_d, end_d = dates_value.split(' - ')
        start_date = datetime.strptime(start_d, '%d/%m/%Y').date()
        end_date = datetime.strptime(end_d, '%d/%m/%Y').date()
    else:
        start_date = default_start
        end_date = today
        dates_value = f'{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}'
    status = source_args.get('status', '')
    return start_date, end_date, dates_value, status


@cmte.get('/report/participant-records')
@login_required
@cmte_admin_permission.require()
def report_participant_records():
    _, _, selected_dates, selected_status = _get_participant_record_filters(request.args)
    assumptions = [
        'ช่วงวันที่ใช้กรองจากวันที่บันทึกรายการผู้เข้าร่วมเพื่อให้ครอบคลุมทั้งรายการที่ยังไม่อนุมัติและรายการที่อนุมัติแล้ว',
        'สถานะแบ่งเป็น รออนุมัติ, อนุมัติแล้ว, และไม่อนุมัติ',
    ]
    return render_template('cmte/admin/report_participant_records.html',
                           selected_dates=selected_dates,
                           selected_status=selected_status,
                           assumptions=assumptions)


@cmte.get('/report/participant-records/data')
@login_required
@cmte_admin_permission.require()
def report_participant_records_data():
    start_date, end_date, _, status = _get_participant_record_filters(request.args)
    search = request.args.get('search[value]', '')
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=10)
    draw = request.args.get('draw', type=int)

    def build_record_id_query(include_search=False, include_join_for_order=False):
        query = (db.session.query(CMTEEventParticipationRecord.id)
                 .select_from(CMTEEventParticipationRecord)
                 .filter(CMTEEventParticipationRecord.create_datetime != None)
                 .filter(func.date(CMTEEventParticipationRecord.create_datetime) >= start_date)
                 .filter(func.date(CMTEEventParticipationRecord.create_datetime) <= end_date))

        if status == 'approved':
            query = query.filter(CMTEEventParticipationRecord.approved_date != None)
        elif status == 'pending':
            query = query.filter(CMTEEventParticipationRecord.approved_date == None,
                                 CMTEEventParticipationRecord.closed_date == None)
        elif status == 'rejected':
            query = query.filter(CMTEEventParticipationRecord.closed_date != None)

        if include_search or include_join_for_order:
            query = (query
                     .outerjoin(CMTEEvent, CMTEEvent.id == CMTEEventParticipationRecord.event_id)
                     .outerjoin(CMTEEventSponsor, CMTEEventSponsor.id == CMTEEvent.sponsor_id)
                     .outerjoin(License, License.number == CMTEEventParticipationRecord.license_number)
                     .outerjoin(Member, Member.id == License.member_id))

        if include_search and search:
            query = query.filter(or_(
                CMTEEventParticipationRecord.license_number.ilike(f'%{search}%'),
                CMTEEventParticipationRecord.submitted_name.ilike(f'%{search}%'),
                CMTEEvent.title.ilike(f'%{search}%'),
                CMTEEventSponsor.name.ilike(f'%{search}%'),
                Member.th_firstname.ilike(f'%{search}%'),
                Member.th_lastname.ilike(f'%{search}%'),
            )).distinct()

        return query

    records_total = build_record_id_query().order_by(None).count()
    records_filtered = build_record_id_query(include_search=bool(search)).order_by(None).count()

    orderable_columns = {
        0: CMTEEventParticipationRecord.create_datetime,
        1: Member.th_firstname,
        2: CMTEEventParticipationRecord.license_number,
        3: CMTEEvent.title,
        4: CMTEEventSponsor.name,
        5: CMTEEventParticipationRecord.score,
        6: CMTEEventParticipationRecord.approved_date,
    }
    col_idx = request.args.get('order[0][column]', type=int)
    direction = request.args.get('order[0][dir]', default='desc')

    needs_join_for_order = col_idx in {1, 3, 4}
    ordered_ids_query = build_record_id_query(
        include_search=bool(search),
        include_join_for_order=needs_join_for_order
    )

    if col_idx in orderable_columns:
        order_column = orderable_columns[col_idx]
        ordered_ids_query = ordered_ids_query.order_by(order_column.desc() if direction == 'desc' else order_column.asc())
    else:
        ordered_ids_query = ordered_ids_query.order_by(CMTEEventParticipationRecord.create_datetime.desc())

    paged_ids = [row.id for row in ordered_ids_query.offset(start).limit(length).all()]

    if not paged_ids:
        return jsonify({
            'data': [],
            'recordsFiltered': records_filtered,
            'recordsTotal': records_total,
            'draw': draw,
        })

    query = (db.session.query(
        CMTEEventParticipationRecord.id,
        CMTEEventParticipationRecord.submitted_name,
        CMTEEventParticipationRecord.license_number,
        CMTEEventParticipationRecord.score,
        CMTEEventParticipationRecord.create_datetime,
        CMTEEventParticipationRecord.approved_date,
        CMTEEventParticipationRecord.closed_date,
        CMTEEvent.title.label('event_title'),
        CMTEEventSponsor.name.label('sponsor_name'),
        Member.th_firstname.label('member_firstname'),
        Member.th_lastname.label('member_lastname'),
    )
    .select_from(CMTEEventParticipationRecord)
    .outerjoin(CMTEEvent, CMTEEvent.id == CMTEEventParticipationRecord.event_id)
    .outerjoin(CMTEEventSponsor, CMTEEventSponsor.id == CMTEEvent.sponsor_id)
    .outerjoin(License, License.number == CMTEEventParticipationRecord.license_number)
    .outerjoin(Member, Member.id == License.member_id)
    .filter(CMTEEventParticipationRecord.id.in_(paged_ids)))

    rows_by_id = {row.id: row for row in query.all()}
    rows = [rows_by_id[row_id] for row_id in paged_ids if row_id in rows_by_id]
    data = []
    for row in rows:
        if row.closed_date:
            status_label = 'ไม่อนุมัติ'
        elif row.approved_date:
            status_label = 'อนุมัติแล้ว'
        else:
            status_label = 'รออนุมัติ'

        full_name = ' '.join(filter(None, [row.member_firstname, row.member_lastname])).strip()
        data.append({
            'created_at': row.create_datetime.isoformat() if row.create_datetime else None,
            'member_name': full_name or row.submitted_name or '-',
            'submitted_name': row.submitted_name or '-',
            'license_number': row.license_number or '-',
            'event_title': row.event_title or '-',
            'sponsor_name': row.sponsor_name or '-',
            'score': float(row.score) if row.score is not None else None,
            'approved_at': row.approved_date.isoformat() if row.approved_date else None,
            'status': status_label,
        })

    pprint(data)

    return jsonify({
        'data': data,
        'recordsFiltered': records_filtered,
        'recordsTotal': records_total,
        'draw': draw,
    })


def _get_overview_dashboard_filters(source_args):
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    dates_value = source_args.get('dates')
    if dates_value:
        start_d, end_d = dates_value.split(' - ')
        start_date = datetime.strptime(start_d, '%d/%m/%Y').date()
        end_date = datetime.strptime(end_d, '%d/%m/%Y').date()
    else:
        start_date = default_start
        end_date = today
        dates_value = f'{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}'
    return start_date, end_date, dates_value


def _get_overview_event_base_query(start_date, end_date):
    return (db.session.query(
        CMTEEvent.id.label('event_id'),
        CMTEEvent.sponsor_id.label('sponsor_id'),
        CMTEEvent.activity_id.label('activity_id'),
        CMTEEvent.approved_datetime.label('approved_datetime'),
    )
    .filter(CMTEEvent.approved_datetime != None)
    .filter(CMTEEvent.cancelled_datetime == None)
    .filter(func.date(CMTEEvent.approved_datetime) >= start_date)
    .filter(func.date(CMTEEvent.approved_datetime) <= end_date)
    ).subquery()


@cmte.get('/report/overview-dashboard')
@login_required
@cmte_admin_permission.require()
def report_overview_dashboard():
    _, _, selected_dates = _get_overview_dashboard_filters(request.args)
    return render_template('cmte/admin/report_overview_dashboard.html',
                           selected_dates=selected_dates)


@cmte.get('/report/overview-dashboard/summary')
@login_required
@cmte_admin_permission.require()
def report_overview_dashboard_summary():
    start_date, end_date, _ = _get_overview_dashboard_filters(request.args)
    event_base = _get_overview_event_base_query(start_date, end_date)

    summary_row = (db.session.query(
        func.count(func.distinct(event_base.c.sponsor_id)).label('sponsors'),
        func.count(func.distinct(event_base.c.activity_id)).label('activities'),
        func.count(func.distinct(event_base.c.event_id)).label('events'),
        func.count(CMTEEventParticipationRecord.id).label('participation_records'),
        func.count(func.distinct(License.member_id)).label('participating_members'),
    )
    .select_from(event_base)
    .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
    .outerjoin(License, License.number == CMTEEventParticipationRecord.license_number)
    .one())

    monthly_rows = (db.session.query(
        func.extract('year', event_base.c.approved_datetime).label('year'),
        func.extract('month', event_base.c.approved_datetime).label('month'),
        func.count(func.distinct(event_base.c.event_id)).label('events'),
        func.count(CMTEEventParticipationRecord.id).label('participation_records'),
    )
    .select_from(event_base)
    .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
    .group_by(func.extract('year', event_base.c.approved_datetime),
              func.extract('month', event_base.c.approved_datetime))
    .order_by(func.extract('year', event_base.c.approved_datetime),
              func.extract('month', event_base.c.approved_datetime))
    .all())

    sponsor_rows = (db.session.query(
        func.coalesce(CMTEEventSponsor.name, 'ไม่ระบุสถาบัน').label('label'),
        func.count(func.distinct(event_base.c.event_id)).label('event_count'),
    )
    .select_from(event_base)
    .outerjoin(CMTEEventSponsor, CMTEEventSponsor.id == event_base.c.sponsor_id)
    .group_by(CMTEEventSponsor.name)
    .order_by(db.text('event_count DESC'), db.text('label ASC'))
    .limit(8)
    .all())

    activity_rows = (db.session.query(
        func.coalesce(CMTEEventActivity.name, 'ไม่ระบุชนิดกิจกรรม').label('label'),
        func.count(CMTEEventParticipationRecord.id).label('record_count'),
    )
    .select_from(event_base)
    .outerjoin(CMTEEventActivity, CMTEEventActivity.id == event_base.c.activity_id)
    .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
    .group_by(CMTEEventActivity.name)
    .order_by(db.text('record_count DESC'), db.text('label ASC'))
    .limit(8)
    .all())

    trend_rows = []
    for row in monthly_rows:
        trend_rows.append([
            f'{calendar.month_abbr[int(row.month)]} {int(row.year)}',
            int(row.events or 0),
            int(row.participation_records or 0),
        ])

    return jsonify({
        'kpi': {
            'sponsors': int(summary_row.sponsors or 0),
            'activities': int(summary_row.activities or 0),
            'events': int(summary_row.events or 0),
            'participation_records': int(summary_row.participation_records or 0),
            'participating_members': int(summary_row.participating_members or 0),
        },
        'trend_rows': trend_rows,
        'sponsor_chart_rows': [[row.label, int(row.event_count or 0)] for row in sponsor_rows],
        'activity_chart_rows': [[row.label, int(row.record_count or 0)] for row in activity_rows],
    })


@cmte.get('/report/overview-dashboard/breakdown')
@login_required
@cmte_admin_permission.require()
def report_overview_dashboard_breakdown():
    start_date, end_date, _ = _get_overview_dashboard_filters(request.args)
    search = request.args.get('search[value]', '')
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=10)
    draw = request.args.get('draw', type=int)
    event_base = _get_overview_event_base_query(start_date, end_date)

    breakdown_query = (db.session.query(
        func.coalesce(CMTEEventSponsor.name, 'ไม่ระบุสถาบัน').label('sponsor_name'),
        func.count(func.distinct(event_base.c.event_id)).label('event_count'),
        func.count(CMTEEventParticipationRecord.id).label('participation_record_count'),
        func.count(func.distinct(License.member_id)).label('participating_member_count'),
    )
    .select_from(event_base)
    .outerjoin(CMTEEventSponsor, CMTEEventSponsor.id == event_base.c.sponsor_id)
    .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
    .outerjoin(License, License.number == CMTEEventParticipationRecord.license_number)
    .group_by(CMTEEventSponsor.name))

    breakdown_subquery = breakdown_query.subquery()
    query = db.session.query(breakdown_subquery)

    if search:
        query = query.filter(breakdown_subquery.c.sponsor_name.ilike(f'%{search}%'))

    records_total = db.session.query(func.count()).select_from(breakdown_subquery).scalar()
    records_filtered = query.count()

    orderable_columns = {
        0: breakdown_subquery.c.sponsor_name,
        1: breakdown_subquery.c.event_count,
        2: breakdown_subquery.c.participation_record_count,
        3: breakdown_subquery.c.participating_member_count,
    }
    col_idx = request.args.get('order[0][column]', type=int)
    direction = request.args.get('order[0][dir]', default='desc')
    if col_idx in orderable_columns:
        order_column = orderable_columns[col_idx]
        query = query.order_by(order_column.desc() if direction == 'desc' else order_column.asc())
    else:
        query = query.order_by(breakdown_subquery.c.event_count.desc(), breakdown_subquery.c.sponsor_name.asc())

    rows = query.offset(start).limit(length).all()
    data = [{
        'sponsor_name': row.sponsor_name,
        'event_count': int(row.event_count or 0),
        'participation_record_count': int(row.participation_record_count or 0),
        'participating_member_count': int(row.participating_member_count or 0),
    } for row in rows]

    return jsonify({
        'data': data,
        'recordsFiltered': records_filtered,
        'recordsTotal': records_total,
        'draw': draw,
    })


def _get_dashboard_filters(source_args):
    today = datetime.now().date()
    default_start = datetime(today.year, 1, 1).date()
    dates_value = source_args.get('dates')
    if dates_value:
        start_d, end_d = dates_value.split(' - ')
        start_date = datetime.strptime(start_d, '%d/%m/%Y').date()
        end_date = datetime.strptime(end_d, '%d/%m/%Y').date()
    else:
        start_date = default_start
        end_date = today
        dates_value = f'{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}'
    selected_activity = source_args.get('activity_id', '')
    return start_date, end_date, dates_value, selected_activity


def _get_dashboard_event_base_query(start_date, end_date, selected_activity=''):
    query = (db.session.query(
        CMTEEvent.id.label('event_id'),
        CMTEEvent.sponsor_id.label('sponsor_id'),
        CMTEEvent.activity_id.label('activity_id'),
        CMTEEvent.approved_datetime.label('approved_datetime'),
    ).filter(CMTEEvent.approved_datetime != None)
     .filter(CMTEEvent.cancelled_datetime == None)
     .filter(func.date(CMTEEvent.approved_datetime) >= start_date)
     .filter(func.date(CMTEEvent.approved_datetime) <= end_date))

    if selected_activity:
        query = query.filter(CMTEEvent.activity_id == int(selected_activity))

    return query.subquery()


def _get_dashboard_activity_breakdown_query(start_date, end_date, selected_activity=''):
    event_base = _get_dashboard_event_base_query(start_date, end_date, selected_activity)
    pending_case = case((CMTEEventParticipationRecord.approved_date == None, 1), else_=0)
    return (
        db.session.query(
            func.coalesce(CMTEEventActivity.name, 'Unassigned activity').label('activity_name'),
            func.count(func.distinct(event_base.c.event_id)).label('event_count'),
            func.count(CMTEEventParticipationRecord.id).label('participant_count'),
            func.coalesce(func.sum(pending_case), 0).label('pending_count'),
            func.count(func.distinct(event_base.c.sponsor_id)).label('sponsor_count'),
        )
        .select_from(event_base)
        .outerjoin(CMTEEventActivity, CMTEEventActivity.id == event_base.c.activity_id)
        .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
        .group_by(CMTEEventActivity.name)
    )


@cmte.route('/report/event/dashboard', methods=['GET'])
@login_required
@cmte_admin_permission.require()
def report_events_dashboard():
    _, _, selected_dates, selected_activity = _get_dashboard_filters(request.args)
    all_activity = CMTEEventActivity.query.order_by(CMTEEventActivity.number, CMTEEventActivity.name).all()

    assumptions = [
        'ตัวชี้วัดนี้นับเฉพาะกิจกรรม CMTE ที่อนุมัติแล้วและยังไม่ถูกยกเลิก',
        'ช่วงเวลาตั้งต้นคือปีปฏิทินปัจจุบัน โดยอ้างอิงจากวันที่อนุมัติกิจกรรม',
        'จำนวนผู้เข้าร่วมที่แสดงนับตามรายการบันทึกผู้เข้าร่วมที่อัปโหลด ไม่ใช่จำนวนสมาชิกที่ไม่ซ้ำกัน',
        'ตารางสรุปจัดกลุ่มตามชนิดกิจกรรม และกิจกรรมที่ยังไม่ได้ระบุชนิดจะแสดงเป็น "ยังไม่ระบุชนิดกิจกรรม"',
    ]

    return render_template(
        'cmte/admin/report_event_dashboard.html',
        selected_dates=selected_dates,
        selected_activity=selected_activity,
        all_activity=all_activity,
        assumptions=assumptions,
    )


@cmte.get('/report/event/dashboard/summary')
@login_required
@cmte_admin_permission.require()
def report_events_dashboard_summary():
    start_date, end_date, _, selected_activity = _get_dashboard_filters(request.args)
    event_base = _get_dashboard_event_base_query(start_date, end_date, selected_activity)

    kpi_row = (
        db.session.query(
            func.count(func.distinct(event_base.c.event_id)).label('approved_events'),
            func.count(func.distinct(event_base.c.sponsor_id)).label('active_sponsors'),
            func.count(CMTEEventParticipationRecord.id).label('participant_records'),
            func.coalesce(func.sum(case((CMTEEventParticipationRecord.approved_date == None, 1), else_=0)), 0)
            .label('pending_participant_approvals'),
        )
        .select_from(event_base)
        .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
        .one()
    )

    monthly_rows = (
        db.session.query(
            func.extract('year', event_base.c.approved_datetime).label('year'),
            func.extract('month', event_base.c.approved_datetime).label('month'),
            func.count(func.distinct(event_base.c.event_id)).label('approved_events'),
            func.count(CMTEEventParticipationRecord.id).label('participant_records'),
        )
        .select_from(event_base)
        .outerjoin(CMTEEventParticipationRecord, CMTEEventParticipationRecord.event_id == event_base.c.event_id)
        .group_by(func.extract('year', event_base.c.approved_datetime),
                  func.extract('month', event_base.c.approved_datetime))
        .order_by(func.extract('year', event_base.c.approved_datetime),
                  func.extract('month', event_base.c.approved_datetime))
        .all()
    )

    activity_rows = (_get_dashboard_activity_breakdown_query(start_date, end_date, selected_activity)
                     .order_by(db.text('event_count DESC'),
                               db.text('activity_name ASC'))
                     .limit(8)
                     .all())

    trend_rows = []
    for row in monthly_rows:
        year = int(row.year)
        month = int(row.month)
        trend_rows.append([
            f'{calendar.month_abbr[month]} {year}',
            int(row.approved_events or 0),
            int(row.participant_records or 0),
        ])

    activity_chart_rows = [
        [row.activity_name, int(row.event_count or 0)]
        for row in activity_rows
    ]

    return jsonify({
        'kpi': {
            'approved_events': int(kpi_row.approved_events or 0),
            'active_sponsors': int(kpi_row.active_sponsors or 0),
            'participant_records': int(kpi_row.participant_records or 0),
            'pending_participant_approvals': int(kpi_row.pending_participant_approvals or 0),
        },
        'trend_rows': trend_rows,
        'activity_chart_rows': activity_chart_rows,
    })


@cmte.get('/report/event/dashboard/activity-breakdown')
@login_required
@cmte_admin_permission.require()
def report_events_dashboard_activity_breakdown():
    start_date, end_date, _, selected_activity = _get_dashboard_filters(request.args)
    search = request.args.get('search[value]', '')
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=10)
    draw = request.args.get('draw', type=int)

    breakdown_query = _get_dashboard_activity_breakdown_query(start_date, end_date, selected_activity)
    breakdown_subquery = breakdown_query.subquery()

    query = db.session.query(breakdown_subquery)
    if search:
        query = query.filter(breakdown_subquery.c.activity_name.ilike(f'%{search}%'))

    records_filtered = query.count()
    records_total = db.session.query(func.count()).select_from(breakdown_subquery).scalar()

    orderable_columns = {
        0: breakdown_subquery.c.activity_name,
        1: breakdown_subquery.c.event_count,
        2: breakdown_subquery.c.participant_count,
        3: breakdown_subquery.c.pending_count,
        4: breakdown_subquery.c.sponsor_count,
    }
    col_idx = request.args.get('order[0][column]', type=int)
    direction = request.args.get('order[0][dir]', default='desc')
    if col_idx in orderable_columns:
        order_column = orderable_columns[col_idx]
        query = query.order_by(order_column.desc() if direction == 'desc' else order_column.asc())
    else:
        query = query.order_by(breakdown_subquery.c.event_count.desc(), breakdown_subquery.c.activity_name.asc())

    rows = query.offset(start).limit(length).all()
    data = [{
        'activity_name': row.activity_name,
        'event_count': int(row.event_count or 0),
        'participant_count': int(row.participant_count or 0),
        'pending_count': int(row.pending_count or 0),
        'sponsor_count': int(row.sponsor_count or 0),
    } for row in rows]

    return jsonify({
        'data': data,
        'recordsFiltered': records_filtered,
        'recordsTotal': records_total,
        'draw': draw,
    })
