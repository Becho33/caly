"""Add the application's complete staff roster to the database.

This script is safe to run more than once: existing staff members are left
unchanged and only missing names are inserted.
"""

from app import Staff, app, db


STAFF_NAMES = (
    "Jules",
    "Aly",
    "Amira",
    "Echo",
    "Suprani",
    "Rose",
    "Daisy",
    "Lay",
    "Riina",
    "Atheana",
)


def seed_staff() -> list[str]:
    """Insert missing staff members and return the names that were added."""
    existing_names = {
        staff.name.strip().casefold()
        for staff in Staff.query.all()
        if staff.name and staff.name.strip()
    }
    added_names = []

    for name in STAFF_NAMES:
        if name.casefold() not in existing_names:
            db.session.add(Staff(name=name))
            existing_names.add(name.casefold())
            added_names.append(name)

    db.session.commit()
    return added_names


if __name__ == "__main__":
    with app.app_context():
        added = seed_staff()
        if added:
            print(f"Added {len(added)} staff members: {', '.join(added)}")
        else:
            print("All staff members already exist.")
