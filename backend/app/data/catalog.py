"""Reference data for the *SmartHealth Consumer Analytics* synthetic dataset.

SYNTHETIC DATA NOTICE: every entity below is fictional and generated purely for
demonstration.  It is not Philips data and does not represent any real company.
"""
from __future__ import annotations

REGIONS = [
    # region_id, name, country, warehouse, demand weight
    ("NORTH",   "North",   "India", "WH-N", 0.28),
    ("SOUTH",   "South",   "India", "WH-S", 0.22),
    ("WEST",    "West",    "India", "WH-W", 0.24),
    ("EAST",    "East",    "India", "WH-E", 0.14),
    ("CENTRAL", "Central", "India", "WH-C", 0.12),
]

SUPPLIERS = [
    # id, name, country, standard_lead_time_days, reliability_score
    ("SUP01", "OralCare Devices Pvt Ltd",  "India",   10, 0.95),
    ("SUP02", "MediSense Instruments",     "India",   12, 0.93),
    ("SUP03", "AirTech Components Co",     "China",   14, 0.88),
    ("SUP04", "GroomWell Manufacturing",   "India",    9, 0.96),
    ("SUP05", "SonicWave Electronics",     "Vietnam", 16, 0.91),
    ("SUP06", "KitchenPro Industries",     "India",   11, 0.94),
]

CHANNELS = [
    ("CH01", "Online D2C",     0.30),
    ("CH02", "Marketplace",    0.28),
    ("CH03", "Retail Partner", 0.27),
    ("CH04", "Modern Trade",   0.15),
]

SEGMENTS = [
    # name, share of customer base, avg units per order, discount appetite
    ("Premium",    0.18, 1.15, 0.03),
    ("Regular",    0.46, 1.10, 0.07),
    ("New",        0.24, 1.05, 0.11),
    ("Enterprise", 0.12, 2.60, 0.13),
]

AGE_GROUPS = [("18-25", 0.16), ("26-35", 0.34), ("36-45", 0.26), ("46-60", 0.17), ("60+", 0.07)]

ACQUISITION_CHANNELS = [
    ("Paid Search", 0.24), ("Social", 0.21), ("Organic", 0.19),
    ("Retail Walk-in", 0.20), ("Referral", 0.10), ("Email", 0.06),
]

# Monthly seasonality multipliers, index 0 = January.
SEASONALITY = {
    # Air quality demand peaks Oct-Jan (winter pollution); Jun and Jul are an
    # equally soft shoulder, so a Jun->Jul move is NOT explained by seasonality.
    "air":      [1.28, 1.18, 1.00, 0.90, 0.88, 0.90, 0.90, 0.94, 1.02, 1.22, 1.34, 1.30],
    "health":   [1.06, 1.00, 0.98, 0.97, 0.98, 0.99, 1.00, 1.00, 1.01, 1.04, 1.05, 1.02],
    "grooming": [0.96, 0.98, 1.02, 1.04, 1.02, 0.99, 0.98, 1.00, 1.04, 1.16, 1.12, 1.05],
    "audio":    [0.95, 0.97, 1.00, 1.02, 1.01, 0.99, 0.99, 1.01, 1.05, 1.18, 1.14, 1.06],
    "kitchen":  [1.02, 1.00, 0.99, 1.00, 1.02, 1.01, 1.00, 1.00, 1.03, 1.12, 1.08, 1.04],
    "smart":    [0.98, 0.99, 1.00, 1.01, 1.01, 1.00, 1.00, 1.01, 1.03, 1.14, 1.10, 1.05],
}

