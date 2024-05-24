"""changed cmte points column to numeric

Revision ID: 78d396fdce86
Revises: 6f24565ab79f
Create Date: 2024-05-24 15:56:04.988553

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '78d396fdce86'
down_revision = '6f24565ab79f'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('cmte_events', 'cmte_points', type_=sa.Numeric())


def downgrade():
    op.alter_column('cmte_events', 'cmte_points', type_=sa.Integer())
