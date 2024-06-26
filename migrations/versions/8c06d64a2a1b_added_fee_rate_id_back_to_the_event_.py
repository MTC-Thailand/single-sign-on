"""added fee_rate_id back to the event type model

Revision ID: 8c06d64a2a1b
Revises: 11cec8aa9079
Create Date: 2024-05-23 20:34:32.203518

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c06d64a2a1b'
down_revision = '11cec8aa9079'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_events', sa.Column('fee_rate_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'cmte_events', 'cmte_event_fee_rates', ['fee_rate_id'], ['id'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'cmte_events', type_='foreignkey')
    op.drop_column('cmte_events', 'fee_rate_id')
    # ### end Alembic commands ###
