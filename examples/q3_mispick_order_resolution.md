# Example Question 3 — Mispick Order Resolution

## Question

> "What happened with the mispick on order ORD-01047, and what are the consequences for the staff member involved?"

---

## Expected Output

### Answer

Order **ORD-01047** (account ACC-3340, Gold tier) was a mispick: the customer ordered 5 × OF-20045 (Ballpoint Pen Multipack 10-pack) but received 5 × OF-20310 (Ergonomic Desk Organiser) instead. The OMS scanner log confirmed the wrong SKU was scanned at the packing station by staff member **WH-14**. A correct replacement of 5 × OF-20045 was dispatched the same day under **ORD-01063** (expedited, no charge). A prepaid return label was issued for the desk organisers, which were received back at the warehouse on 2025-11-05 and restocked.

Regarding staff consequences: this was WH-14's **second mispick in November**. Under the warehouse dispatch procedure, three mispicks in a single month by the same staff member trigger mandatory retraining. WH-14 has been flagged for a retraining review. The ticket also recommends the supervisor review the picking station layout, as OF-20045 and OF-20310 are stored in adjacent bins on Shelf Row 7 — a likely root cause of the repeated confusion.

Because ACC-3340 holds a Gold account tier, the restocking fee (normally 10% on orders over $200 returned for non-defect reasons) does not apply. The order total of $34.95 is below the $200 restocking threshold in any case.

### Supporting Evidence

- Order ORD-01047: ACC-3340 (Gold), 5 × OF-20045, order total $34.95, delivered 2025-11-09, return_requested=No. Notes: "Mispick resolved; correct items resent under ORD-01063."
  *(source: records.csv, order ORD-01047)*

- Order ORD-01063: replacement for mispick ORD-01047, 5 × OF-20045, dispatched 2025-11-09, unit price $0.00, expedited no charge, delivery status Delivered.
  *(source: records.csv, order ORD-01063)*

- Scanner log confirmed OF-20310 was scanned instead of OF-20045 by staff member WH-14. This is WH-14's second mispick in November.
  *(source: support_ticket_ST-0055.txt)*

- Correct items dispatched same day under ORD-01063 (expedited, no charge). Return label issued; desk organisers received back and restocked 2025-11-05.
  *(source: support_ticket_ST-0055.txt)*

- WH-14 flagged for retraining review. Warehouse procedure states three mispicks in a month by the same staff member triggers retraining.
  *(source: support_ticket_ST-0055.txt, warehouse_dispatch_procedure.txt)*

- OF-20045 and OF-20310 stored in adjacent bins on Shelf Row 7. Relabelling or bin separation recommended.
  *(source: support_ticket_ST-0055.txt)*

- Restocking fee of 10% applies to orders over $200 for non-defect returns; fee waived for Gold and Platinum tier customers.
  *(source: returns_and_refunds_policy.txt)*

### Gaps and Unverified Items

- The retraining review outcome for WH-14 is not yet recorded in the available documents (ticket ST-0055 was closed before the review concluded).
- Whether the supervisor acted on the bin separation recommendation is not documented in the current corpus.

---

## Tool Calls Evidence

| Step | Agent | Tool | Input | Key Output |
|------|-------|------|-------|------------|
| 1 | Researcher | `search_documents` | `query="mispick ORD-01047"` | Hit: `support_ticket_ST-0055.txt` (3 matches) |
| 2 | Researcher | `search_documents` | `query="mispick retraining procedure"` | Hit: `warehouse_dispatch_procedure.txt` (2 matches), `support_ticket_ST-0055.txt` (1 match) |
| 3 | Analyst | `read_record` | `order_id="ORD-01047"` | Gold tier, OF-20045, $34.95, mispick note confirmed |
| 4 | Analyst | `read_record` | `order_id="ORD-01063"` | Replacement, $0.00, expedited, delivered |
| 5 | Analyst | `search_documents` | `query="restocking fee Gold tier"` | Hit: `returns_and_refunds_policy.txt` (2 matches) |
| 6 | Writer | `save_report` | `title="Mispick ORD-01047 Resolution and Staff Review"` | `REPORT SAVED: outputs/reports/..._mispick_ord_01047_resolution_and_staff_review.md` |

---

## Grounding Check

| Claim in answer | Traceable to source? |
|----------------|----------------------|
| Wrong item sent: OF-20310 instead of OF-20045 | ✅ `support_ticket_ST-0055.txt` lines 16–17 |
| Staff member WH-14 confirmed by scanner log | ✅ `support_ticket_ST-0055.txt` lines 21–22 |
| Second mispick for WH-14 in November | ✅ `support_ticket_ST-0055.txt` line 24 |
| Replacement ORD-01063, same day, expedited, no charge | ✅ `records.csv, order ORD-01063` + `support_ticket_ST-0055.txt` line 27 |
| Return received and restocked 2025-11-05 | ✅ `support_ticket_ST-0055.txt` (ticket closed note) |
| 3 mispicks = retraining trigger | ✅ `warehouse_dispatch_procedure.txt` line 42 |
| WH-14 flagged for retraining review | ✅ `support_ticket_ST-0055.txt` lines 34–35 |
| Adjacent bins on Shelf Row 7 root cause | ✅ `support_ticket_ST-0055.txt` lines 38–40 |
| Restocking fee waived for Gold tier | ✅ `returns_and_refunds_policy.txt` line 37 |
