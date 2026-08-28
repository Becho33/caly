from flask import Flask, render_template, request, redirect, jsonify, session, url_for, flash
import os
from functools import wraps
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from datetime import datetime, timedelta

app = Flask(__name__)

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///details.db'
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
# Staff are paid for assigned appointment time at a fixed per-minute rate.
APPOINTMENT_RATE_PER_MINUTE = 0.50
# Minimum required staff for coverage checks
MIN_REQUIRED_STAFF = int(os.environ.get('MIN_REQUIRED_STAFF', '2'))

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
migrate = Migrate(app, db)


# Database Model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(db.String(100))
    phone = db.Column(db.String(50))

    start_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)

    paid = db.Column(db.Boolean)
    payment_status = db.Column(db.String(20), default='not_paid')

    room = db.Column(db.String(20))  # NEW FIELD
    location = db.Column(db.String(100))  # NEW FIELD


class StaffLoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Staff and rota/payment models
class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    hourly_rate = db.Column(db.Float, default=HOURLY_RATE)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    availabilities = db.relationship('StaffAvailability', backref='staff', cascade='all, delete-orphan')
    shifts = db.relationship('StaffShift', backref='staff', cascade='all, delete-orphan')
    unavailabilities = db.relationship('StaffUnavailability', backref='staff', cascade='all, delete-orphan')
    payments = db.relationship('StaffPayment', backref='staff', cascade='all, delete-orphan')


class StaffAvailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    # 0=Monday .. 6=Sunday
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)


class StaffUnavailability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    reason = db.Column(db.String(255))


class StaffShift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(50), default='scheduled')
    hourly_rate = db.Column(db.Float)  # allow override per shift
    notes = db.Column(db.String(500))


class StaffPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(100))
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Home page
@app.route("/")
def home():
    quote = TEAM_QUOTES[datetime.now().day % len(TEAM_QUOTES)]
    return render_template("home.html", quote=quote)


# Instructions / manual page
@app.route('/instructions')
def instructions():
    return render_template('instructions.html')


# Calendar page
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def mask_personal_detail(value):
    """Return a non-identifying placeholder for stored contact information."""
    if not value:
        return "Not provided"
    return "*" * min(max(len(str(value)), 6), 12)


app.jinja_env.filters['mask_personal'] = mask_personal_detail


