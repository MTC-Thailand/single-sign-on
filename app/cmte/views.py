import time
from datetime import timedelta

import arrow
from flask import render_template, flash, redirect, url_for, make_response, request
from pytz import timezone

from app import db
from app.cmte import cmte_bp as cmte
from app.cmte.forms import CMTEEventForm, ParticipantForm
from app.cmte.models import CMTEEvent, CMTEEventType, CMTEEventParticipationRecord

bangkok = timezone('Asia/Bangkok')


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
    if form.validate_on_submit():
        if not event_id:
            event = CMTEEvent()
        else:
            event = CMTEEvent.query.get(event_id)
        form.populate_obj(event)
        event_type_fee_rate_id = request.form.get('event_type_fee_rate', type=int)
        event.fee_rate_id = event_type_fee_rate_id
        event.start_date = arrow.get(event.start_date, 'Asia/Bangkok').datetime
        event.end_date = arrow.get(event.end_date, 'Asia/Bangkok').datetime
        db.session.add(event)
        db.session.commit()
        flash('กรุณาตรวจสอบข้อมูลก่อนทำการยื่นขออนุมัติ', 'success')
        return redirect(url_for('cmte.preview_event', event_id=event.id))
    flash('กรุณาตรวจสอบความถูกต้องของข้อมูล', 'warning')
    return render_template('cmte/event_registration.html', form=form)


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


@cmte.get('/admin/events/<int:event_id>/preview')
def admin_preview_event(event_id):
    event = CMTEEvent.query.get(event_id)
    return render_template('cmte/admin/event_preview.html', event=event)


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
@cmte.route('/events/<int:event_id>/participants/<int:rec_id>', methods=['DELETE', 'PATCH'])
def edit_participants(event_id: int=None, rec_id: int=None):
    form = ParticipantForm()
    if request.method == 'GET':
        return render_template('cmte/modals/participant_form.html', form=form, event_id=event_id)

    if request.method == 'DELETE':
        rec = CMTEEventParticipationRecord.query.get(rec_id)
        db.session.delete(rec)
        db.session.commit()
        flash('ลบรายการเรียบร้อยแล้ว', 'success')
    if form.validate_on_submit():
        rec = CMTEEventParticipationRecord.query.filter_by(firstname=form.firstname.data, lastname=form.lastname.data).first()
        if rec:
            flash('รายชื่อนี้มีการเพิ่มเข้ามาแล้ว', 'warning')
        else:
            rec = CMTEEventParticipationRecord()
            form.populate_obj(rec)
            rec.event_id = event_id
            rec.create_datetime = arrow.now('Asia/Bangkok').datetime
            db.session.add(rec)
            db.session.commit()
            flash('เพิ่มรายชื่อเรียบร้อยแล้ว', 'success')

    if request.headers.get('HX-Request') == 'true':
        resp = make_response()
        resp.headers['HX-Redirect'] = url_for('cmte.preview_event', event_id=event_id)
        return resp


@cmte.get('/admin/events/pending')
def pending_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter_by(approved_datetime=None)
    events = query.paginate(page=page, per_page=20)
    next_url = url_for('cmte.pending_events', page=events.next_num) if events.has_next else None
    return render_template('cmte/admin/pending_events.html',
                           events=events.items, next_url=next_url)


@cmte.get('/admin/events/approved')
def admin_approved_events():
    page = request.args.get('page', type=int, default=1)
    query = CMTEEvent.query.filter(CMTEEvent.approved_datetime!=None)
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
    events = CMTEEvent.query.filter_by(approved_datetime=None)
    event.approved_datetime = arrow.now('Asia/Bangkok').datetime
    event.submitted_datetime = event.approved_datetime + timedelta(days=event.event_type.submission_due)
    db.session.add(event)
    db.session.commit()
    flash('อนุมัติกิจกรรมเรียบร้อย', 'success')
    resp = make_response()
    resp.headers['HX-Redirect'] = url_for('cmte.pending_events')
    return resp


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
