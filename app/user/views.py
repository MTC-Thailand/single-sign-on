from flask import render_template, flash, redirect, url_for, current_app, session, request
from flask_login import login_user, current_user, logout_user, login_required
from flask_principal import identity_changed, Identity, AnonymousIdentity
from werkzeug.security import check_password_hash

from app import db, admin_permission, cmte_admin_permission
from app.cmte.models import CMTEFeePaymentRecord, CMTEEvent, CMTEEventParticipationRecord, CMTEEventSponsor, \
    CMTERenewSponsorRequest
from app.models import User, Client
from app.user import user_bp as user
from app.user.forms import LoginForm, ClientRegisterForm, UserRegisterForm


@user.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            if check_password_hash(user._password_hash, form.password.data):
                login_user(user, remember=True)
                if user.is_activated:
                    identity_changed.send(current_app._get_current_object(), identity=Identity(user.unique_id))
                    flash('Logged in successfully', 'success')
                else:
                    flash('User has not been activated.', 'danger')
                if request.args.get('next'):
                    return redirect(request.args.get('next'))
                else:
                    return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'danger')
        else:
            flash('Username not found.', 'danger')

    return render_template('user/login.html', form=form)


@user.route('/logout')
def logout():
    if current_user.is_authenticated:
        logout_user()
        for key in ('identity.name', 'identity.auth_type', 'login_as'):
            session.pop(key, None)

        # Tell Flask-Principal the user is anonymous
        identity_changed.send(current_app._get_current_object(), identity=AnonymousIdentity())
        flash('Logged out successfully', 'success')
    else:
        flash('User is not logged in.', 'warning')
    return redirect(url_for('index'))


@user.route('/clients/register', methods=['GET', 'POST'])
def register_client():
    form = ClientRegisterForm()
    if form.validate_on_submit():
        client = Client()
        form.populate_obj(client)
        client.creator = current_user
        client.generate_client_id()
        secret = client.generate_client_secret()
        db.session.add(client)
        db.session.commit()
        return render_template('user/client_detail.html', client=client, secret=secret)
    else:
        for field in form.errors:
            flash('{}: {}'.format(field, form.errors[field]), 'danger')
    return render_template('user/client_form.html', form=form)


@user.route('/users/register', methods=['GET', 'POST'])
def register_user():
    form = UserRegisterForm()
    if form.validate_on_submit():
        user = User()
        form.populate_obj(user)
        user.password = form.new_password.data
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('index'))
    else:
        for field in form.errors:
            flash('{}: {}'.format(field, form.errors[field]), 'danger')
    return render_template('user/user_registration_form.html', form=form)


@user.route('/index')
def admin_index():
    return render_template('admin_index.html')


@user.get('/cmte/admin')
@login_required
@cmte_admin_permission.require()
def cmte_admin_index():
    pending_sponsors = CMTEEventSponsor.query.filter_by(registered_datetime=None).count()
    pending_requests = CMTERenewSponsorRequest.query.filter_by(approved_at=None).count()
    pending_payments = CMTEFeePaymentRecord.query.filter_by(payment_datetime=None).count()
    pending_individual_records = CMTEEventParticipationRecord.query.filter_by(individual=True,
                                                                              approved_date=None,
                                                                              closed_date=None).count()
    pending_events = CMTEEvent.query.filter_by(approved_datetime=None, cancelled_datetime=None).count()
    return render_template('cmte/admin/index.html',
                           pending_sponsors=pending_sponsors,
                           pending_payments=pending_payments,
                           pending_events=pending_events,
                           pending_individual_records=pending_individual_records,
                           pending_requests=pending_requests)
