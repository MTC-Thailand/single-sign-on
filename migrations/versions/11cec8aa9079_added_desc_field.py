"""added desc field

Revision ID: 11cec8aa9079
Revises: 4b5d308c4434
Create Date: 2024-05-23 20:28:54.492073

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11cec8aa9079'
down_revision = '4b5d308c4434'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_fee_rates', sa.Column('desc', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_fee_rates', 'desc')
    # ### end Alembic commands ###
