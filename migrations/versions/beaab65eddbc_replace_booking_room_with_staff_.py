"""Replace booking room with staff relationship

Revision ID: beaab65eddbc
Revises: 2cbfef498407
Create Date: 2026-09-01 19:50:31.934986

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'beaab65eddbc'
down_revision = '2cbfef498407'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('booking', schema=None) as batch_op:
        batch_op.add_column(sa.Column('staff_id', sa.Integer(), nullable=True))

    # Preserve existing assignments by matching the old stored name to Staff.
    op.execute(sa.text("""
        UPDATE booking
        SET staff_id = (
            SELECT staff.id
            FROM staff
            WHERE lower(trim(staff.name)) = lower(trim(booking.room))
            LIMIT 1
        )
        WHERE room IS NOT NULL
          AND lower(trim(room)) NOT IN ('', 'not assigned yet')
    """))

    with op.batch_alter_table('booking', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_booking_staff_id_staff', 'staff', ['staff_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.drop_column('room')


def downgrade():
    with op.batch_alter_table('booking', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room', sa.VARCHAR(length=20), nullable=True))

    op.execute(sa.text("""
        UPDATE booking
        SET room = (
            SELECT staff.name FROM staff WHERE staff.id = booking.staff_id
        )
        WHERE staff_id IS NOT NULL
    """))

    with op.batch_alter_table('booking', schema=None) as batch_op:
        batch_op.drop_constraint('fk_booking_staff_id_staff', type_='foreignkey')
        batch_op.drop_column('staff_id')