def pay_settings_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if not session.get('pay_settings_unlocked'):
            return redirect(url_for('pay_settings_unlock', next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route('/privacy/unlock', methods=['GET', 'POST'])
@login_required
def privacy_unlock():
    next_url = request.values.get('next', '').strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('calendar')

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == STAFF_LOG_PASSWORD:
            session['personal_details_unlocked'] = True
            flash('Personal details are now visible for this session.', 'success')
            return redirect(next_url)
        flash('Incorrect reveal password.', 'warning')

    return render_template('privacy_unlock.html', next_url=next_url)


@app.route('/privacy/lock', methods=['POST'])
@login_required
def privacy_lock():
    session.pop('personal_details_unlocked', None)
    flash('Personal details have been hidden.', 'info')
    return redirect(request.referrer or url_for('calendar'))


@app.route('/pay-settings/unlock', methods=['GET', 'POST'])
@login_required
def pay_settings_unlock():
    next_url = request.values.get('next', '').strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('payments_dashboard')

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == STAFF_LOG_PASSWORD:
            session['pay_settings_unlocked'] = True
            flash('Payment details are now unlocked for this session.', 'success')
            return redirect(next_url)
        flash('Incorrect payment password.', 'warning')

    return render_template('pay_settings_unlock.html', next_url=next_url)


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
    session.pop('personal_details_unlocked', None)
    session.pop('pay_settings_unlocked', None)
    flash('Logged out', 'info')
    return redirect(url_for('home'))


@app.route('/logout-window', methods=['POST'])
def logout_window():
    """Clear sensitive session state when a previous browser window is reopened."""
    session.pop('logged_in', None)
    session.pop('personal_details_unlocked', None)
    session.pop('pay_settings_unlocked', None)
    return ('', 204)


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
            earned = minutes * APPOINTMENT_RATE_PER_MINUTE
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
            'earnings': values['minutes'] * APPOINTMENT_RATE_PER_MINUTE,
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
        hourly_rate=APPOINTMENT_RATE_PER_MINUTE * 60,
        per_minute_rate=APPOINTMENT_RATE_PER_MINUTE
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
            return _render_booking_form("add_booking.html", form_data=form, start_value=start_time_str)

        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            duration = int(duration_str)
            if duration <= 0:
                raise ValueError
        except ValueError:
            flash("Please provide a valid appointment time and duration.", "warning")
            return _render_booking_form("add_booking.html", form_data=form, start_value=start_time_str)

        payment_status = {'yes': 'paid', 'group': 'group'}.get(paid_value, 'not_paid')
        paid = payment_status in ('paid', 'group')

        booking = Booking(
            customer_name=name,
            phone=phone,
            start_time=start_time,
            duration=duration,
            paid=paid,
            payment_status=payment_status,
            room=room,
            location=location
        )

        db.session.add(booking)
        db.session.commit()

        return redirect("/calendar")

    requested_date = request.args.get('date', '')
    start_value = f'{requested_date}T09:00' if requested_date else ''
    return _render_booking_form("add_booking.html", form_data={}, start_value=start_value)


def _render_booking_form(template_name, **context):
    staff_members = Staff.query.order_by(Staff.name).all()
    # build availability text for each staff member
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    staff_avail = {}
    for s in staff_members:
        parts = []
        for a in s.availabilities:
            try:
                parts.append(f"{days[a.day_of_week]} {a.start_time.strftime('%H:%M')}-{a.end_time.strftime('%H:%M')}")
            except Exception:
                continue
        staff_avail[s.id] = ', '.join(parts) if parts else 'No availability'

    return render_template(template_name, staff_members=staff_members, staff_avail=staff_avail, **context)


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
        if session.get('personal_details_unlocked'):
            booking.phone = (form.get("phone") or booking.phone or "").strip()
        start_time_str = form.get("start_time", "").strip()
        duration_str = form.get("duration", "").strip()
        paid_value = form.get("paid", "no")
        booking.room = (form.get("room") or booking.room or "Not assigned yet").strip()
        booking.location = (form.get("location") or booking.location or "").strip()

        if not booking.customer_name or not booking.phone or not start_time_str or not duration_str:
            flash("Customer name, phone, appointment time and duration are required.", "warning")
            start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""
            return _render_booking_form("edit_booking.html", booking=booking, start_value=start_value)

        try:
            booking.start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
            booking.duration = int(duration_str)
            if booking.duration <= 0:
                raise ValueError
        except ValueError:
            flash("Please provide a valid appointment time and duration.", "warning")
            start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""
            return _render_booking_form("edit_booking.html", booking=booking, start_value=start_value)

        booking.payment_status = {'yes': 'paid', 'group': 'group'}.get(paid_value, 'not_paid')
        booking.paid = booking.payment_status in ('paid', 'group')

        db.session.commit()

        return redirect("/calendar")

    # prepare value for datetime-local input
    start_value = booking.start_time.strftime("%Y-%m-%dT%H:%M") if booking.start_time else ""

    return _render_booking_form("edit_booking.html", booking=booking, start_value=start_value)


# Calendar events route
@app.route("/events")
def events():
    # events are protected so only logged in users can fetch them
    if not session.get('logged_in'):
        return jsonify([])

    bookings = Booking.query.all()

    events_list = []

    for booking in bookings:

        if not booking.start_time or not booking.duration or booking.duration <= 0:
            continue

        end_time = booking.start_time + timedelta(
            minutes=booking.duration
        )
        payment_status = booking.payment_status or ('paid' if booking.paid else 'not_paid')
        payment_label = {
            'paid': 'PAID',
            'not_paid': 'NOT PAID',
            'group': 'GROUPON VOUCHER',
        }.get(payment_status, 'NOT PAID')

        events_list.append({
            "title": f"{booking.room} | {booking.customer_name} | {booking.location} | {booking.duration} mins | {payment_label}",
            "id": booking.id,
            "start": booking.start_time.isoformat(),
            "end": end_time.isoformat(),

            "extendedProps": {
                "customer_name": booking.customer_name,
                "room": booking.room,
                "location": booking.location,
                "phone": booking.phone if session.get('personal_details_unlocked') else mask_personal_detail(booking.phone),
                "paid": booking.paid,
                "payment_status": payment_status,
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


# --------------------
# Staff management routes
# --------------------


@app.route('/staff')
@login_required
def staff_list():
    staff_members = Staff.query.order_by(Staff.name).all()
    return render_template('staff_list.html', staff=staff_members)


@app.route('/staff/add', methods=['GET', 'POST'])
@login_required
def add_staff():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        rate = request.form.get('hourly_rate', '').strip() if session.get('pay_settings_unlocked') else ''

        if not name:
            flash('Name is required', 'warning')
            return render_template('staff_form.html', staff=None)

        try:
            rate_val = float(rate) if rate else HOURLY_RATE
        except ValueError:
            rate_val = HOURLY_RATE

        s = Staff(name=name, email=email, phone=phone, hourly_rate=rate_val)
        db.session.add(s)
        db.session.commit()
        flash('Staff member added', 'success')
        return redirect(url_for('staff_list'))

    return render_template('staff_form.html', staff=None)


@app.route('/staff/edit/<int:staff_id>', methods=['GET', 'POST'])
@login_required
def edit_staff(staff_id):
    s = Staff.query.get_or_404(staff_id)
    if request.method == 'POST':
        s.name = request.form.get('name', s.name).strip()
        if session.get('personal_details_unlocked'):
            s.email = request.form.get('email', s.email).strip()
            s.phone = request.form.get('phone', s.phone).strip()
        if session.get('pay_settings_unlocked') and 'hourly_rate' in request.form:
            rate = request.form.get('hourly_rate', '')
            try:
                rate_value = float(rate)
                if rate_value < 0:
                    raise ValueError
                s.hourly_rate = rate_value
            except (TypeError, ValueError):
                flash('Hourly rate must be a non-negative number', 'warning')
                return render_template('staff_form.html', staff=s)
        db.session.commit()
        flash('Staff updated', 'success')
        return redirect(url_for('staff_list'))

    return render_template('staff_form.html', staff=s)


@app.route('/staff/toggle/<int:staff_id>', methods=['POST'])
@login_required
def toggle_staff_active(staff_id):
    s = Staff.query.get_or_404(staff_id)
    s.active = not s.active
    db.session.commit()
    flash('Staff status updated', 'info')
    return redirect(url_for('staff_list'))


@app.route('/staff/<int:staff_id>')
@login_required
def staff_profile(staff_id):
    s = Staff.query.get_or_404(staff_id)

    # Shifts and payments
    shifts = StaffShift.query.filter_by(staff_id=staff_id).order_by(StaffShift.date.desc()).all()
    payments = StaffPayment.query.filter_by(staff_id=staff_id).order_by(StaffPayment.payment_date.desc()).all()

    # Payroll is based on appointment minutes assigned to this staff member,
    # not the length of their rota shifts.
    assigned_bookings = Booking.query.filter_by(room=s.name).all()
    total_minutes, earned = _appointment_pay_for_staff(s, assigned_bookings)
    hours = total_minutes / 60.0

    total_paid = sum(p.amount for p in payments)
    outstanding = earned - total_paid

    return render_template('staff_profile.html', staff=s, shifts=shifts, payments=payments, hours=hours, earned=earned, paid=total_paid, outstanding=outstanding)


def _appointment_pay_for_staff(staff, bookings):
    """Calculate appointment pay, applying a matching shift's hourly override."""
    total_minutes = 0
    earned = 0.0

    for booking in bookings:
        minutes = max(0, booking.duration or 0)
        total_minutes += minutes
        rate_per_minute = APPOINTMENT_RATE_PER_MINUTE

        if booking.start_time:
            booking_time = booking.start_time.time()
            matching_shift = StaffShift.query.filter(
                StaffShift.staff_id == staff.id,
                StaffShift.date == booking.start_time.date(),
                StaffShift.start_time <= booking_time,
                StaffShift.end_time > booking_time,
            ).first()
            if matching_shift and matching_shift.hourly_rate is not None:
                rate_per_minute = matching_shift.hourly_rate / 60.0

        earned += minutes * rate_per_minute

    return total_minutes, earned


@app.route('/staff/<int:staff_id>/payments/add', methods=['POST'])
@pay_settings_required
def add_payment(staff_id):
    s = Staff.query.get_or_404(staff_id)
    amount = request.form.get('amount')
    date_str = request.form.get('payment_date')
    method = request.form.get('payment_method')
    notes = request.form.get('notes')

    try:
        amt = float(amount)
        if amt <= 0:
            raise ValueError
    except Exception:
        flash('Payment amount must be greater than zero', 'warning')
        return redirect(url_for('staff_profile', staff_id=staff_id))

    try:
        pd = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
    except Exception:
        pd = datetime.utcnow().date()

    p = StaffPayment(staff_id=staff_id, amount=amt, payment_date=pd, payment_method=method, notes=notes)
    db.session.add(p)
    db.session.commit()
    flash('Payment recorded', 'success')
    return redirect(url_for('staff_profile', staff_id=staff_id))


@app.route('/staff/<int:staff_id>/payments/delete/<int:payment_id>', methods=['POST'])
@pay_settings_required
def delete_payment(staff_id, payment_id):
    p = StaffPayment.query.filter_by(id=payment_id, staff_id=staff_id).first_or_404()
    db.session.delete(p)
    db.session.commit()
    flash('Payment removed', 'info')
    return redirect(url_for('staff_profile', staff_id=staff_id))


# --------------------
# Availability and Rota
# --------------------


def start_of_week_for(date_obj):
    return date_obj - timedelta(days=(date_obj.weekday() + 1) % 7)


@app.route('/availability')
@login_required
def availability_list():
    staff_members = Staff.query.order_by(Staff.name).all()
    return render_template('availability_list.html', staff=staff_members)


@app.route('/availability/edit/<int:staff_id>', methods=['GET', 'POST'])
@login_required
def edit_availability(staff_id):
    s = Staff.query.get_or_404(staff_id)
    if request.method == 'POST':
        # remove existing weekly availabilities
        StaffAvailability.query.filter_by(staff_id=staff_id).delete()
        db.session.commit()

        # expect fields like start_0,end_0 ... for 0=Mon .. 6=Sun
        for d in range(7):
            start_key = f'start_{d}'
            end_key = f'end_{d}'
            start_val = request.form.get(start_key, '').strip()
            end_val = request.form.get(end_key, '').strip()
            if start_val and end_val:
                try:
                    st = datetime.strptime(start_val, '%H:%M').time()
                    et = datetime.strptime(end_val, '%H:%M').time()
                    av = StaffAvailability(staff_id=staff_id, day_of_week=d, start_time=st, end_time=et)
                    db.session.add(av)
                except Exception:
                    continue

        db.session.commit()
        flash('Availability updated', 'success')
        return redirect(url_for('availability_list'))

    # prepare existing values
    existing = {a.day_of_week: a for a in s.availabilities}
    return render_template('availability_form.html', staff=s, existing=existing)


def _check_shift_overlaps(date_obj, start_time, end_time, exclude_id=None):
    # find existing shifts on the same date (optionally excluding one id)
    q = StaffShift.query.filter(StaffShift.date == date_obj)
    if exclude_id:
        q = q.filter(StaffShift.id != exclude_id)
    existing = q.all()

    # build list of overlapping segments within candidate interval for conflict detection
    events = []
    conflicts = []
    for ex in existing:
        if ex.end_time <= start_time or ex.start_time >= end_time:
            continue
        seg_start = max(ex.start_time, start_time)
        seg_end = min(ex.end_time, end_time)
        events.append((seg_start, 1, ex))
        events.append((seg_end, -1, ex))
        conflicts.append({'staff': ex.staff.name, 'start': seg_start.strftime('%H:%M'), 'end': seg_end.strftime('%H:%M')})

    # sweep line to compute max concurrent existing overlaps within candidate interval
    max_concurrent = 0
    if events:
        events.sort(key=lambda x: (x[0].hour, x[0].minute, -x[1]))
        concurrent = 0
        for ev in events:
            concurrent += ev[1]
            max_concurrent = max(max_concurrent, concurrent)

    # compute suggestions: find gaps on the day where the requested duration fits
    req_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
    # build busy intervals for the whole day
    busy = []
    existing_shifts = []
    for ex in existing:
        smin = ex.start_time.hour * 60 + ex.start_time.minute
        emin = ex.end_time.hour * 60 + ex.end_time.minute
        busy.append((smin, emin))
        existing_shifts.append({'staff': ex.staff.name, 'start': ex.start_time.strftime('%H:%M'), 'end': ex.end_time.strftime('%H:%M')})
    busy.sort()
    # merge busy intervals
    merged = []
    for s_min, e_min in busy:
        if not merged or s_min > merged[-1][1]:
            merged.append([s_min, e_min])
        else:
            merged[-1][1] = max(merged[-1][1], e_min)

    # working day bounds
    day_start = 6 * 60
    day_end = 23 * 60
    earliest = []
    latest = []
    centered = []
    prev = day_start
    for s_min, e_min in merged:
        gap = s_min - prev
        if gap >= req_minutes:
            # earliest in gap
            sug_start = prev
            sug_end = prev + req_minutes
            earliest.append({'start': f"{sug_start//60:02d}:{sug_start%60:02d}", 'end': f"{sug_end//60:02d}:{sug_end%60:02d}"})
            # latest in gap (end at gap end)
            sug_end_l = s_min
            sug_start_l = s_min - req_minutes
            latest.append({'start': f"{sug_start_l//60:02d}:{sug_start_l%60:02d}", 'end': f"{sug_end_l//60:02d}:{sug_end_l%60:02d}"})
            # centered in gap
            center_start = prev + max(0, (gap - req_minutes)//2)
            center_end = center_start + req_minutes
            centered.append({'start': f"{center_start//60:02d}:{center_start%60:02d}", 'end': f"{center_end//60:02d}:{center_end%60:02d}"})
        prev = max(prev, e_min)
    # tail gap
    gap = day_end - prev
    if gap >= req_minutes:
        sug_start = prev
        sug_end = prev + req_minutes
        earliest.append({'start': f"{sug_start//60:02d}:{sug_start%60:02d}", 'end': f"{sug_end//60:02d}:{sug_end%60:02d}"})
        sug_end_l = day_end
        sug_start_l = day_end - req_minutes
        latest.append({'start': f"{sug_start_l//60:02d}:{sug_start_l%60:02d}", 'end': f"{sug_end_l//60:02d}:{sug_end_l%60:02d}"})
        center_start = prev + max(0, (gap - req_minutes)//2)
        center_end = center_start + req_minutes
        centered.append({'start': f"{center_start//60:02d}:{center_start%60:02d}", 'end': f"{center_end//60:02d}:{center_end%60:02d}"})

    suggestions = {'earliest': earliest, 'latest': latest, 'centered': centered}

    blocked = max_concurrent >= 2
    return blocked, conflicts, suggestions, existing_shifts


@app.route('/shifts/add', methods=['GET', 'POST'])
@login_required
def add_shift():
    staff_members = Staff.query.order_by(Staff.name).all()
    if request.method == 'POST':
        date_str = request.form.get('date')
        start = request.form.get('start')
        end = request.form.get('end')
        rate = request.form.get('hourly_rate') if session.get('pay_settings_unlocked') else None
        notes = request.form.get('notes')

        try:
            staff_id = int(request.form.get('staff_id', ''))
            Staff.query.get_or_404(staff_id)
            dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            st = datetime.strptime(start, '%H:%M').time()
            et = datetime.strptime(end, '%H:%M').time()
            if et <= st:
                raise ValueError
        except Exception:
            flash('Invalid date/time', 'warning')
            return render_template('shift_form.html', staff=staff_members, shift=None)

        try:
            rate_val = float(rate) if rate else None
            if rate_val is not None and rate_val < 0:
                raise ValueError
        except (TypeError, ValueError):
            flash('Hourly rate must be a positive number.', 'warning')
            return render_template('shift_form.html', staff=staff_members, shift=None)

        # check overlaps: if there are already 2 or more overlapping shifts at any time, block
        blocked, conflicts, suggestions, existing_shifts = _check_shift_overlaps(dt, st, et)
        if blocked:
            conflict_strings = [f"{c['staff']} {c['start']}-{c['end']}" for c in conflicts]
            flash('Requested time conflicts with existing shifts: ' + ', '.join(conflict_strings), 'warning')
            # create a temporary shift object to prefill form with attempted values
            tmp = StaffShift(staff_id=staff_id, date=dt, start_time=st, end_time=et, hourly_rate=rate_val, notes=notes)
            return render_template('shift_form.html', staff=staff_members, shift=tmp)

        sh = StaffShift(staff_id=staff_id, date=dt, start_time=st, end_time=et, hourly_rate=rate_val, notes=notes)
        db.session.add(sh)
        db.session.commit()
        flash('Shift added', 'success')
        return redirect(url_for('rota_week'))

    return render_template('shift_form.html', staff=staff_members, shift=None)


@app.route('/shifts/edit/<int:shift_id>', methods=['GET', 'POST'])
@login_required
def edit_shift(shift_id):
    sh = StaffShift.query.get_or_404(shift_id)
    staff_members = Staff.query.order_by(Staff.name).all()
    if request.method == 'POST':
        date_str = request.form.get('date')
        start = request.form.get('start')
        end = request.form.get('end')
        rate = request.form.get('hourly_rate') if session.get('pay_settings_unlocked') else None
        notes = request.form.get('notes')

        try:
            staff_id = int(request.form.get('staff_id', ''))
            Staff.query.get_or_404(staff_id)
            dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            st = datetime.strptime(start, '%H:%M').time()
            et = datetime.strptime(end, '%H:%M').time()
            if et <= st:
                raise ValueError
        except Exception:
            flash('Invalid date/time', 'warning')
            return render_template('shift_form.html', staff=staff_members, shift=sh)

        try:
            rate_val = float(rate) if rate else None
            if rate_val is not None and rate_val < 0:
                raise ValueError
        except (TypeError, ValueError):
            flash('Hourly rate must be a positive number.', 'warning')
            return render_template('shift_form.html', staff=staff_members, shift=sh)

        # check overlaps excluding this shift
        blocked, conflicts, suggestions, existing_shifts = _check_shift_overlaps(dt, st, et, exclude_id=shift_id)
        if blocked:
            conflict_strings = [f"{c['staff']} {c['start']}-{c['end']}" for c in conflicts]
            flash('Requested time conflicts with existing shifts: ' + ', '.join(conflict_strings), 'warning')
            tmp_rate = rate_val if session.get('pay_settings_unlocked') else sh.hourly_rate
            tmp = StaffShift(staff_id=staff_id, date=dt, start_time=st, end_time=et, hourly_rate=tmp_rate, notes=notes)
            tmp.id = sh.id
            return render_template('shift_form.html', staff=staff_members, shift=tmp)

        sh.staff_id = staff_id
        sh.start_time = st
        sh.end_time = et
        try:
            if session.get('pay_settings_unlocked'):
                sh.hourly_rate = rate_val
        except Exception:
            pass
        sh.notes = notes
        try:
            sh.date = dt
        except Exception:
            pass
        db.session.commit()
        flash('Shift updated', 'success')
        return redirect(url_for('rota_week'))

    return render_template('shift_form.html', staff=staff_members, shift=sh)


@app.route('/shifts/delete/<int:shift_id>', methods=['POST'])
@login_required
def delete_shift(shift_id):
    sh = StaffShift.query.get_or_404(shift_id)
    db.session.delete(sh)
    db.session.commit()
    flash('Shift deleted', 'info')
    return redirect(url_for('rota_week'))


@app.route('/shifts/check', methods=['POST'])
@login_required
def check_shift_overlap():
    # Accept form-encoded or JSON body
    try:
        req_json = request.get_json(silent=True) or {}
        date_str = request.form.get('date') or req_json.get('date')
        start = request.form.get('start') or req_json.get('start')
        end = request.form.get('end') or req_json.get('end')
        shift_id = request.form.get('shift_id') or req_json.get('shift_id')
        if not date_str or not start or not end:
            return jsonify({'error': 'date/start/end required'}), 400
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        st = datetime.strptime(start, '%H:%M').time()
        et = datetime.strptime(end, '%H:%M').time()
    except Exception:
        return jsonify({'error': 'invalid date/time'}), 400

    exclude_id = int(shift_id) if shift_id else None
    blocked, conflicts, suggestions, existing_shifts = _check_shift_overlaps(dt, st, et, exclude_id=exclude_id)
    return jsonify({'blocked': blocked, 'conflicts': conflicts, 'suggestions': suggestions, 'existing': existing_shifts})


@app.route('/rota/week')
@login_required
def rota_week():
    date_str = request.args.get('date')
    if date_str:
        try:
            base = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            base = datetime.now().date()
    else:
        base = datetime.now().date()

    sow = start_of_week_for(base)
    days = [sow + timedelta(days=i) for i in range(7)]

    staff_members = Staff.query.order_by(Staff.name).all()
    shifts = StaffShift.query.filter(StaffShift.date >= days[0], StaffShift.date <= days[-1]).all()

    # organize shifts by staff and date
    shifts_by_staff = {s.id: [] for s in staff_members}
    for sh in shifts:
        shifts_by_staff.setdefault(sh.staff_id, []).append(sh)

    # coverage per hour (6..21)
    coverage = {}
    for d in days:
        day_cov = {}
        for hour in range(6, 22):
            count = 0
            for sh in shifts:
                if sh.date != d:
                    continue
                try:
                    start_hour = sh.start_time.hour
                    end_hour = sh.end_time.hour
                    if start_hour <= hour < end_hour:
                        count += 1
                except Exception:
                    continue
            day_cov[hour] = count
        coverage[d] = day_cov

    # bookings for the week
    bookings = Booking.query.filter(Booking.start_time >= datetime.combine(days[0], datetime.min.time()), Booking.start_time <= datetime.combine(days[-1], datetime.max.time())).all()

    # bookings per hour for the week
    bookings_by_day_hour = {d: {h: 0 for h in range(6, 22)} for d in days}
    for b in bookings:
        if not b.start_time:
            continue
        b_date = b.start_time.date()
        if b_date < days[0] or b_date > days[-1]:
            continue
        try:
            b_start = b.start_time
            b_end = b_start + timedelta(minutes=(b.duration or 0))
            hour = b_start.hour
            while hour <= b_end.hour:
                if 6 <= hour < 22:
                    bookings_by_day_hour[b_date][hour] = bookings_by_day_hour[b_date].get(hour, 0) + 1
                hour += 1
        except Exception:
            continue

    # associate bookings to shifts where possible
    bookings_by_shift = {}
    unassigned_bookings = []
    for b in bookings:
        assigned = False
        if not b.start_time:
            unassigned_bookings.append(b)
            continue
        for sh in shifts:
            if sh.date != b.start_time.date():
                continue
            try:
                if sh.start_time <= b.start_time.time() < sh.end_time:
                    bookings_by_shift.setdefault(sh.id, []).append(b)
                    assigned = True
                    break
            except Exception:
                continue
        if not assigned:
            unassigned_bookings.append(b)

    # gap detection: consecutive hours where coverage < MIN_REQUIRED_STAFF
    gaps = {}
    for d in days:
        gaps[d] = []
        in_gap = False
        gap_start = None
        for hour in range(6, 22):
            cnt = coverage[d].get(hour, 0)
            if cnt < MIN_REQUIRED_STAFF:
                if not in_gap:
                    in_gap = True
                    gap_start = hour
            else:
                if in_gap:
                    gaps[d].append((gap_start, hour, coverage[d].get(gap_start, 0)))
                    in_gap = False
                    gap_start = None
        if in_gap:
            gaps[d].append((gap_start, 22, coverage[d].get(gap_start, 0)))

    return render_template(
        'rota_week.html', staff=staff_members, days=days,
        shifts_by_staff=shifts_by_staff, coverage=coverage,
        bookings_by_day_hour=bookings_by_day_hour,
        bookings_by_shift=bookings_by_shift,
        unassigned_bookings=unassigned_bookings, gaps=gaps,
        min_required=MIN_REQUIRED_STAFF,
        previous_week=(sow - timedelta(days=7)).isoformat(),
        next_week=(sow + timedelta(days=7)).isoformat()
    )



@app.route('/rota/copy-week', methods=['POST'])
@login_required
def rota_copy_week():
    # Copy previous week shifts into the week containing provided date (or current week)
    date_str = request.form.get('date')
    if date_str:
        try:
            base = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            base = datetime.now().date()
    else:
        base = datetime.now().date()

    target_sow = start_of_week_for(base)
    source_sow = target_sow - timedelta(days=7)

    # fetch source shifts
    source_shifts = StaffShift.query.filter(StaffShift.date >= source_sow, StaffShift.date < source_sow + timedelta(days=7)).all()

    copied = 0
    for sh in source_shifts:
        offset = (sh.date - source_sow).days
        new_date = target_sow + timedelta(days=offset)
        # avoid exact duplicate: check if staff has a shift at same date/start/end
        exists = StaffShift.query.filter_by(staff_id=sh.staff_id, date=new_date, start_time=sh.start_time, end_time=sh.end_time).first()
        if exists:
            continue
        new_shift = StaffShift(staff_id=sh.staff_id, date=new_date, start_time=sh.start_time, end_time=sh.end_time, status=sh.status, hourly_rate=sh.hourly_rate, notes=(sh.notes or '') )
        db.session.add(new_shift)
        copied += 1

    db.session.commit()
    flash(f'Copied {copied} shifts from previous week', 'success')
    return redirect(url_for('rota_week', date=target_sow.strftime('%Y-%m-%d')))


@app.route('/bookings/assign/<int:booking_id>/<int:staff_id>', methods=['POST'])
@login_required
def assign_booking(booking_id, staff_id):
    b = Booking.query.get_or_404(booking_id)
    s = Staff.query.get_or_404(staff_id)
    # For simplicity store staff name in booking.room
    b.room = s.name
    db.session.commit()
    flash('Booking assigned to ' + s.name, 'success')
    return redirect(request.referrer or url_for('rota_week'))


@app.route('/payments', methods=['GET'])
@pay_settings_required
def payments_dashboard():
    # date range filter
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
    except Exception:
        start = None
    try:
        end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None
    except Exception:
        end = None

    staff_members = Staff.query.order_by(Staff.name).all()

    results = []
    total_hours = 0.0
    total_earned = 0.0
    total_paid = 0.0

    for s in staff_members:
        # Payroll is based on assigned appointment minutes in the date range.
        q = Booking.query.filter_by(room=s.name)
        if start:
            q = q.filter(Booking.start_time >= datetime.combine(start, datetime.min.time()))
        if end:
            q = q.filter(Booking.start_time <= datetime.combine(end, datetime.max.time()))
        assigned_bookings = q.all()

        minutes, earned = _appointment_pay_for_staff(s, assigned_bookings)

        # payments in range
        pq = StaffPayment.query.filter_by(staff_id=s.id)
        if start:
            pq = pq.filter(StaffPayment.payment_date >= start)
        if end:
            pq = pq.filter(StaffPayment.payment_date <= end)
        payments = pq.all()
        paid = sum(p.amount for p in payments)

        total_hours += minutes / 60.0
        total_earned += earned
        total_paid += paid

        results.append({'staff': s, 'hours': minutes / 60.0, 'earned': earned, 'paid': paid, 'outstanding': earned - paid})

    totals = {'hours': total_hours, 'earned': total_earned, 'paid': total_paid, 'outstanding': total_earned - total_paid}

    return render_template('payments_dashboard.html', results=results, totals=totals, start=start, end=end)



# Create database
with app.app_context():
    db.create_all()
    booking_columns = {column['name'] for column in inspect(db.engine).get_columns('booking')}
    if 'payment_status' not in booking_columns:
        db.session.execute(text("ALTER TABLE booking ADD COLUMN payment_status VARCHAR(20) DEFAULT 'not_paid'"))
        db.session.execute(text("UPDATE booking SET payment_status = CASE WHEN paid = 1 THEN 'paid' ELSE 'not_paid' END"))
    db.session.execute(text("UPDATE booking SET paid = 1 WHERE payment_status = 'group'"))
    db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)
