"""add building to member addresses

Revision ID: 5a7c3d21e8f4
Revises: 1b4d6d9d8e21
Create Date: 2026-04-01 18:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a7c3d21e8f4'
down_revision = '1b4d6d9d8e21'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('member_addresses', sa.Column('building', sa.String(), nullable=True))


def downgrade():
    op.drop_column('member_addresses', 'building')
