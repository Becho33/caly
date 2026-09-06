import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MigrationTest(unittest.TestCase):
    def test_upgrade_preserves_weekly_data_and_matches_models(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'migration.db'
            env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + str(database)}

            def migrate(*args):
                result = subprocess.run(
                    [sys.executable, '-m', 'flask', '--app', 'app', 'db', *args],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            migrate('upgrade', 'beaab65eddbc')
            with sqlite3.connect(database) as connection:
                connection.execute("INSERT INTO staff (id, name) VALUES (1, 'Migration test')")
                connection.execute("INSERT INTO staff_availability (staff_id, day_of_week, start_time, end_time) VALUES (1, 0, '09:00:00', '17:00:00')")
            connection.close()
            migrate('upgrade')
            migrate('check')
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM staff_availability').fetchone()[0], 1)
                connection.execute("INSERT INTO staff_date_availability (staff_id, date) VALUES (1, '2026-09-07')")
            connection.close()
            migrate('downgrade', 'beaab65eddbc')
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM staff_availability').fetchone()[0], 1)
            connection.close()
            migrate('upgrade')
