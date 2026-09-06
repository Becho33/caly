import os
import unittest
from datetime import date, time

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import app, db, Staff, StaffAvailability, StaffDateAvailability


class MonthlyAvailabilityTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.context = app.app_context()
        self.context.push()
        db.create_all()
        staff = Staff(name='Test staff')
        db.session.add(staff)
        db.session.flush()
        self.staff_id = staff.id
        db.session.add(StaffAvailability(staff_id=staff.id, day_of_week=0,
                                        start_time=time(9), end_time=time(17)))
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['logged_in'] = True
        self.url = f'/availability/edit/{self.staff_id}'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_month_lengths_and_defaults(self):
        for month, last in [('2028-02', 29), ('2026-02', 28), ('2026-04', 30), ('2026-12', 31)]:
            response = self.client.get(self.url + '?month=' + month)
            self.assertEqual(response.status_code, 200)
            self.assertIn(f'name="start_{month}-{last}"'.encode(), response.data)
            self.assertNotIn(f'name="start_{month}-{last + 1}"'.encode(), response.data)
        self.assertIn(b'value="09:00"', response.data)
        self.assertEqual(self.client.get(self.url + '?month=invalid').status_code, 400)

    def test_dates_month_isolation_and_blank_override(self):
        for month in ['2026-09', '2026-10']:
            response = self.client.post(self.url, data={
                'month': month, f'start_{month}-07': '10:00', f'end_{month}-07': '16:00',
            })
            self.assertEqual(response.status_code, 302)
        self.assertEqual(StaffDateAvailability.query.count(), 61)
        self.assertEqual(StaffAvailability.query.count(), 1)
        # September 14 is a Monday, but the saved blank overrides the weekly hours.
        blank = StaffDateAvailability.query.filter_by(date=date(2026, 9, 14)).one()
        self.assertIsNone(blank.start_time)
        response = self.client.get('/availability?month=2026-09')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'10:00', response.data)
        self.assertNotIn(b'09:00', response.data)
        self.client.post(self.url, data={'month': '2026-09'})
        self.assertEqual(StaffDateAvailability.query.count(), 61)
        self.assertEqual(StaffDateAvailability.query.filter_by(date=date(2026, 10, 7)).one().start_time, time(10))

    def test_invalid_submission_preserves_saved_month(self):
        self.client.post(self.url, data={'month': '2026-09', 'start_2026-09-01': '09:00', 'end_2026-09-01': '17:00'})
        for start, end in [('17:00', '09:00'), ('09:00', ''), ('bad', '17:00')]:
            response = self.client.post(self.url, data={'month': '2026-09', 'start_2026-09-01': start, 'end_2026-09-01': end})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(StaffDateAvailability.query.filter_by(date=date(2026, 9, 1)).one().start_time, time(9))


if __name__ == '__main__':
    unittest.main()
