"""empty message

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 创建客户表
    op.create_table('customer',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('customer_code', sa.String(length=50), nullable=False),
        sa.Column('customer_name', sa.String(length=200), nullable=False),
        sa.Column('customer_short_name', sa.String(length=100), nullable=True),
        sa.Column('industry', sa.String(length=50), nullable=True),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('customer_level', sa.String(length=20), nullable=True),
        sa.Column('customer_status', sa.String(length=20), nullable=False),
        sa.Column('sales_user_id', sa.BigInteger(), nullable=True),
        sa.Column('operation_user_id', sa.BigInteger(), nullable=True),
        sa.Column('first_deal_time', sa.DateTime(), nullable=True),
        sa.Column('last_follow_time', sa.DateTime(), nullable=True),
        sa.Column('current_resource_count', sa.Integer(), nullable=True),
        sa.Column('current_month_consumption', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('next_month_forecast', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('source_system', sa.String(length=50), nullable=True),
        sa.Column('source_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_id'), 'customer', ['id'], unique=False)
    op.create_index('idx_customer_code', 'customer', ['customer_code'], unique=False)
    op.create_index('idx_customer_status', 'customer', ['customer_status'], unique=False)
    op.create_index('idx_sales_user', 'customer', ['sales_user_id'], unique=False)

    # 创建客户联系人表
    op.create_table('customer_contact',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('customer_id', sa.BigInteger(), nullable=False),
        sa.Column('contact_name', sa.String(length=100), nullable=False),
        sa.Column('contact_title', sa.String(length=50), nullable=True),
        sa.Column('contact_phone', sa.String(length=20), nullable=True),
        sa.Column('contact_email', sa.String(length=100), nullable=True),
        sa.Column('contact_wechat', sa.String(length=50), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_contact_id'), 'customer_contact', ['id'], unique=False)
    op.create_index('idx_contact_customer', 'customer_contact', ['customer_id'], unique=False)

    # 创建货源表
    op.create_table('resource',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('resource_code', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=20), nullable=False),
        sa.Column('cloud_provider', sa.String(length=20), nullable=True),
        sa.Column('identifier_field', sa.String(length=200), nullable=True),
        sa.Column('account_name', sa.String(length=200), nullable=True),
        sa.Column('definition_name', sa.String(length=200), nullable=True),
        sa.Column('cloud_account_id', sa.String(length=100), nullable=True),
        sa.Column('total_quantity', sa.Integer(), nullable=True),
        sa.Column('allocated_quantity', sa.Integer(), nullable=True),
        sa.Column('available_quantity', sa.Integer(), nullable=True),
        sa.Column('unit_cost', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('suggested_price', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('resource_status', sa.String(length=20), nullable=False),
        sa.Column('source_system', sa.String(length=50), nullable=True),
        sa.Column('source_id', sa.String(length=100), nullable=True),
        sa.Column('last_sync_time', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resource_id'), 'resource', ['id'], unique=False)
    op.create_index('idx_resource_type', 'resource', ['resource_type'], unique=False)
    op.create_index('idx_resource_status', 'resource', ['resource_status'], unique=False)
    op.create_index('idx_cloud_provider', 'resource', ['cloud_provider'], unique=False)

    # 创建分配表
    op.create_table('allocation',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('allocation_code', sa.String(length=50), nullable=False),
        sa.Column('customer_id', sa.BigInteger(), nullable=False),
        sa.Column('resource_id', sa.BigInteger(), nullable=False),
        sa.Column('allocated_quantity', sa.Integer(), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('unit_price', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('total_price', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('profit_amount', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('profit_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('allocation_status', sa.String(length=20), nullable=False),
        sa.Column('allocated_by', sa.BigInteger(), nullable=True),
        sa.Column('allocated_at', sa.DateTime(), nullable=True),
        sa.Column('delivery_status', sa.String(length=20), nullable=True),
        sa.Column('delivery_at', sa.DateTime(), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ),
        sa.ForeignKeyConstraint(['resource_id'], ['resource.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_allocation_id'), 'allocation', ['id'], unique=False)
    op.create_index('idx_allocation_customer', 'allocation', ['customer_id'], unique=False)
    op.create_index('idx_allocation_resource', 'allocation', ['resource_id'], unique=False)
    op.create_index('idx_allocation_status', 'allocation', ['allocation_status'], unique=False)

    # 创建用量记录表
    op.create_table('usage_record',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('customer_id', sa.BigInteger(), nullable=False),
        sa.Column('resource_id', sa.BigInteger(), nullable=False),
        sa.Column('allocation_id', sa.BigInteger(), nullable=True),
        sa.Column('usage_date', sa.DateTime(), nullable=False),
        sa.Column('usage_amount', sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column('usage_cost', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('source_system', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_record_id'), 'usage_record', ['id'], unique=False)
    op.create_index('idx_usage_customer', 'usage_record', ['customer_id'], unique=False)
    op.create_index('idx_usage_resource', 'usage_record', ['resource_id'], unique=False)
    op.create_index('idx_usage_date', 'usage_record', ['usage_date'], unique=False)


def downgrade():
    op.drop_table('usage_record')
    op.drop_table('allocation')
    op.drop_table('resource')
    op.drop_table('customer_contact')
    op.drop_table('customer')
