import io
import time
import os
import uuid
from datetime import timedelta, datetime
from io import BytesIO
import pandas as pd

import arrow
import boto3
from flask import render_template, flash, redirect, url_for, make_response, request, send_file, current_app, session
from flask_login import login_required, login_user, current_user
from flask_principal import identity_changed, Identity
from flask_wtf.csrf import generate_csrf
from pytz import timezone

from app import db, sponsor_event_management_permission
from app.cmte import cmte_bp as cmte
from app.cmte.forms import (CMTEEventForm,
                            ParticipantForm,
                            CMTESponsorMemberForm,
                            CMTESponsorMemberLoginForm,
                            CMTEEventSponsorForm,
                            CMTEPaymentForm,
                            CMTEParticipantFileUploadForm, CMTEFeePaymentForm, CMTEAdminEventForm, CMTEEventCodeForm)
from app.cmte.models import CMTEEvent, CMTEEventType, CMTEEventParticipationRecord, CMTEEventDoc, CMTEFeePaymentRecord, \
    CMTESponsorMember, CMTEEventSponsor
from app.members.models import License
from app import cmte_admin_permission, cmte_sponsor_admin_permission

bangkok = timezone('Asia/Bangkok')


@cmte.route('/aws-s3/download/<key>', methods=['GET'])
@login_required
@cmte_sponsor_admin_permission.require()
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
def cmte_index():
    return render_template('cmte/index.html')


@cmte.get('/events/registration')
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
        event_type_fee_rate_id = request.form.get('event_type_fee_rate', type=int)
        event.fee_rate_id = event_type_fee_rate_id
        event.start_date = arrow.get(event.start_date, 'Asia/Bangkok').datetime
        event.end_date = arrow.get(event.end_date, 'Asia/Bangkok').datetime
        event.sponsor = current_user.sponsor
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


@cmte.post('/fee-rates')
@login_required
def get_fee_rates():
    event_type_id = request.form.get('event_type', type=int)
    fee_rate_id = request.args.get('fee_rate_id', type=int)
    event_type = CMTEEventType.query.get(event_type_id)
    options = ''
    for fr in event_type.fee_rates:
        checked = 'checked' if fr.id == fee_rate_id else ''
        options += f'<label class="radio is-danger"><input type="radio" required {checked} name="event_type_fee_rate" value="{fr.id}"/> {fr}</label><br>'
    options += '<p class="help is-danger">โปรดเลือกค่าธรรมเนียมที่เหมาะสม</p>'
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
    form = CMTEParticipantFileUploadForm()
    event = CMTEEvent.query.get(event_id)
    _file = form.upload_file.data
    df = pd.read_excel(_file, sheet_name='Sheet1')
    for idx, row in df.iterrows():
        license_number = str(row['license_number'])
        score = float(row['score'])
        rec = CMTEEventParticipationRecord.query.filter_by(license_number=license_number,
                                                           event_id=event_id).first()
        if not rec:
            rec = CMTEEventParticipationRecord()
            rec.license_number = license_number
            rec.event_id = event_id
        rec.create_datetime = arrow.now('Asia/Bangkok').datetime
        rec.score = event.cmte_points if score > event.cmte_points else score
        db.session.add(rec)
    db.session.commit()
    flash('เพิ่มรายชื่อผู้เข้าร่วมแล้ว', 'success')
    if request.args.get('source') == 'admin':
        return redirect(url_for('cmte.admin_preview_event', event_id=event_id))
    return redirect(url_for('cmte.preview_event', event_id=event_id))


@cmte.get('/events/participants/template-file')
@login_required
@cmte_sponsor_admin_permission.require()
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
                           event=event, next_url=next_url, form=form, participant_form=participant_form)


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
    else:
        flash('รายการนี้ได้ยื่นขออนุมัติแล้ว', 'success')
    resp = make_response()
    resp.headers['HX-Redirect'] = request.args.get('next') or url_for('cmte.cmte_index')
    return resp


