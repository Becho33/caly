from app import app, db, Booking
from datetime import datetime

def insert_test():
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        b = Booking(
            customer_name='Test Customer',
            phone='07000000000',
            start_time=datetime(2026, 9, 1, 10, 0),
            duration=60,
            paid=False,
            room='TestRoom',
            location='TestLocation'
        )
        db.session.add(b)
        db.session.commit()
        print('Inserted booking id:', b.id)

if __name__ == '__main__':
    insert_test()
