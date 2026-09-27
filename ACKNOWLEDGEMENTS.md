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

The v2 incremental-statement optimization also references these public business sources:

- [证券公司与资产管理产品管理人及服务机构间对账数据接口](https://www.sse.com.cn/lawandrules/regulations/csrcannoun/c/10751838/files/38d0a2f3c4b643879286c7c26ad2e520.pdf): standardized real-time and file-based statement exchange, including funds, securities, and pending-settlement data.
- [中国结算结算规则](http://www.chinaclear.cn/zdjs/editor_file/20220620141248275.pdf): hierarchical settlement, multilateral netting, delivery-versus-payment, and participant settlement obligations.
- [证券公司结算业务信创建设有关思考](https://www.stcn.com/article/detail/914855.html): multi-system coupling, data timeliness, interface complexity, and the need to decouple surrounding services from core settlement systems.

These sources define the business setting. The account-level fingerprint, incremental
rebuild, conservation gates, and versioned evidence model are this project's original
implementation and are evaluated only on synthetic data.
