"""added number field to the event type model

Revision ID: 5f67f05eab38
Revises: a962ebab8957
Create Date: 2025-02-09 05:52:40.946977

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f67f05eab38'
down_revision = 'a962ebab8957'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_types', sa.Column('number', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_types', 'number')
    # ### end Alembic commands ###
