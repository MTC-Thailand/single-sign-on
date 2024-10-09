"""added score_valid_until field to CMTE participation model

Revision ID: 20fd868d768f
Revises: d16a04b0f59e
Create Date: 2024-10-09 07:48:59.143375

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20fd868d768f'
down_revision = 'd16a04b0f59e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_participation_records', sa.Column('score_valid_until', sa.Date(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_participation_records', 'score_valid_until')
    # ### end Alembic commands ###