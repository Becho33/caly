from flask import Flask, render_template, request, redirect, jsonify, session, url_for, flash
import os
from functools import wraps
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

app = Flask(__name__)

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secret key for session (development). You can override with env var.
# Secret key for session (development). You can override with env var.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key')

# Admin password (can be overridden with ADMIN_PASSWORD env var)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Weareateam33!')

# Password for the separate staff log page.
STAFF_LOG_PASSWORD = os.environ.get('STAFF_LOG_PASSWORD', 'adminrus')

# Default hourly rate used for estimated weekly earnings.
HOURLY_RATE = float(os.environ.get('HOURLY_RATE', '30'))

TEAM_QUOTES = [
    "Great teams turn individual effort into collective magic.",
    "When we work together, every appointment feels more personal.",
    "A strong team makes every day flow with care and clarity.",
    "Together we build trust, one booking at a time.",
    "Shared purpose turns busy days into meaningful progress.",
    "The best results come when every voice is heard.",
    "Teamwork turns challenges into opportunities for everyone.",
    "We shine brighter when we support each other.",
    "Unity is the heartbeat of a successful service.",
    "Every great outcome starts with a team that shows up.",
]

# Simple in-memory tracking of failed login attempts by IP address.
# Structure: { ip: { 'count': int, 'locked_until': datetime or None } }
LOGIN_ATTEMPTS = {}

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


class StaffLoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Home page
@app.route("/")
def home():
    quote = TEAM_QUOTES[datetime.now().day % len(TEAM_QUOTES)]
    return render_template("home.html", quote=quote)


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

    # check lockout
    attempt = LOGIN_ATTEMPTS.get(client_ip, {'count': 0, 'locked_until': None})
    if attempt.get('locked_until'):
        if datetime.utcnow() < attempt['locked_until']:
            remaining = attempt['locked_until'] - datetime.utcnow()
            mins = int(remaining.total_seconds() // 60) + 1
            flash(f'Too many failed attempts. Try again in {mins} minutes.', 'danger')
            return render_template('login.html')
        else:
            # lock expired
            LOGIN_ATTEMPTS[client_ip] = {'count': 0, 'locked_until': None}

    if request.method == 'POST':
        pw = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        if pw == ADMIN_PASSWORD:
            session['logged_in'] = True
            LOGIN_ATTEMPTS[client_ip] = {'count': 0, 'locked_until': None}
            if name:
                log_entry = StaffLoginLog(name=name)
                db.session.add(log_entry)
                db.session.commit()
            flash('Logged in successfully.', 'success')
            return redirect(url_for('calendar'))
        else:
            # increment attempts
            attempt = LOGIN_ATTEMPTS.get(client_ip, {'count': 0, 'locked_until': None})
            attempt['count'] = attempt.get('count', 0) + 1
            LOGIN_ATTEMPTS[client_ip] = attempt

            remaining = max(0, 3 - attempt['count'])
            if remaining <= 0:
                # lock for 1 minute
                lock_until = datetime.utcnow() + timedelta(minutes=1)
                attempt['locked_until'] = lock_until
                LOGIN_ATTEMPTS[client_ip] = attempt
                flash('Too many failed attempts. You are locked out for 1 minute.', 'danger')
            else:
                flash(f'Invalid password. {remaining} attempts remaining.', 'warning')

            return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out', 'info')
    return redirect(url_for('home'))


@app.route('/staff-log', methods=['GET', 'POST'])
def staff_log():
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        if password != STAFF_LOG_PASSWORD:
            flash('Incorrect staff log password.', 'warning')
            return render_template('staff_log.html', entries=[], totals=None, therapist_stats=None)

        entries = StaffLoginLog.query.order_by(StaffLoginLog.logged_at.desc()).all()
        bookings = Booking.query.all()

        roster = [
            'Jules', 'Aly', 'Amira', 'Echo',
            'Suprani', 'Rose', 'Daisy', 'Lay',
            'Not assigned yet'
        ]

        therapist_stats = {
            name: {'hours': 0, 'earned': 0, 'paid': 0, 'owed': 0}
            for name in roster
        }

        total_earned = 0
        total_paid = 0
        total_owed = 0

        for booking in bookings:
            therapist = booking.room or 'Not assigned yet'
            if therapist not in therapist_stats:
                therapist_stats[therapist] = {'hours': 0, 'earned': 0, 'paid': 0, 'owed': 0}

            minutes = booking.duration or 0
            hours = minutes / 60
            earned = hours * HOURLY_RATE
            paid_amount = earned if booking.paid else 0
            owed_amount = earned - paid_amount

            therapist_stats[therapist]['hours'] += hours
            therapist_stats[therapist]['earned'] += earned
            therapist_stats[therapist]['paid'] += paid_amount
            therapist_stats[therapist]['owed'] += owed_amount

            total_earned += earned
            total_paid += paid_amount
            total_owed += owed_amount

        therapist_stats = [
            {
                'therapist': therapist,
                'hours': values['hours'],
                'earned': values['earned'],
                'paid': values['paid'],
                'owed': values['owed'],
            }
            for therapist, values in sorted(therapist_stats.items())
        ]

        totals = {
            'earned': total_earned,
            'paid': total_paid,
            'owed': total_owed,
        }

        return render_template('staff_log.html', entries=entries, totals=totals, therapist_stats=therapist_stats)

    return render_template('staff_log.html', entries=[], totals=None, therapist_stats=None)


@app.route('/calendar')
@login_required
def calendar():
    today = datetime.now().date()
    start_of_week = today - timedelta(days=(today.weekday() + 1) % 7)
    end_of_week = start_of_week + timedelta(days=6)

    weekly_stats = {}
    total_weekly_minutes = 0

    bookings = Booking.query.all()
    for booking in bookings:
        if not booking.start_time:
            continue

        booking_date = booking.start_time.date()
        if start_of_week <= booking_date <= end_of_week:
            therapist = booking.room or 'Unassigned'
            if therapist not in weekly_stats:
                weekly_stats[therapist] = {'minutes': 0, 'appointments': 0}

            weekly_stats[therapist]['minutes'] += booking.duration or 0
            weekly_stats[therapist]['appointments'] += 1
            total_weekly_minutes += booking.duration or 0

    weekly_stats_list = []
    for therapist, values in sorted(weekly_stats.items()):
        hours = values['minutes'] / 60
        weekly_stats_list.append({
            'therapist': therapist,
            'hours': hours,
            'earnings': hours * HOURLY_RATE,
            'appointments': values['appointments']
        })

    monthly_appointments = sum(
        1 for booking in bookings
        if booking.start_time and booking.start_time.year == today.year and booking.start_time.month == today.month
    )

    monthly_bookings = [
        booking for booking in bookings
        if booking.start_time and booking.start_time.year == today.year and booking.start_time.month == today.month
    ]

    monthly_weeks = []
    for week_start in range(1, 32):
        pass

    week_totals = []
    for booking in monthly_bookings:
        booking_week = booking.start_time.date() - timedelta(days=(booking.start_time.weekday() + 1) % 7)
        week_totals.append((booking_week, booking.duration or 0))

    weekly_totals_by_week = {}
    for booking_week, minutes in week_totals:
        weekly_totals_by_week[booking_week] = weekly_totals_by_week.get(booking_week, 0) + minutes

    if weekly_totals_by_week:
        average_weekly_hours = sum(value / 60 for value in weekly_totals_by_week.values()) / len(weekly_totals_by_week)
    else:
        average_weekly_hours = 0

    return render_template(
        "calendar.html",
        weekly_stats=weekly_stats_list,
        weekly_total_hours=total_weekly_minutes / 60,
        weekly_start_label=start_of_week.strftime('%d %b'),
        weekly_end_label=end_of_week.strftime('%d %b'),
        monthly_appointments=monthly_appointments,
        average_weekly_hours=average_weekly_hours,
        hourly_rate=HOURLY_RATE
    )


# Add booking page
@app.route("/add-booking", methods=["GET", "POST"])
@login_required
def add_booking():

    if request.method == "POST":
        form = request.form
        name = form.get("customer_name", "").strip()
        phone = form.get("phone", "").strip()
        start_time_str = form.get("start_time", "").strip()
        duration_str = form.get("duration", "").strip()
        paid_value = form.get("paid", "no")
        room = form.get("room", "Not assigned yet").strip()
        location = form.get("location", "").strip()

        if not name or not phone or not start_time_str or not duration_str:
            flash("Customer name, phone, appointment time and duration are required.", "warning")
            return render_template("add_booking.html")

        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            duration = int(duration_str)
        except ValueError:
            flash("Please provide a valid appointment time and duration.", "warning")
            return render_template("add_booking.html")

        paid = paid_value == "yes"

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
        form = request.form
        booking.customer_name = (form.get("customer_name") or booking.customer_name or "").strip()
        booking.phone = (form.get("phone") or booking.phone or "").strip()
        start_time_str = form.get("start_time", "").strip()
        duration_str = form.get("duration", "").strip()
        paid_value = form.get("paid", "no")
        booking.room = (form.get("room") or booking.room or "Not assigned yet").strip()
        booking.location = (form.get("location") or booking.location or "").strip()

        if not booking.customer_name or not booking.phone or not start_time_str or not duration_str:
            flash("Customer name, phone, appointment time and duration are required.", "warning")
            start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""
            return render_template("edit_booking.html", booking=booking, start_value=start_value)

        try:
            booking.start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            booking.duration = int(duration_str)
        except ValueError:
            flash("Please provide a valid appointment time and duration.", "warning")
            start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""
            return render_template("edit_booking.html", booking=booking, start_value=start_value)

        booking.paid = paid_value == "yes"

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