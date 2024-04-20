import arrow
from flask import render_template, flash, redirect, url_for, make_response
from pytz import timezone
from sqlalchemy.event import Events

from app import db
from app.cmte import cmte_bp as cmte
from app.cmte.forms import CMTEEventForm
from app.cmte.models import CMTEEvent

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
    return render_template('cmte/event_registration.html', form=form)


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
        event.start_date = arrow.get(event.start_date, 'Asia/Bangkok').datetime
        event.end_date = arrow.get(event.end_date, 'Asia/Bangkok').datetime
        db.session.add(event)
        db.session.commit()
        flash('กรุณาตรวจสอบข้อมูลก่อนทำการยื่นขออนุมัติ', 'success')
        return redirect(url_for('cmte.preview_event', event_id=event.id))
    flash('กรุณาตรวจสอบความถูกต้องของข้อมูล', 'warning')
    return render_template('cmte/event_registration.html', form=form)


@cmte.get('/events/<int:event_id>/preview')
def preview_event(event_id):
    event = CMTEEvent.query.get(event_id)
    return render_template('cmte/event_preview.html', event=event)


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
    resp.headers['HX-Redirect'] = url_for('cmte.cmte_index')
    return resp
