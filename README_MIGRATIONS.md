Flask-Migrate / Database migration instructions

Setup (virtualenv recommended):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The migration repository is already initialized. To create a new database or
bring an existing database up to date:

```bash
export FLASK_APP=app.py
flask db upgrade
```

When you change models:

```bash
export FLASK_APP=app.py
flask db migrate -m "describe change"
flask db upgrade
```

Notes:
- `FLASK_APP` must point to `app.py` (or set via `.flaskenv`).
- The default active database is `instance/details.db`.
- Old, unused database files are retained under `database_backups/`; the app
  does not read from them.
- Set `DATABASE_URL` to intentionally use another database. For example:
  `DATABASE_URL=sqlite:////absolute/path/to/test.db`.
- If Alembic complains about autogenerate, inspect the generated migration file before applying.
- Back up the database before running migrations in production.
