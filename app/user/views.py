from flask import render_template, flash, redirect, url_for, current_app, session
from flask_login import login_user, current_user, logout_user
from flask_principal import identity_changed, Identity, AnonymousIdentity
from werkzeug.security import check_password_hash

from app import db
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
                    identity_changed.send(current_app._get_current_object(), identity=Identity(user.id))
                    flash('Logged in successfully', 'success')
                else:
                    flash('User has not been activated.', 'danger')
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
        for key in ('identity.name', 'identity.auth_type'):
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
        print(form.new_password.data)
        user.password = form.new_password.data
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('index'))
    else:
        for field in form.errors:
            flash('{}: {}'.format(field, form.errors[field]), 'danger')
    return render_template('user/user_registration_form.html', form=form)

