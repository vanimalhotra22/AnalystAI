# Supplier Management Policy (SYNTHETIC / DEMO)

*Fictional internal policy written for the SmartHealth Consumer Analytics demo dataset.*

## 1. Lead time commitments
- Every supplier has a contracted standard lead time recorded in the supplier master.
- Deliveries arriving more than **2 days** after the promised date count as late.
- Rolling 90-day on-time delivery below **90%** places the supplier on watch status.

## 2. Escalation thresholds
- Average delay above **5 days** in any calendar month triggers a formal escalation to
  the supplier account manager within 5 working days.
- A single delay above **10 days** on a Class A product requires an incident review and a
  written recovery plan from the supplier.

## 3. Dual sourcing
- Any product where a single supplier covers more than 60% of volume, and whose
  reliability score is below **0.90**, must have a qualified secondary source.
- Secondary sources are re-qualified annually.

## 4. Buffer strategy for imports
- Imported categories carry additional in-transit buffer stock, because customs holds are
  the dominant source of variance.
- Where a supplier's delay variance exceeds 4 days, planning must use the **85th
  percentile** lead time rather than the contracted lead time.

## 5. Commercial remedies
- Contracts include a service credit for late delivery on Class A products.
- Repeated escalations within a rolling quarter are reviewed for volume reallocation.

## 6. Monitoring
- Supplier lead-time variance is monitored weekly.
- The supply review pack reports promised vs received date, delay days, affected
  warehouses, and the downstream stockout days attributable to each late consignment.
