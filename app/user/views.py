from flask import render_template, flash, redirect, url_for
from flask_login import login_user, current_user, logout_user
from werkzeug.security import check_password_hash

from app import db
from app.models import User, Client
from app.user import user_bp as user
from app.user.forms import LoginForm, ClientRegisterForm


@user.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            if check_password_hash(user._password_hash, form.password.data):
                login_user(user, remember=True)
                flash('Logged in successfully', 'success')
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