@cmte.route('/events/<int:event_id>/payment', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def process_payment(event_id):
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
            if _file:
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
    return render_template('cmte/event_payment_form.html', event=event, form=form)


@cmte.route('/events/<int:event_id>/participants', methods=['GET', 'POST'])
@cmte.route('/events/<int:event_id>/participants/<int:rec_id>', methods=['GET', 'DELETE', 'POST'])
@login_required
@cmte_sponsor_admin_permission.union(cmte_admin_permission).require()
def edit_participants(event_id: int = None, rec_id: int = None):
    form = ParticipantForm()
    if request.method == 'GET':
        license = None
        if rec_id:
            rec = CMTEEventParticipationRecord.query.get(rec_id)
            if rec:
                form.license_number.data = rec.license_number
                form.score.data = rec.score
                license = rec.license
        return render_template('cmte/modals/participant_form.html',
                               form=form,
                               event_id=event_id,
                               license=license,
                               rec_id=rec_id)

    if request.method == 'DELETE':
        rec = CMTEEventParticipationRecord.query.get(rec_id)
        db.session.delete(rec)
        db.session.commit()
        resp = make_response()
        return resp
    if form.validate_on_submit():
        if rec_id:
            rec = CMTEEventParticipationRecord.query.get(rec_id)
            if rec:
                rec.score = form.score.data
                rec.create_datetime = arrow.now('Asia/Bangkok').datetime
        else:
            rec = CMTEEventParticipationRecord.query.filter_by(license_number=form.license_number.data,
                                                               event_id=event_id).first()
            if rec:
                resp = make_response()
                resp.headers['HX-Trigger'] = 'alertError'
                return resp
            else:
                rec = CMTEEventParticipationRecord(event_id=event_id, license_number=form.license_number.data,
                                                   score=float(form.score.data))
                rec.create_datetime = arrow.now('Asia/Bangkok').datetime
        db.session.add(rec)
        db.session.commit()
        flash('เพิ่มข้อมูลเรียบร้อยแล้ว', 'success')
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp

    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Refresh'] = 'true'
        return resp


@cmte.get('/admin/events/pending')
@login_required
@cmte_admin_permission.require()
def admin_pending_events():
    events = CMTEEvent.query.filter_by(approved_datetime=None).all()
    return render_template('cmte/admin/pending_events.html', events=events)


@cmte.get('/admin/events/approved')
@login_required
@cmte_admin_permission.require()
def admin_approved_events():
    events = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None).all()
    return render_template('cmte/admin/approved_events.html', events=events)


@cmte.get('/admin/events/load-pending/pages/<int:page_no>')
@login_required
@cmte_sponsor_admin_permission.require()
def load_pending_events(page_no=1):
    events = CMTEEvent.query.filter_by(approved_datetime=None).offset(page_no * 10).limit(10)


@cmte.post('/admin/events/<int:event_id>/approve')
@login_required
@cmte_admin_permission.require()
def approve_event(event_id):
    event = CMTEEvent.query.get(event_id)
    event.approved_datetime = arrow.now('Asia/Bangkok').datetime
    event.submitted_datetime = event.approved_datetime + timedelta(days=event.event_type.submission_due)
    cmte_points = request.form.get('cmte_points', type=float)
    event.cmte_points = cmte_points
    db.session.add(event)
    db.session.commit()
    flash('อนุมัติกิจกรรมเรียบร้อย', 'success')
    resp = make_response()
    resp.headers['HX-Refresh'] = "true"
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
@login_required
@cmte_sponsor_admin_permission.require()
def show_draft_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter_by(submitted_datetime=None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/draft_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/events/submitted')
@login_required
@cmte_sponsor_admin_permission.require()
def show_submitted_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.submitted_datetime != None).filter(CMTEEvent.approved_datetime == None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/submitted_events.html', events=events.items, next_url=next_url)


@cmte.get('/events/approved')
@login_required
@cmte_sponsor_admin_permission.require()
def show_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None).order_by(CMTEEvent.start_datetime)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
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
    form = ParticipantForm(data={'license_number': license_number})
    if license:
        return render_template('cmte/modals/participant_form.html',
                               license=license,
                               event_id=event_id,
                               form=form,
                               rec_id=None)
    else:
        return render_template('cmte/modals/participant_form.html',
                               not_found=True,
                               event_id=event_id,
                               form=form,
                               rec_id=None)


