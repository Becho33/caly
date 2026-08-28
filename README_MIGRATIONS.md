Flask-Migrate / Database migration instructions

Setup (virtualenv recommended):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Initialize Alembic (first time only):

```bash
export FLASK_APP=app.py
flask db init
flask db migrate -m "Initial migration"
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
- If Alembic complains about autogenerate, inspect the generated migration file before applying.
- This project uses SQLite by default (`sqlite:///details.db`). Back up your DB before running migrations in production.
