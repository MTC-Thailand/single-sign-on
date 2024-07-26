"""added approve date column

Revision ID: ba59ade8be80
Revises: 8461d05b8011
Create Date: 2024-07-25 14:59:27.912201

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba59ade8be80'
down_revision = '8461d05b8011'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_participation_records', sa.Column('approved_date', sa.Date(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_participation_records', 'approved_date')
    # ### end Alembic commands ###
