# Design references

SettleRecon is an original implementation. No source code was copied from the
projects below. Their public documentation was reviewed for reconciliation
terminology and common exception patterns:

- [rekon](https://github.com/rjdscott/rekon) (MIT): generic finance and operations
  reconciliation workflow.
- [Payment Reconciliation Agent](https://github.com/adithyaathreya2264/payment-reconciliation-agent)
  (Apache-2.0): deterministic-first matching and explicit escalation for ambiguous cases.

SettleRecon narrows the problem to securities middle/back-office operations. Its
original additions include trade-reference and composite-key matching, one-to-one
consumption, settlement-date checks, amount tolerance, bilateral missing-record
classification, ambiguous-candidate blocking, batch idempotency, and persisted reports.

