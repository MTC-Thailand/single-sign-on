"""removed unique constraint from member model

Revision ID: fb4b2fef298e
Revises: b61dcc64efd1
Create Date: 2024-10-13 09:24:25.001314

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb4b2fef298e'
down_revision = 'b61dcc64efd1'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('members_tel_key', 'members', type_='unique')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint('members_tel_key', 'members', ['tel'])
    # ### end Alembic commands ###
