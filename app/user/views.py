from flask import render_template, flash, redirect, url_for
from flask_login import login_user, current_user, logout_user
from werkzeug.security import check_password_hash

from app.models import User
from app.user import user_bp as user
from app.user.forms import LoginForm


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