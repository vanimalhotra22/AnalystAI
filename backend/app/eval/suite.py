"""Evaluation suite.

Thirty-four business questions with machine-checkable expectations.  The point is
not to score prose: it is to check that the agent (a) understood the question,
(b) reached for the right evidence, (c) produced numbers that match an
independent SQL query, and (d) ruled out what it should rule out.

Expectation keys
  intent          expected classification
  tools_any       at least one of these tools must have been called
  tools_all       all of these tools must have been called
  facts_present   these fact keys must exist and be non-null
  facts_equal     these fact keys must equal the given value
  period_label    the period the agent resolved from the question
  comparison_label the comparison period it resolved
  root_cause      expected root-cause hypothesis key
  ruled_out       hypotheses that must come back 'ruled_out'
  max_steps       investigation budget for this question
"""
from __future__ import annotations

SUITE = [
    # ---------------------------------------------------------- root cause
    {"id": "Q01", "question": "Revenue decreased this month. Find out why and recommend what we should do.",
     "expect": {"intent": "action", "root_cause": "inventory_stockout",
                "tools_all": ["get_revenue_summary", "get_breakdown", "check_demand_vs_served",
                              "get_supplier_performance", "quantify_impact", "search_policy"],
                "facts_equal": {"worst_region": "NORTH", "worst_product": "P103"},
                "ruled_out": ["pricing_discounting", "customer_churn"], "max_steps": 15}},
    {"id": "Q02", "question": "Why did revenue decline in July 2026?",
     "expect": {"intent": "root_cause", "root_cause": "inventory_stockout",
                "facts_present": ["revenue_pct_change", "fill_rate_pct", "stockout_days"]}},
    {"id": "Q03", "question": "What is behind the drop in sales last month?",
     "expect": {"intent": "root_cause", "tools_any": ["get_breakdown"]}},
    {"id": "Q04", "question": "Explain the revenue movement between June and July.",
     "expect": {"intent": "root_cause", "facts_present": ["revenue_delta"]}},
    {"id": "Q05", "question": "What caused the North region to underperform?",
     "expect": {"intent": "root_cause", "facts_equal": {"worst_region": "NORTH"}}},

    # --------------------------------------------------------- descriptive
    {"id": "Q06", "question": "Which region performed worst last month?",
     "expect": {"intent": "descriptive", "tools_any": ["get_breakdown"],
                "facts_equal": {"worst_region": "NORTH"}, "max_steps": 4}},
    {"id": "Q07", "question": "Show me the revenue trend over the last year.",
     "expect": {"intent": "descriptive", "tools_all": ["get_trend"], "max_steps": 3}},
    {"id": "Q08", "question": "Which products have abnormal inventory?",
     "expect": {"intent": "descriptive", "tools_any": ["get_inventory_health", "detect_anomalies"],
                "facts_present": ["stockout_days"], "max_steps": 4}},
    {"id": "Q09", "question": "Is our supplier delivery performance getting worse?",
     "expect": {"intent": "descriptive", "tools_all": ["get_supplier_performance"],
                "facts_present": ["supplier_avg_delay_days"], "max_steps": 4}},
    {"id": "Q10", "question": "How did marketing spend change in North?",
     "expect": {"intent": "descriptive", "tools_all": ["get_marketing_performance"], "max_steps": 4}},
    {"id": "Q11", "question": "Did we change pricing or discounts recently?",
     "expect": {"intent": "descriptive", "tools_all": ["check_pricing"], "max_steps": 4}},
    {"id": "Q12", "question": "How many active customers did we have in July 2026?",
     "expect": {"intent": "descriptive", "tools_any": ["get_customer_metrics"], "max_steps": 4}},
    {"id": "Q13", "question": "Which products declined the most?",
     "expect": {"intent": "descriptive", "tools_any": ["get_breakdown"],
                "facts_equal": {"worst_product": "P103"}, "max_steps": 4}},
    {"id": "Q14", "question": "What was total revenue in June 2026?",
     "expect": {"intent": "descriptive", "tools_any": ["get_revenue_summary"], "max_steps": 4,
                "period_label": "June 2026"}},
    {"id": "Q15", "question": "Show inventory for SmartAir Purifier 3000i in North.",
     "expect": {"intent": "descriptive", "tools_any": ["get_inventory_health"],
                "facts_present": ["stockout_days"], "max_steps": 4}},
    {"id": "Q16", "question": "How did the Home Environment category perform?",
     "expect": {"intent": "descriptive", "max_steps": 4}},
    {"id": "Q17", "question": "Which region had the strongest growth?",
     "expect": {"intent": "descriptive", "tools_any": ["get_breakdown"], "max_steps": 4}},

    # ------------------------------------------------------------- product
    {"id": "Q18", "question": "Why did SmartAir Purifier 3000i revenue fall in North?",
     "expect": {"intent": "root_cause", "root_cause": "inventory_stockout",
                "facts_present": ["fill_rate_pct"],
                "tools_all": ["check_demand_vs_served", "get_supplier_performance"]}},
    {"id": "Q19", "question": "Why is P103 selling less than usual?",
     "expect": {"intent": "root_cause", "facts_present": ["fill_rate_pct"]}},
    {"id": "Q20", "question": "Did the marketing spend cut in North hurt revenue?",
     "expect": {"intent": "descriptive", "tools_all": ["get_marketing_performance"], "max_steps": 4}},
    {"id": "Q21", "question": "Which supplier caused the delays?",
     "expect": {"intent": "root_cause", "tools_any": ["get_supplier_performance"],
                "facts_present": ["worst_po_supplier"]}},

    # -------------------------------------------------------------- action
    {"id": "Q22", "question": "What should we do about the revenue decline?",
     "expect": {"intent": "action", "root_cause": "inventory_stockout",
                "tools_all": ["search_policy"], "max_steps": 15}},
    {"id": "Q23", "question": "Recommend actions to protect revenue next month.",
     "expect": {"intent": "action", "tools_any": ["search_policy"], "max_steps": 15}},
    {"id": "Q24", "question": "How do we stop this happening again?",
     "expect": {"intent": "action", "tools_any": ["search_policy"], "max_steps": 15}},

    # ------------------------------------------------------------- what-if
    {"id": "Q25", "question": "What if we increase safety stock by 15% for P103 in North?",
     "expect": {"intent": "what_if", "tools_all": ["simulate_safety_stock"],
                "facts_present": ["whatif_net_benefit"], "max_steps": 6}},
    {"id": "Q26", "question": "Simulate raising safety stock by 25% for P103 in North.",
     "expect": {"intent": "what_if", "tools_all": ["simulate_safety_stock"], "max_steps": 6}},
    {"id": "Q27", "question": "What if we increase inventory for SmartAir Purifier 3000i in North?",
     "expect": {"intent": "what_if", "tools_any": ["simulate_safety_stock"], "max_steps": 6}},

    # --------------------------------------------------------- period care
    {"id": "Q28", "question": "Why did revenue decline in 2026-07 versus 2026-06?",
     "expect": {"intent": "root_cause", "facts_present": ["revenue_per_day_pct_change"]}},
    # The period is read out of the question text - no API argument is passed.
    {"id": "Q29", "question": "Which region performed worst in Q2 2026?",
     "expect": {"intent": "descriptive", "tools_any": ["get_breakdown"], "max_steps": 4,
                "period_label": "Q2 2026"}},
    {"id": "Q30", "question": "Compare July 2026 with the same month last year.",
     "expect": {"intent": "descriptive", "max_steps": 4,
                "period_label": "July 2026", "comparison_label": "July 2025"}},

    # -------------------------------------------------------------- robust
    {"id": "Q31", "question": "Tell me something interesting.",
     "expect": {"intent": "descriptive", "max_steps": 4}},
    {"id": "Q32", "question": "Why did revenue decline in East?",
     "expect": {"intent": "root_cause", "facts_equal": {"breakdown_scope_region": "EAST"}}},
    {"id": "Q33", "question": "Was the decline caused by customers leaving us?",
     "expect": {"intent": "root_cause", "tools_any": ["get_customer_metrics"],
                "ruled_out": ["customer_churn"]}},
    {"id": "Q34", "question": "Was the decline caused by discounting?",
     "expect": {"intent": "root_cause", "tools_any": ["check_pricing"],
                "ruled_out": ["pricing_discounting"]}},
]
