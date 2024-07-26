"""added unique constraint and not null constraint

Revision ID: 36984cb06315
Revises: cc740487116e
Create Date: 2024-07-04 15:09:43.501366

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '36984cb06315'
down_revision = 'cc740487116e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'name',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.create_unique_constraint(None, 'users', ['name'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'users', type_='unique')
    op.alter_column('users', 'name',
               existing_type=sa.VARCHAR(),
               nullable=True)
    # ### end Alembic commands ###