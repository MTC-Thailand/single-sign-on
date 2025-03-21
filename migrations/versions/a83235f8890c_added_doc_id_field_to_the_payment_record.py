"""added doc_id field to the payment record

Revision ID: a83235f8890c
Revises: 8b6de1dc98a1
Create Date: 2024-11-19 10:38:03.773011

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a83235f8890c'
down_revision = '8b6de1dc98a1'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cmte_fee_payment_records', sa.Column('doc_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'cmte_fee_payment_records', 'cmte_event_docs', ['doc_id'], ['id'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'cmte_fee_payment_records', type_='foreignkey')
    op.drop_column('cmte_fee_payment_records', 'doc_id')
    # ### end Alembic commands ###
