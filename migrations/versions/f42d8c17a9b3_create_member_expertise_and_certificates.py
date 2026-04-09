"""create member expertise and certificates

Revision ID: f42d8c17a9b3
Revises: 1e6a0d54f2ab
Create Date: 2026-04-10 10:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f42d8c17a9b3'
down_revision = '1e6a0d54f2ab'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'member_expertise',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('expertise', sa.String(), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'member_certificates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('certificate_name', sa.String(), nullable=True),
        sa.Column('certificate_detail', sa.String(), nullable=True),
        sa.Column('issued_date', sa.Date(), nullable=True),
        sa.Column('mtc_issued_date', sa.Date(), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('member_certificates')
    op.drop_table('member_expertise')
