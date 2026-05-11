from flask import Flask, render_template, request, redirect, jsonify, session, url_for, flash
import os
from functools import wraps
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import CSRFProtect

app = Flask(__name__)

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secret key for session (development). You can override with env var.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key')
app.config['WTF_CSRF_ENABLED'] = False

# Admin password (plain fallback) or hashed via ADMIN_PASSWORD_HASH env var
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Whothefuckisalice!')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')

# If no hashed password provided, derive one from ADMIN_PASSWORD for
# backward compatibility (development only)
if ADMIN_PASSWORD_HASH:
    ADMIN_HASH = ADMIN_PASSWORD_HASH
else:
    ADMIN_HASH = generate_password_hash(ADMIN_PASSWORD)

# CSRF protection
csrf = CSRFProtect()
csrf.init_app(app)

db = SQLAlchemy(app)


# Database Model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(db.String(100))
    phone = db.Column(db.String(50))

    start_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)

    paid = db.Column(db.Boolean)

    room = db.Column(db.String(20))  # NEW FIELD
    location = db.Column(db.String(100))  # NEW FIELD


# Lockout model to persist failed login attempts per IP
class Lockout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(100), unique=True, nullable=False)
    count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)


# Home page
@app.route("/")
def home():
    return render_template("home.html")


# Calendar page
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    client_ip = request.remote_addr or 'unknown'
    # use Lockout DB model for attempts
    lock = Lockout.query.filter_by(ip=client_ip).first()
    if lock and lock.locked_until and datetime.utcnow() < lock.locked_until:
        remaining = lock.locked_until - datetime.utcnow()
        mins = int(remaining.total_seconds() // 60) + 1
        flash(f'Too many failed attempts. Try again in {mins} minutes.', 'danger')
        return render_template('login.html')

    if request.method == 'POST':
        pw = request.form.get('password', '')
        if check_password_hash(ADMIN_HASH, pw):
            session['logged_in'] = True
            # reset lockout
            if lock:
                lock.count = 0
                lock.locked_until = None
                db.session.commit()
            flash('Logged in successfully.', 'success')
            return redirect(url_for('calendar'))
        else:
            # increment or create lock record
            if not lock:
                lock = Lockout(ip=client_ip, count=1)
                db.session.add(lock)
            else:
                lock.count = (lock.count or 0) + 1

            remaining = max(0, 3 - lock.count)
            if remaining <= 0:
                lock.locked_until = datetime.utcnow() + timedelta(minutes=30)
                flash('Too many failed attempts. You are locked out for 30 minutes.', 'danger')
            else:
                flash(f'Invalid password. {remaining} attempts remaining.', 'warning')

            db.session.commit()
            return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out', 'info')
    return redirect(url_for('home'))


@app.route('/calendar')
@login_required
def calendar():
    return render_template("calendar.html")


# Add booking page
@app.route("/add-booking", methods=["GET", "POST"])
@login_required
def add_booking():

    if request.method == "POST":

        name = request.form["customer_name"]
        phone = request.form["phone"]

        start_time = datetime.strptime(
            request.form["start_time"],
            "%Y-%m-%dT%H:%M"
        )

        duration = int(request.form["duration"])

        paid = request.form["paid"] == "yes"

        room = request.form["room"]
        location = request.form["location"]

        booking = Booking(
            customer_name=name,
            phone=phone,
            start_time=start_time,
            duration=duration,
            paid=paid,
            room=room,
            location=location
        )

        db.session.add(booking)
        db.session.commit()

        return redirect("/calendar")

    return render_template("add_booking.html")


# Edit booking page
@app.route("/edit-booking/<int:booking_id>", methods=["GET", "POST"])
@login_required
def edit_booking(booking_id):
    booking = Booking.query.get(booking_id)
    if not booking:
        return redirect("/calendar")

    if request.method == "POST":
        booking.customer_name = request.form["customer_name"]
        booking.phone = request.form["phone"]

        booking.start_time = datetime.strptime(
            request.form["start_time"],
            "%Y-%m-%dT%H:%M"
        )

        booking.duration = int(request.form["duration"])
        booking.paid = request.form["paid"] == "yes"
        booking.room = request.form["room"]
        booking.location = request.form["location"]

        db.session.commit()

        return redirect("/calendar")

    # prepare value for datetime-local input
    start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""

    return render_template("edit_booking.html", booking=booking, start_value=start_value)


# Calendar events route
@app.route("/events")
def events():
    # events are protected so only logged in users can fetch them
    if not session.get('logged_in'):
        return jsonify([])

    bookings = Booking.query.all()

    events_list = []

    for booking in bookings:

        end_time = booking.start_time + timedelta(
            minutes=booking.duration
        )

        events_list.append({
            "title": f"{booking.room} | {booking.customer_name} | {booking.location} | {booking.duration} mins | {'PAID' if booking.paid else 'NOT PAID'}",
            "id": booking.id,
            "start": booking.start_time.isoformat(),
            "end": end_time.isoformat(),

            "extendedProps": {
                "room": booking.room,
                "location": booking.location,
                "phone": booking.phone,
                "paid": booking.paid,
                "duration": booking.duration
            }
        })

    return jsonify(events_list)


@app.route('/delete-booking/<int:booking_id>', methods=['DELETE'])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get(booking_id)
    if not booking:
        return jsonify({'success': False, 'error': 'not found'})
    db.session.delete(booking)
    db.session.commit()
    return jsonify({'success': True})


# Create database
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)