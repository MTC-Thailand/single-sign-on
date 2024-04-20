"""added timezone True to start and end datetime

Revision ID: 13340d16f2bf
Revises: fbff9a8d2929
Create Date: 2024-04-20 07:44:05.748735

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '13340d16f2bf'
down_revision = 'fbff9a8d2929'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cmte_events") as batch_op:
        batch_op.alter_column("start_date", type_=sa.DateTime(timezone=True))
        batch_op.alter_column("end_date", type_=sa.DateTime(timezone=True))


def downgrade():
    with op.batch_alter_table("cmte_events") as batch_op:
        batch_op.alter_column("start_date", sa.DateTime())
        batch_op.alter_column("end_date", sa.DateTime())
