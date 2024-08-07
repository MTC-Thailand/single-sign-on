"""replaced is_active with is_activated field in User

Revision ID: 8461d05b8011
Revises: 6d0d4d137e63
Create Date: 2024-07-07 11:14:46.623472

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8461d05b8011'
down_revision = '6d0d4d137e63'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('is_activated', sa.Boolean(), nullable=True))
    op.drop_column('users', 'is_active')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.drop_column('users', 'is_activated')
    # ### end Alembic commands ###
