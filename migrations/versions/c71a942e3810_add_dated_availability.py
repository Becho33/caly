"""Add date-specific staff availability.

Revision ID: c71a942e3810
Revises: beaab65eddbc
"""
from alembic import op
import sqlalchemy as sa

revision = 'c71a942e3810'
down_revision = 'beaab65eddbc'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'staff_date_availability',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('staff_id', sa.Integer(), sa.ForeignKey('staff.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.UniqueConstraint('staff_id', 'date'),
    )


def downgrade():
    op.drop_table('staff_date_availability')
