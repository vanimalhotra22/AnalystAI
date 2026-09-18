# Inventory & Replenishment Policy (SYNTHETIC / DEMO)

*Fictional internal policy written for the SmartHealth Consumer Analytics demo dataset.*

## 1. Product classification
Products are classified by trailing 90-day revenue contribution:
- **Class A** - top 20% of revenue. Availability is business critical.
- **Class B** - next 30% of revenue.
- **Class C** - the remaining long tail.

## 2. Safety stock norms
- Class A products must hold safety stock equal to **at least 15% of lead-time demand**,
  and never fewer than **5 days of cover**.
- Class B products hold at least 10% of lead-time demand.
- For imported products (supplier outside India), add **3 additional days** of cover to
  absorb customs and port variability.
- Safety stock is reviewed monthly, and after any supplier delay above 5 days.

## 3. Reorder discipline
- Reorder point = forecast daily demand x (standard lead time + safety days).
- A replenishment order must be raised on the same working day the reorder point is crossed.
- Only one open purchase order per product-warehouse is permitted, so a delayed
  consignment is not silently compensated by a second order.

## 4. Stockout alerting
- A **low-stock alert** must be raised when projected cover falls below **7 days of
  forecast demand**.
- A **critical alert** is raised at 3 days of cover and goes to the category manager and
  the supply planner together.
- Any Class A product with more than **2 consecutive stockout days** requires a written
  root-cause note in the monthly supply review.

## 5. Service level targets
- Target fill rate (units served / units demanded) is **97% for Class A**, 95% for Class B.
- Fill rate below 90% for a calendar month is treated as a service incident.

## 6. Emergency measures
- Air freight may be used for Class A replenishment when the projected stockout exceeds
  5 days; approval sits with the supply chain director.
- Inter-warehouse stock transfer is the preferred first response when one region is at
  zero stock and another holds more than 20 days of cover.
