"""removed not null constraint from payment datetime

Revision ID: 9ba2968ed296
Revises: a83235f8890c
Create Date: 2024-11-19 11:06:31.950280

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9ba2968ed296'
down_revision = 'a83235f8890c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('cmte_fee_payment_records', 'payment_datetime',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('cmte_fee_payment_records', 'payment_datetime',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    # ### end Alembic commands ###