@cmte.route('/admin/fee-payment-record-form', methods=['GET', 'POST'])
@cmte.route('/admin/fee-payment-record-form/<int:record_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def admin_edit_fee_payment_record(record_id=None):
    form = CMTEFeePaymentForm()
    today = datetime.today()
    active_payments = CMTEFeePaymentRecord.query.filter(CMTEFeePaymentRecord.end_date >= today).all()
    if request.method == 'POST':
        if form.validate_on_submit():
            record = CMTEFeePaymentRecord()
            license = License.query.filter_by(number=form.license_number.data).one()
            if license:
                if license.get_active_cmte_fee_payment():
                    flash('Fee payment has been recorded and active.', 'warning')
                    return redirect(url_for('member.admin_index'))

                form.populate_obj(record)
                record.start_date = license.start_date
                record.end_date = license.end_date
                db.session.add(record)
                db.session.commit()
                flash('Fee payment record has been created.', 'success')
                return redirect(url_for('user.cmte_admin_index'))
            else:
                flash('Fee payment record update failed. No license number found.', 'danger')
        else:
            flash('Error updating fee payment record form.', 'danger')
    return render_template('cmte/admin/fee_payment_form.html', form=form, active_payments=active_payments)


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
def register_sponsor_member():
    form = CMTESponsorMemberForm()
    if form.validate_on_submit():
        member = CMTESponsorMember.query.filter_by(email=form.email.data).first()
        if not member:
            member = CMTESponsorMember()
            form.populate_obj(member)
            member.password = form.password.data
            db.session.add(member)
            db.session.commit()
            flash(f'ลงทะเบียนเรียบร้อยแล้ว กรุณาลงชื่อเข้าใช้งาน', 'success')
            return redirect(url_for('cmte.sponsor_member_login'))
        else:
            flash(f'{form.email.data} มีการลงทะเบียนแล้ว หากลืมรหัสผ่านกรุณาติดต่อเจ้าหน้าที่', 'warning')
    return render_template('cmte/sponsor/member_form.html', form=form)


@cmte.route('/sponsors/register', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def register_sponsor():
    if current_user.sponsor:
        return redirect(url_for('cmte.manage_sponsor', sponsor_id=current_user.sponsor_id))
    form = CMTEEventSponsorForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            sponsor = CMTEEventSponsor()
            form.populate_obj(sponsor)
            sponsor.members.append(current_user)
            db.session.add(sponsor)
            db.session.commit()
            flash(f'ลงทะเบียนเรียบร้อย', 'success')
            return redirect(url_for('cmte.cmte_index'))
        else:
            flash(f'Errors: {form.errors}', 'danger')
    return render_template('cmte/sponsor/sponsor_form.html', form=form)


@cmte.route('/sponsors/<int:sponsor_id>', methods=['GET', 'POST'])
@login_required
@cmte_sponsor_admin_permission.require()
def manage_sponsor(sponsor_id):
    sponsor = CMTEEventSponsor.query.get(sponsor_id)
    return render_template('cmte/sponsor/view_sponsor.html', sponsor=sponsor)


@cmte.route('/admin/events', methods=['GET', 'POST'])
@cmte.route('/admin/events/<int:event_id>', methods=['GET', 'POST'])
@login_required
@cmte_admin_permission.require()
def admin_event_edit(event_id=None):
    if event_id:
        event = CMTEEvent.query.get(event_id)
        form = CMTEAdminEventForm(obj=event)
    else:
        event = None
        form = CMTEAdminEventForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            if not event:
                event = CMTEEvent()
            form.populate_obj(event)
            db.session.add(event)
            db.session.commit()
            flash('เพิ่มกิจกรรมเรียบร้อย', 'success')
            return redirect(url_for('users.cmte_admin_index'))
        else:
            flash(f'Error {form.errors}', 'danger')
    return render_template('cmte/admin/admin_event_form.html', form=form)
