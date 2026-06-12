---
doc_id: customer-account-sample
title: Customer Account Record — Sample (Customer PII)
allowed_roles: []
clearance_level: 3
sensitivity_class: D
owner_department: Customer Support
summary: A single synthetic customer account record (name, email, balance) — customer PII.
---
# Customer Account Record (Customer PII)

This is a synthetic customer account record drawn from the Meridian customer
ledger. Customer-PII (class D) is masked for sessions below clearance level 4 and
returned raw only to L4+ — least-privilege, not blackout.

Customer name: Dana Okafor. Account email: dana.okafor@example.com. Loyalty tier:
Gold. Current wallet balance: 1,284.50 USD. Last login city: Singapore.

The record is owned by Customer Support and governed at clearance level 3,
sensitivity class D. A support agent or analyst at L2-L3 sees this record with the
PII redacted; a customer-data steward at L4+ sees it raw.
