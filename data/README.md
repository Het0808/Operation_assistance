# Data Directory

Synthetic operational data for the Operations Assistant project.
All names, accounts, and order numbers are fictional.

---

## documents/

| File | Type | Contents |
|------|------|----------|
| `returns_and_refunds_policy.txt` | Policy | Return windows, condition requirements, refund timelines, restocking fees |
| `shipping_and_delivery_policy.txt` | Policy | Shipping tiers, free shipping threshold, address change rules, failed delivery handling |
| `low_stock_reorder_policy.txt` | Policy | Reorder point formula, supplier lead times, approval thresholds, emergency stock procedure |
| `product_damage_claims_procedure.txt` | Procedure | 4-step damage claim process, category triage, carrier claim filing |
| `warehouse_dispatch_procedure.txt` | Procedure | Daily dispatch schedule, pick/pack standards, mispick handling |
| `product_notes_electronics.txt` | Product Notes | Storage, top SKUs (EL-10042, EL-10087, EL-10115), known defect batch, warranty info |
| `product_notes_office_supplies.txt` | Product Notes | Storage, top SKUs (OF-20010, OF-20045, OF-20201, OF-20310), bundle SKU, FINAL_SALE items |
| `support_ticket_ST-0041.txt` | Support Ticket | Defective EL-10042 (WCP-2023 batch); resolved with replacement |
| `support_ticket_ST-0055.txt` | Support Ticket | Mispick on ORD-01047 (OF-20045 vs OF-20310); resolved, staff flagged for retraining |
| `support_ticket_ST-0067.txt` | Support Ticket | Late damage claim on EL-10087 (ORD-01201); escalated to Operations Manager |
| `supplier_contact_directory.txt` | Reference | Supplier A/B/C contacts, lead times, payment terms, carrier contacts |

---

## records.csv

One row per order. 20 rows covering October–November 2025.

| Column | Description |
|--------|-------------|
| `order_id` | Unique order identifier (ORD-XXXXX) — use as `id` for `read_record` |
| `customer_account` | Customer account code (ACC-XXXX) |
| `account_tier` | Standard / Gold / Platinum |
| `sku` | Product SKU |
| `product_name` | Human-readable product name |
| `quantity` | Units ordered |
| `unit_price` | Price per unit in USD |
| `order_total` | Total order value in USD |
| `order_date` | Date order was placed |
| `dispatch_date` | Date order was dispatched (or expected) |
| `carrier` | FastFreight Logistics or BackupCarrier Co. |
| `tracking_number` | Carrier tracking reference |
| `delivery_status` | Delivered / In Transit / Pending Dispatch |
| `return_requested` | Yes / No |
| `notes` | Free-text notes linking to tickets, replacements, or policy references |

### Sample queries this data supports
- "What is the status of order ORD-01035?"
- "Which orders have a return requested and why?"
- "What orders were shipped by BackupCarrier?"
- "Show me all Platinum account orders."
- "What happened with the mispick on ACC-3340's order?"
