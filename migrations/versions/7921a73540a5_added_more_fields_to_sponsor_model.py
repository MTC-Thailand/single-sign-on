"""added more fields to Sponsor model

Revision ID: 7921a73540a5
Revises: df43e25de94c
Create Date: 2024-04-20 04:04:24.790131

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7921a73540a5'
down_revision = 'df43e25de94c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_event_sponsors', sa.Column('affiliation', sa.String(), nullable=True))
    op.add_column('cmte_event_sponsors', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('cmte_event_sponsors', sa.Column('telephone', sa.String(), nullable=True))
    op.add_column('cmte_event_sponsors', sa.Column('expire_datetime', sa.DateTime(timezone=True), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cmte_event_sponsors', 'expire_datetime')
    op.drop_column('cmte_event_sponsors', 'telephone')
    op.drop_column('cmte_event_sponsors', 'address')
    op.drop_column('cmte_event_sponsors', 'affiliation')
    # ### end Alembic commands ###