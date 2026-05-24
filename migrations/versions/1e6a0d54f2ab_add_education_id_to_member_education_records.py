"""add education_id to member education records

Revision ID: 1e6a0d54f2ab
Revises: 5719255b8b82
Create Date: 2026-04-09 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e6a0d54f2ab'
down_revision = '5719255b8b82'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('member_education_records', sa.Column('education_id', sa.String(), nullable=True))
    op.create_unique_constraint(
        'uq_member_education_records_education_id',
        'member_education_records',
        ['education_id'],
    )


def downgrade():
    op.drop_constraint('uq_member_education_records_education_id', 'member_education_records', type_='unique')
    op.drop_column('member_education_records', 'education_id')
