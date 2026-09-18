# Revenue Reporting Standard (SYNTHETIC / DEMO)

*Fictional internal reporting standard written for the SmartHealth Consumer Analytics demo dataset.*

## 1. Definitions
- **Revenue** - net of discount, excluding tax and freight (`sales.revenue`).
- **Units** - `sales.quantity`.
- **AOV** - revenue divided by order count.
- **Realised price per unit** - revenue divided by units.
- **Fill rate** - units served divided by units demanded (served + unserved).

## 2. Period comparison rules
- The default management comparison is the **latest complete calendar month versus the
  immediately preceding calendar month**.
- Because calendar months differ in length, every month-on-month revenue movement must be
  reported **both as a total and as a revenue-per-day rate**. The per-day rate is the
  like-for-like figure.
- Where a movement may be seasonal, the same month in the prior year must also be shown.

## 3. Attribution rules
- Contribution to change is measured in absolute currency, not in percentage change, so
  that small, volatile lines do not dominate the explanation.
- An explanation must state how much of the total change it accounts for, and the
  remainder must be reported explicitly as unexplained.

## 4. Evidence standard
- Every stated cause must cite the source table and the period it was measured over.
- Correlation observed in a single month is described as **evidence**, not as proof of
  causation, unless a mechanism is also demonstrated - for example unserved demand
  recorded in the inventory ledger.