# product_id, name, category, subcategory, price, cost, supplier, revenue share, season key,
# stock policy (target days of cover, safety days)
PRODUCTS = [
    ("P101", "SmartCare Sonic Toothbrush Pro", "Personal Health", "Oral Care",      9999,  6700, "SUP01", 0.070, "health",   30, 8),
    ("P102", "SmartCare Kids Sonic Brush",     "Personal Health", "Oral Care",      3499,  2250, "SUP01", 0.030, "health",   30, 8),
    ("P103", "SmartAir Purifier 3000i",        "Home Environment","Air Treatment", 24999, 16800, "SUP03", 0.160, "air",      18, 3),
    ("P104", "SmartAir Compact 800i",          "Home Environment","Air Treatment", 12499,  8600, "SUP03", 0.045, "air",      28, 8),
    ("P105", "SmartCare Water Flosser",        "Personal Health", "Oral Care",      5999,  3900, "SUP01", 0.035, "health",   30, 8),
    ("P106", "SmartAir Humidifier H2",         "Home Environment","Air Treatment",  8999,  6100, "SUP03", 0.025, "air",      30, 9),
    ("P107", "SmartVital BP Monitor",          "Personal Health", "Diagnostics",    4299,  2800, "SUP02", 0.030, "health",   32, 9),
    ("P108", "SmartVital Thermometer",         "Personal Health", "Diagnostics",    1199,   700, "SUP02", 0.012, "health",   32, 9),
    ("P109", "SmartAir Quality Monitor",       "Home Environment","Air Treatment",  6499,  4300, "SUP03", 0.020, "air",      30, 9),
    ("P110", "GroomEdge Beard Trimmer 5000",   "Grooming",        "Trimmers",       2499,  1500, "SUP04", 0.045, "grooming", 28, 7),
    ("P111", "GroomEdge Multigroom 7000",      "Grooming",        "Trimmers",       4999,  3100, "SUP04", 0.040, "grooming", 28, 7),
    ("P112", "GroomEdge Hair Dryer Pro",       "Grooming",        "Hair Care",      3299,  2050, "SUP04", 0.030, "grooming", 28, 7),
    ("P113", "GroomEdge Straightener S3",      "Grooming",        "Hair Care",      2999,  1850, "SUP04", 0.025, "grooming", 28, 7),
    ("P114", "GroomEdge Shaver S7000",         "Grooming",        "Shavers",       12999,  8700, "SUP04", 0.050, "grooming", 26, 7),
    ("P115", "PureSound Soundbar 300",         "Audio",           "Home Audio",    15999, 11200, "SUP05", 0.050, "audio",    34, 10),
    ("P116", "PureSound Earbuds T2",           "Audio",           "Personal Audio", 4999,  3150, "SUP05", 0.050, "audio",    34, 10),
    ("P117", "PureSound Headphones H9",        "Audio",           "Personal Audio", 9999,  6800, "SUP05", 0.035, "audio",    34, 10),
    ("P118", "PureSound Speaker BT50",         "Audio",           "Personal Audio", 2999,  1900, "SUP05", 0.025, "audio",    34, 10),
    ("P119", "ChefLine Coffee Machine 2200",   "Kitchen",         "Beverage",      18999, 13100, "SUP06", 0.040, "kitchen",  30, 8),
    ("P120", "ChefLine Air Fryer XL",          "Kitchen",         "Cooking",        9499,  6300, "SUP06", 0.045, "kitchen",  30, 8),
    ("P121", "ChefLine Blender Pro",           "Kitchen",         "Cooking",        4499,  2900, "SUP06", 0.025, "kitchen",  30, 8),
    ("P122", "ChefLine Electric Kettle",       "Kitchen",         "Beverage",       1799,  1050, "SUP06", 0.015, "kitchen",  30, 8),
    ("P123", "LumaHome Smart Lamp",            "Smart Home",      "Lighting",       3999,  2500, "SUP05", 0.022, "smart",    32, 9),
    ("P124", "LumaHome Smart Plug Mini",       "Smart Home",      "Lighting",        999,   560, "SUP05", 0.008, "smart",    32, 9),
]

# Company-level scale knob: average revenue per day at the start of history.
TARGET_DAILY_REVENUE = 4.20e7 / 30.44   # ~ INR 4.2 Cr / month

HERO_PRODUCT = "P103"
HERO_SUPPLIER = "SUP03"
