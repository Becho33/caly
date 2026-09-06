"""Add typed signatures without fabricating signatures for past acceptances."""
from alembic import op
import sqlalchemy as sa

revision = 'e93c164a5032'
down_revision = 'd82b053f4921'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('staff_contract_acceptance') as batch:
        batch.add_column(sa.Column('signature_name', sa.String(120), nullable=True))
        batch.add_column(sa.Column('signed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('staff_contract_acceptance') as batch:
        batch.drop_column('signed_at')
        batch.drop_column('signature_name')
