# Example Question 1 — Electronics Return Window

## Question

> "What is the return window for electronics, and does a restocking fee apply?"

---

## Expected Output

### Answer

Electronics and high-value items with a unit price above $500 have a **15-day return window** from the confirmed delivery date. Standard items carry a 30-day window, but electronics fall under the shorter window regardless of the reason for return. A **10% restocking fee** applies to any order over $200 returned for reasons other than defect or damage. This fee is waived entirely for customers with a Gold or Platinum account tier.

### Supporting Evidence

- Electronics return window is 15 days from confirmed delivery date, shorter than the standard 30-day window for items priced above $500.
  *(source: returns_and_refunds_policy.txt)*

- A 10% restocking fee applies to orders over $200 returned for reasons other than defect or damage. The fee is waived for Gold and Platinum account tier customers.
  *(source: returns_and_refunds_policy.txt)*

- Items arriving damaged or defective may be reported within 72 hours for a full replacement or refund, with no return required unless the unit value exceeds $300.
  *(source: returns_and_refunds_policy.txt)*

- All electronics carry a 12-month manufacturer warranty; warranty claims go directly through the manufacturer and do not use the standard returns flow.
  *(source: product_notes_electronics.txt)*

### Gaps and Unverified Items

None. The returns policy explicitly covers electronics, and the restocking fee conditions are stated without ambiguity.

---

## Tool Calls Evidence

| Step | Agent | Tool | Input | Key Output |
|------|-------|------|-------|------------|
| 1 | Researcher | `search_documents` | `query="electronics return"` | Hit: `returns_and_refunds_policy.txt` (3 matches), `product_notes_electronics.txt` (1 match) |
| 2 | Researcher | `search_documents` | `query="restocking fee"` | Hit: `returns_and_refunds_policy.txt` (2 matches) |
| 3 | Analyst | `search_documents` | `query="warranty electronics"` | Hit: `product_notes_electronics.txt` (1 match) |
| 4 | Writer | `save_report` | `title="Electronics Return Window Q&A"` | `REPORT SAVED: outputs/reports/..._electronics_return_window_q_a.md` |

---

## Grounding Check

| Claim in answer | Traceable to source? |
|----------------|----------------------|
| 15-day window for electronics > $500 | ✅ `returns_and_refunds_policy.txt` line 14 |
| 30-day window for standard items | ✅ `returns_and_refunds_policy.txt` line 13 |
| 10% restocking fee on orders > $200 | ✅ `returns_and_refunds_policy.txt` line 36 |
| Fee waived for Gold/Platinum | ✅ `returns_and_refunds_policy.txt` line 37 |
| 72-hour window for damage/defect claims | ✅ `returns_and_refunds_policy.txt` lines 27–30 |
| 12-month manufacturer warranty | ✅ `product_notes_electronics.txt` line 34 |
