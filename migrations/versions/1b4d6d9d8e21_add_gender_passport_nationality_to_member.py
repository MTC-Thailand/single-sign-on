"""add gender passport_id and nationality to member

Revision ID: 1b4d6d9d8e21
Revises: 08dbcb75e534, 84d8913776f3, f60fd3a71fec
Create Date: 2026-04-01 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b4d6d9d8e21'
down_revision = ('08dbcb75e534', '84d8913776f3', 'f60fd3a71fec')
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('members', sa.Column('gender', sa.String(), nullable=True))
    op.add_column('members', sa.Column('passport_id', sa.String(), nullable=True))
    op.add_column('members', sa.Column('nationality', sa.String(), nullable=True))


def downgrade():
    op.drop_column('members', 'nationality')
    op.drop_column('members', 'passport_id')
    op.drop_column('members', 'gender')
