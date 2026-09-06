import os
import unittest
from datetime import date, datetime, time
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import (app, db, Staff, Booking, StaffShift, StaffPayment,
                 StaffLoginLog, ADMIN_PASSWORD, STAFF_LOG_PASSWORD, LOGIN_ATTEMPTS,
                 _appointment_pay_for_staff)


class AppWorkflowsTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()
        self.staff = Staff(name='Test staff')
        db.session.add(self.staff)
        db.session.commit()
        self.client = app.test_client()
        LOGIN_ATTEMPTS.clear()
        with self.client.session_transaction() as session:
            session['logged_in'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def unlock(self):
        with self.client.session_transaction() as session:
            session['personal_details_unlocked'] = True
            session['pay_settings_unlocked'] = True

    def booking(self):
        return dict(customer_name='Test customer', phone='01234567890',
                    start_time='2026-09-07T10:00', duration='60',
                    staff_id=str(self.staff.id), location='Test clinic', paid='yes')

    def test_all_get_pages_and_templates(self):
        booking = Booking(customer_name='Test customer', phone='01234567890',
                          start_time=datetime(2026, 9, 7, 10), duration=60, staff=self.staff)
        shift = StaffShift(staff_id=self.staff.id, date=date(2026, 9, 7),
                           start_time=time(9), end_time=time(17))
        db.session.add_all([booking, shift])
        db.session.commit()
        self.unlock()
        paths = ['/', '/instructions', '/login', '/privacy/unlock', '/pay-settings/unlock',
                 '/staff-log', '/calendar', '/add-booking', f'/edit-booking/{booking.id}',
                 '/events', '/staff', '/staff/add', f'/staff/edit/{self.staff.id}',
                 f'/staff/{self.staff.id}', '/availability',
                 f'/availability/edit/{self.staff.id}', '/shifts/add',
                 f'/shifts/edit/{shift.id}', '/rota/week', '/payments',
                 '/static/css/styles.css', '/static/js/calaendar.js']
        for path in paths:
            with self.subTest(path=path):
                with self.client.get(path) as response:
                    self.assertEqual(response.status_code, 200)
        for template in app.jinja_env.list_templates():
            app.jinja_env.get_template(template)

    def test_login_logout_and_lockout(self):
        self.client.get('/logout')
        self.assertEqual(self.client.get('/availability').status_code, 302)
        self.assertEqual(self.client.get('/events').json, [])
        self.client.post('/login', data={'password': ADMIN_PASSWORD, 'name': 'Test login'})
        self.assertEqual(StaffLoginLog.query.count(), 1)
        self.assertEqual(self.client.get('/availability').status_code, 200)
        self.client.post('/logout-window')
        for _ in range(3):
            self.client.post('/login', data={'password': 'wrong'})
        self.client.post('/login', data={'password': ADMIN_PASSWORD})
        self.assertEqual(self.client.get('/availability').status_code, 302)

    def test_booking_create_edit_delete_and_privacy(self):
        self.assertEqual(self.client.post('/add-booking', data=self.booking()).status_code, 302)
        booking = Booking.query.one()
        self.assertEqual(booking.staff_id, self.staff.id)
        events = self.client.get('/events').json
        self.assertNotEqual(events[0]['extendedProps']['phone'], '01234567890')
        self.unlock()
        self.assertEqual(self.client.get('/events').json[0]['extendedProps']['phone'], '01234567890')
        data = self.booking()
        data.update(duration='90', paid='group')
        self.assertEqual(self.client.post(f'/edit-booking/{booking.id}', data=data).status_code, 302)
        self.assertEqual(booking.duration, 90)
        self.assertEqual(booking.payment_status, 'group')
        self.assertTrue(self.client.delete(f'/delete-booking/{booking.id}').json['success'])
        self.assertEqual(Booking.query.count(), 0)

    def test_invalid_bookings(self):
        for duration in ['0', '-1', 'abc', '']:
            data = self.booking()
            data['duration'] = duration
            self.assertEqual(self.client.post('/add-booking', data=data).status_code, 200)
        self.assertEqual(Booking.query.count(), 0)

    def test_staff_create_edit_toggle(self):
        self.client.post('/staff/add', data={'name': 'New staff', 'hourly_rate': '99'})
        staff = Staff.query.filter_by(name='New staff').one()
        self.unlock()
        self.assertEqual(self.client.post(f'/staff/edit/{staff.id}', data={
            'name': 'Updated staff', 'email': 'test@example.com', 'phone': '123', 'hourly_rate': '40'
        }).status_code, 302)
        self.assertEqual(staff.hourly_rate, 40)
        self.client.post(f'/staff/toggle/{staff.id}')
        self.assertFalse(staff.active)

    def test_edit_staff_with_empty_contact_details(self):
        self.unlock()
        self.assertEqual(self.client.post(f'/staff/edit/{self.staff.id}', data={'name': 'Renamed'}).status_code, 302)

    def test_shifts_create_edit_copy_delete(self):
        data = {'staff_id': self.staff.id, 'date': '2026-09-07', 'start': '09:00', 'end': '17:00'}
        self.assertEqual(self.client.post('/shifts/add', data=data).status_code, 302)
        shift = StaffShift.query.one()
        data['end'] = '16:00'
        self.assertEqual(self.client.post(f'/shifts/edit/{shift.id}', data=data).status_code, 302)
        self.assertEqual(shift.end_time, time(16))
        for _ in range(2):
            self.client.post('/rota/copy-week', data={'date': '2026-09-14'})
        self.assertEqual(StaffShift.query.count(), 2)
        self.client.post(f'/shifts/delete/{shift.id}')
        self.assertEqual(StaffShift.query.count(), 1)

    def test_shift_overlap_and_invalid_input(self):
        for index in range(2):
            staff = Staff(name=f'Other {index}')
            db.session.add(staff)
            db.session.flush()
            db.session.add(StaffShift(staff_id=staff.id, date=date(2026, 9, 7),
                                     start_time=time(9), end_time=time(17)))
        db.session.commit()
        data = {'date': '2026-09-07', 'start': '10:00', 'end': '11:00'}
        self.assertTrue(self.client.post('/shifts/check', json=data).json['blocked'])
        data['staff_id'] = self.staff.id
        self.client.post('/shifts/add', data=data)
        self.assertEqual(StaffShift.query.count(), 2)
        for invalid in [{'shift_id': 'bad'}, {'end': '09:00'}, {'date': 'bad'}]:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.post('/shifts/check', json={**data, **invalid}).status_code, 400)

    def test_payments_and_pay_calculation(self):
        self.assertEqual(self.client.get('/payments').status_code, 302)
        self.unlock()
        self.client.post('/add-booking', data=self.booking())
        self.assertEqual(_appointment_pay_for_staff(self.staff, Booking.query.all()), (60, 30))
        db.session.add(StaffShift(staff_id=self.staff.id, date=date(2026, 9, 7),
                                 start_time=time(9), end_time=time(17), hourly_rate=40))
        db.session.commit()
        self.assertEqual(_appointment_pay_for_staff(self.staff, Booking.query.all()), (60, 40))
        path = f'/staff/{self.staff.id}/payments/add'
        self.client.post(path, data={'amount': '-1'})
        self.assertEqual(StaffPayment.query.count(), 0)
        self.client.post(path, data={'amount': '20', 'payment_date': '2026-09-07'})
        payment = StaffPayment.query.one()
        self.assertEqual(payment.amount, 20)
        self.assertEqual(self.client.get('/payments?start=2026-09-01&end=2026-09-30').status_code, 200)
        self.client.post(f'/staff/{self.staff.id}/payments/delete/{payment.id}')
        self.assertEqual(StaffPayment.query.count(), 0)

    def test_contract_acceptance_requires_checkbox_and_is_saved_once(self):
        from app import StaffContractAcceptance, load_contract
        CONTRACT_TEXT, CONTRACT_VERSION = load_contract()
        profile = f'/staff/{self.staff.id}'
        response = self.client.get(profile)
        self.assertIn(b'SELF-EMPLOYED THERAPIST AGREEMENT', response.data)
        self.assertIn(b'16. DECLARATION', response.data)
        with self.client.session_transaction() as session:
            token = session['contract_csrf']
        path = profile + '/contract/accept'
        data = {'csrf_token': token, 'contract_version': CONTRACT_VERSION, 'signature_name': 'Test Signer'}
        self.client.post(path, data=data)
        self.assertEqual(StaffContractAcceptance.query.count(), 0)
        self.assertEqual(self.client.post(path, data={**data, 'csrf_token': 'bad', 'agree': 'yes'}).status_code, 400)
        self.assertEqual(self.client.post(path, data={**data, 'contract_version': 'old', 'agree': 'yes'}).status_code, 400)
        for invalid in ['', '   ', 'a' * 121]:
            self.client.post(path, data={**data, 'agree': 'yes', 'signature_name': invalid})
            self.assertEqual(StaffContractAcceptance.query.count(), 0)
        for _ in range(2):
            self.assertEqual(self.client.post(path, data={**data, 'agree': 'yes'}).status_code, 302)
        acceptance = StaffContractAcceptance.query.one()
        self.assertEqual(acceptance.signature_name, 'Test Signer')
        self.assertIsNotNone(acceptance.signed_at)
        self.assertIn(b'Signed by Test Signer', self.client.get(profile).data)
        self.assertEqual(acceptance.staff_id, self.staff.id)
        self.assertEqual(acceptance.contract_text, CONTRACT_TEXT)
        self.assertIsNotNone(acceptance.accepted_at)
        self.assertIn(b'Accepted for Test staff', self.client.get(profile).data)
        other = Staff(name='Other therapist')
        db.session.add(other)
        db.session.commit()
        self.assertIn(b'Not yet accepted', self.client.get(f'/staff/{other.id}').data)
        self.client.get('/logout')
        self.assertEqual(self.client.post(path, data={**data, 'agree': 'yes'}).status_code, 302)
        self.assertEqual(StaffContractAcceptance.query.count(), 1)

    def test_contract_changes_require_fresh_acceptance_and_preserve_history(self):
        from unittest.mock import patch
        from app import StaffContractAcceptance, load_contract
        import hashlib
        original_text, original_version = load_contract()
        profile = f'/staff/{self.staff.id}'
        self.client.get(profile)
        with self.client.session_transaction() as session:
            token = session['contract_csrf']
        data = {'csrf_token': token, 'contract_version': original_version, 'agree': 'yes', 'signature_name': 'Test Signer'}
        self.client.post(profile + '/contract/accept', data=data)
        updated_text = original_text + '<p>Updated agreement test clause</p>'
        updated_version = hashlib.sha256(updated_text.encode()).hexdigest()
        with patch('app.Path.read_text', return_value=updated_text):
            response = self.client.get(profile)
            self.assertIn(updated_text.encode(), response.data)
            self.assertIn(b'Not yet accepted', response.data)
            self.assertIn(updated_version.encode(), response.data)
            self.assertEqual(self.client.post(profile + '/contract/accept', data=data).status_code, 400)
            data['contract_version'] = updated_version
            self.assertEqual(self.client.post(profile + '/contract/accept', data=data).status_code, 302)
        records = StaffContractAcceptance.query.order_by(StaffContractAcceptance.id).all()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].contract_text, original_text)
        self.assertEqual(records[1].contract_text, updated_text)

    def test_unlock_and_relock(self):
        self.client.post('/privacy/unlock', data={'password': STAFF_LOG_PASSWORD, 'next': '//example.com'})
        with self.client.session_transaction() as session:
            self.assertTrue(session['personal_details_unlocked'])
        self.client.post('/privacy/lock')
        with self.client.session_transaction() as session:
            self.assertFalse(session.get('personal_details_unlocked', False))
        self.client.post('/pay-settings/unlock', data={'password': STAFF_LOG_PASSWORD})
        self.assertEqual(self.client.get('/payments').status_code, 200)


if __name__ == '__main__':
    unittest.main()
