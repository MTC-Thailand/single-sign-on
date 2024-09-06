import time
import os
import uuid
from datetime import timedelta
from io import BytesIO

import arrow
import boto3
from flask import render_template, flash, redirect, url_for, make_response, request, send_file
from flask_wtf.csrf import generate_csrf
from pytz import timezone

from app import db
from app.cmte import cmte_bp as cmte
from app.cmte.forms import CMTEEventForm, ParticipantForm, IndividualScoreForm
from app.cmte.models import CMTEEvent, CMTEEventType, CMTEEventParticipationRecord, CMTEEventDoc
from app.members.models import License

bangkok = timezone('Asia/Bangkok')


@cmte.route('/aws-s3/download/<key>', methods=['GET'])
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
def register_event():
    form = CMTEEventForm()
    return render_template('cmte/event_registration.html', form=form)


@cmte.get('/events/<int:event_id>/edit')
def edit_event(event_id):
    event = CMTEEvent.query.get(event_id)
    form = CMTEEventForm(obj=event)
    return render_template('cmte/event_registration.html', form=form, event=event)


@cmte.post('/events/registration')
@cmte.post('/events/<int:event_id>/edit')
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
def preview_event(event_id):
    event = CMTEEvent.query.get(event_id)
    next_url = request.args.get('next_url')
    return render_template('cmte/event_preview.html', event=event, next_url=next_url)


@cmte.route('/admin/events/<int:event_id>/preview', methods=('GET', 'POST'))
def admin_preview_event(event_id):
    event = CMTEEvent.query.get(event_id)
    next_url = request.args.get('next_url')
    return render_template('cmte/admin/event_preview.html', event=event, next_url=next_url)


@cmte.post('/events/<int:event_id>/submission')
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


@cmte.post('/events/<int:event_id>/payment')
def process_payment(event_id):
    # mimic an ajax request to the payment system
    time.sleep(3)
    event = CMTEEvent.query.get(event_id)
    event.payment_datetime = arrow.now('Asia/Bangkok').datetime
    db.session.add(event)
    db.session.commit()
    resp = make_response()
    flash('ชำระค่าธรรมเนียมเรียบร้อยแล้ว', 'success')
    resp.headers['HX-Redirect'] = url_for('cmte.preview_event', event_id=event_id)
    return resp


@cmte.route('/events/<int:event_id>/participants', methods=['GET', 'POST'])
@cmte.route('/events/<int:event_id>/participants/<int:rec_id>', methods=['GET', 'DELETE', 'POST'])
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
        flash('ลบรายการเรียบร้อยแล้ว', 'success')
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
        resp.headers['HX-Redirect'] = url_for('cmte.preview_event', event_id=event_id)
        return resp


@cmte.get('/admin/events/pending')
def pending_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter_by(approved_datetime=None).filter(CMTEEvent.payment_datetime != None).filter(
        CMTEEvent.submitted_datetime != None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/admin/pending_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/admin/events/approved')
def admin_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/admin/approved_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/admin/events/load-pending/pages/<int:page_no>')
def load_pending_events(page_no=1):
    events = CMTEEvent.query.filter_by(approved_datetime=None).offset(page_no * 10).limit(10)


@cmte.post('/admin/events/<int:event_id>/approve')
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
def edit_cmte_points(event_id):
    event = CMTEEvent.query.get(event_id)
    cmte_points = request.form.get('cmte_points', type=float)
    event.cmte_points = cmte_points
    db.session.add(event)
    db.session.commit()
    template = f'''<h1 class="title is-size-3">{event.cmte_points} คะแนน</h1>'''
    return template


@cmte.get('/admin/events/<int:event_id>/edit-cmte-points')
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
def show_draft_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter_by(submitted_datetime=None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/draft_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/events/submitted')
def show_submitted_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.submitted_datetime != None).filter(CMTEEvent.approved_datetime == None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/submitted_events.html', events=events.items, next_url=next_url)


@cmte.get('/events/approved')
def show_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime != None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/approved_events.html', events=events.items, next_url=next_url)


@cmte.delete('/admin/events/<int:event_id>/cancel')
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


@cmte.route('/individual-scores/index', methods=['GET'])
def individual_score_index():
    event_types = CMTEEventType.query \
        .filter_by(for_group=False, is_sponsored=False).all()
    return render_template('cmte/individual_score_index.html', event_types=event_types)


@cmte.route('/individual-scores/<int:event_type_id>/form', methods=['GET', 'POST'])
def individual_score_form(event_type_id):
    form = IndividualScoreForm()
    if form.validate_on_submit():
        pass
    return render_template('cmte/individual_score_form.html', form=form)
