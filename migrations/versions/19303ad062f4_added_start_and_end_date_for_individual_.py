"""added start and end date for individual record

Revision ID: 19303ad062f4
Revises: b104f3434c6b
Create Date: 2024-10-21 09:07:40.157882

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '19303ad062f4'
down_revision = 'b104f3434c6b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_participation_records', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('cmte_event_participation_records', sa.Column('end_date', sa.Date(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_participation_records', 'end_date')
    op.drop_column('cmte_event_participation_records', 'start_date')
    # ### end Alembic commands ###
