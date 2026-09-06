"""Record staff contract acceptance and the accepted agreement text."""
from alembic import op
import sqlalchemy as sa

revision = 'd82b053f4921'
down_revision = 'c71a942e3810'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'staff_contract_acceptance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('staff_id', sa.Integer(), sa.ForeignKey('staff.id'), nullable=False),
        sa.Column('staff_name', sa.String(120), nullable=False),
        sa.Column('contract_version', sa.String(64), nullable=False),
        sa.Column('contract_text', sa.Text(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('staff_id', 'contract_version'),
    )


def downgrade():
    op.drop_table('staff_contract_acceptance')
