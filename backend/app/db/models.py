"""Star-ish schema for the SmartHealth Consumer Analytics synthetic dataset.

Facts:      sales, inventory (daily snapshot), marketing, purchase_orders
Dimensions: products, customers, regions, suppliers, channels

The schema is deliberately shaped so that a root cause can be *traced* across
tables:  supplier lead time -> purchase order delay -> inventory stockout ->
lost demand -> revenue decline.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Date, Float, ForeignKey, Index, Integer, MetaData, String, Table,
)

metadata = MetaData()

regions = Table(
    "regions", metadata,
    Column("region_id", String(8), primary_key=True),
    Column("region_name", String(32), nullable=False),
    Column("country", String(32), nullable=False),
    Column("warehouse_id", String(8), nullable=False),
)

suppliers = Table(
    "suppliers", metadata,
    Column("supplier_id", String(8), primary_key=True),
    Column("supplier_name", String(64), nullable=False),
    Column("country", String(32), nullable=False),
    Column("standard_lead_time_days", Integer, nullable=False),
    Column("reliability_score", Float, nullable=False),  # 0-1, historical on-time rate
)

products = Table(
    "products", metadata,
    Column("product_id", String(8), primary_key=True),
    Column("product_name", String(64), nullable=False),
    Column("category", String(32), nullable=False),
    Column("subcategory", String(32), nullable=False),
    Column("unit_price", Float, nullable=False),   # list price, INR
    Column("unit_cost", Float, nullable=False),    # COGS, INR
    Column("supplier_id", String(8), ForeignKey("suppliers.supplier_id"), nullable=False),
    Column("launch_date", Date, nullable=False),
)

channels = Table(
    "channels", metadata,
    Column("channel_id", String(8), primary_key=True),
    Column("channel_name", String(32), nullable=False),
)

customers = Table(
    "customers", metadata,
    Column("customer_id", String(12), primary_key=True),
    Column("segment", String(16), nullable=False),      # Premium/Regular/New/Enterprise
    Column("region_id", String(8), ForeignKey("regions.region_id"), nullable=False),
    Column("age_group", String(8), nullable=False),
    Column("acquisition_channel", String(24), nullable=False),
    Column("signup_date", Date, nullable=False),
)

sales = Table(
    "sales", metadata,
    Column("sale_id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("product_id", String(8), ForeignKey("products.product_id"), nullable=False),
    Column("customer_id", String(12), ForeignKey("customers.customer_id"), nullable=False),
    Column("region_id", String(8), ForeignKey("regions.region_id"), nullable=False),
    Column("channel_id", String(8), ForeignKey("channels.channel_id"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("discount_pct", Float, nullable=False),
    Column("revenue", Float, nullable=False),
    Column("cost", Float, nullable=False),
    Column("profit", Float, nullable=False),
)

inventory = Table(
    "inventory", metadata,
    Column("inventory_id", Integer, primary_key=True, autoincrement=True),
    Column("date", Date, nullable=False),
    Column("product_id", String(8), ForeignKey("products.product_id"), nullable=False),
    Column("warehouse_id", String(8), nullable=False),
    Column("region_id", String(8), ForeignKey("regions.region_id"), nullable=False),
    Column("opening_stock", Integer, nullable=False),
    Column("units_received", Integer, nullable=False),
    Column("units_sold", Integer, nullable=False),
    Column("units_lost", Integer, nullable=False),      # demand that could not be served
    Column("closing_stock", Integer, nullable=False),
    Column("stockout", Boolean, nullable=False),
)

marketing = Table(
    "marketing", metadata,
    Column("campaign_id", String(24), primary_key=True),
    Column("date", Date, nullable=False),              # first day of the campaign month
    Column("product_id", String(8), ForeignKey("products.product_id"), nullable=False),
    Column("region_id", String(8), ForeignKey("regions.region_id"), nullable=False),
    Column("channel", String(24), nullable=False),
    Column("spend", Float, nullable=False),
    Column("impressions", Integer, nullable=False),
    Column("clicks", Integer, nullable=False),
    Column("conversions", Integer, nullable=False),
)

purchase_orders = Table(
    "purchase_orders", metadata,
    Column("po_id", String(20), primary_key=True),
    Column("order_date", Date, nullable=False),
    Column("product_id", String(8), ForeignKey("products.product_id"), nullable=False),
    Column("supplier_id", String(8), ForeignKey("suppliers.supplier_id"), nullable=False),
    Column("warehouse_id", String(8), nullable=False),
    Column("region_id", String(8), ForeignKey("regions.region_id"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("promised_date", Date, nullable=False),
    Column("received_date", Date, nullable=False),
    Column("delay_days", Integer, nullable=False),
)

Index("ix_sales_date", sales.c.date)
Index("ix_sales_product_date", sales.c.product_id, sales.c.date)
Index("ix_sales_region_date", sales.c.region_id, sales.c.date)
Index("ix_inventory_product_date", inventory.c.product_id, inventory.c.date)
Index("ix_marketing_product_date", marketing.c.product_id, marketing.c.date)
Index("ix_po_product_date", purchase_orders.c.product_id, purchase_orders.c.order_date)

ALL_TABLES = [
    "regions", "suppliers", "products", "channels", "customers",
    "sales", "inventory", "marketing", "purchase_orders",
]
