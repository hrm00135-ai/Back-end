"""add task_id is_advance invoice_url to payment_transactions

Revision ID: f7b2c4d8e9a1
Revises: aac9ab681369
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa

revision = 'f7b2c4d8e9a1'
down_revision = 'aac9ab681369'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('is_advance', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('invoice_url', sa.String(500), nullable=True))
        try:
            batch_op.create_foreign_key(
                'fk_payment_tx_task', 'tasks', ['task_id'], ['id'],
                ondelete='SET NULL'
            )
        except Exception:
            pass  # FK may already exist or DB may not support named FKs in batch


def downgrade():
    with op.batch_alter_table('payment_transactions', schema=None) as batch_op:
        try:
            batch_op.drop_constraint('fk_payment_tx_task', type_='foreignkey')
        except Exception:
            pass
        batch_op.drop_column('invoice_url')
        batch_op.drop_column('is_advance')
        batch_op.drop_column('task_id')
