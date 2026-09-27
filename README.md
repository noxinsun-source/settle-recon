# SettleRecon｜证券清算对账服务

一个面向证券中后台的可运行个人项目：将内部成交记录与外部清算记录逐笔核对，识别金额差异、清算日期差异、单边缺失和多候选歧义，并把无法安全自动处理的记录分流至人工复核。

> 项目仅使用模拟数据，不处理真实资金、客户信息或交易指令。

## 业务背景

成交系统和清算文件来自不同系统，常见问题包括成交编号丢失、净额偏差、清算日期异常、内部有成交但清算侧缺失，以及一条清算记录对应多个候选成交。对账系统的关键不是“尽量匹配”，而是避免错误自动匹配，并留下可复核的差异原因。

## 核心能力

- 两阶段匹配：优先使用成交编号精确匹配；编号缺失时使用账户、证券、方向和数量组成的业务键。
- 防误配：候选不唯一时不猜测，标记 `NEEDS_REVIEW`。
- 六类结果：匹配成功、金额差异、日期差异、待复核、内部缺失、清算缺失。
- 一一消费：同一成交或清算记录只能被匹配一次。
- 批次幂等与报告持久化：重复批次返回第一次生成的结果，便于日终任务安全重试。
- FastAPI、Pydantic、SQLite、Docker、pytest、ruff 与 GitHub Actions。

## 对账流程

```text
内部成交 + 清算记录
        ↓
成交编号精确匹配
        ↓ 未匹配
唯一业务键候选匹配
        ↓
金额/日期核验 → 自动匹配或异常分流 → 批次汇总与审计报告
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

提交示例批次：

```bash
curl -X POST http://127.0.0.1:8000/v1/reconciliations \
  -H 'Content-Type: application/json' \
  --data @examples/sample_batch.json
```

## 测试与容器

```bash
pytest -q
ruff check app tests
docker build -t settle-recon .
docker run --rm -p 8000:8000 settle-recon
```

## 公开项目参考与原创边界

项目从零实现，没有复制公开仓库代码。调研来源及与本项目的差异见 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

## 可继续扩展

- 支持 CSV/Excel 批量导入和差异报告导出。
- 增加手续费、印花税、过户费等费用项拆分核对。
- 接入任务队列处理大批量日终文件，并增加异常复核工作台。

