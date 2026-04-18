# 会话日志 (progress.md)

> 时间正序记录关键动作和结果。

---

## 2026-04-18 早些时候(本 session 之前)

- 仓库 clone 到 `/Volumes/macOS/GO/xiaoshou`
- 切到 `feat/v2-lifecycle-rebuild-test-0417` 分支
- docker compose 本地部署成功(4 容器健康)
- `agent-browser` 跑过一轮基础 QA(发现 prod DB schema drift → 本地手动 ALTER 临时修复)
- 拉云端 PG 真实数据到本地(18 客户)
- 拉云端 Container App env 到本地 `.env`(28 个 key 1:1)
- 把本地 PG 升 16→18 匹配云端
- 临时给 Azure PG 加防火墙规则,dump 完已删除
- 之前的 feat→main 合并已 push 到远端 `main` (HEAD `365a444`)

---

## 2026-04-18 本规划阶段开始

### 阶段 0(进行中):盘点 + 锁定基线

- ✅ 写好 task_plan.md / findings.md / progress.md
- ✅ git status 全列举,改动归属到 4 个 source(本 session / dreamy-darwin / 系统 / gitignored)
- ⏳ 等用户对**决策点 A** 答复:别的 session 的改动是否收编

### 待决策:

**决策点 A**:findings.md 第 2.2 节列的 5 项(2 个 modified models + 003 迁移 + 2 个 docs)
- 选项 1:全收编(commit 一起)— 最省事,3 项有依赖关系(模型 + 003 迁移 + 我的 004 迁移)
- 选项 2:只收编 003 迁移 + 模型(技术依赖必需),docs 暂不入库
- 选项 3:全丢弃,只用我的 004 迁移(覆盖 003 的需求需要重写)
- **我推荐**:选项 1(已经在工作树存在,内容看着合理,无理由丢)

---

## 后续将在每个步骤完成后补一条日志,格式:

```
### YYYY-MM-DD HH:MM 阶段 N 步骤 N.X
- 做了什么
- 结果(成功 / 失败 + 原因)
- 下一步
```

### 2026-04-18 阶段 1 进度

- ✅ 1.0 决策点 A:用户答 "全收"
- ✅ 1.1 验链路:迁移 001→002→003→004 完整,模型 customer_code/customer_status 已对齐 003
- ✅ 1.2 改 docker-compose.yml: postgres 16→18-alpine
- ✅ 1.3 重建 PG 容器(v18.3 healthy),api 镜像 build 后跑 alembic upgrade head 全 4 个迁移成功
- ✅ 1.4 验列存在: allocation.{discount_rate, unit_price_after_discount} / customer_follow_up.{to_sales_user_id, parent_follow_up_id} / sales_user.{annual_sales_target, profit_margin_target} 全部 OK
- ✅ 1.5 pytest -q (with AUTH_ENABLED=false override): 117 passed, 1 skipped, 42 warnings
- ⏳ 1.6 生成 .env + 同步数据 + agent-browser smoke

### 2026-04-18 阶段 1 后续修复(dreamy-darwin 半成品收尾)

发现 dreamy-darwin 加了模型字段但 schema 没串起来,补上:
- ✅ app/schemas/customer.py: customer_code 改 Optional (CustomerBase + CustomerCreateLite)
- ✅ app/schemas/allocation.py: AllocationResponse 补 discount_rate + unit_price_after_discount
- ✅ app/schemas/sales.py: SalesUserBase + SalesUserUpdate 补 profit_margin_target
- ✅ docker compose build api + restart
- ✅ pytest -q (AUTH_ENABLED=false): 117 passed, 1 skipped (无回归)
- ✅ /api/customers 返回 18 真实客户

阶段 1 完成。 准备进入 A:commit + push + 等 CI 绿

### 2026-04-18 第二轮规划

- 阶段 5 完成,线上 QA 全绿
- 用户选择 A→B→C 串行 + 多 agent + 线上 /agent-browser 验收
- task_plan.md 追加阶段 6-9 + 决策点 F/G/H
- 等用户启动阶段 6 (套餐 A)


### 2026-04-18 阶段 6 套餐 A 完成

- ✅ A1 (frontend): wizard step 2 真实合同上传 (POST /api/contracts + /upload, FormData, 失败独立 catch)
- ✅ A2 (backend): usage_surge 触发器 + endpoint
  - alert_rule._RULE_TYPES 加 usage_surge
  - app/services/usage_surge_trigger.py: evaluate_usage_surge_rules(db) 返回触发数
  - app/models/alert_event.py: 去重表 (alert_rule_id, customer_id, service, month) unique
  - GET /api/alert-rules/triggered + POST /api/alert-rules/run-evaluator
- ✅ A3 (tests): contract upload 6 case (123 passed) + usage_surge 4 case skip 骨架
- ✅ pytest 全套: 123 passed, 5 skipped

下一步: commit + push + gh pr create + auto-merge (F=是) → 进 7

### 2026-04-18 阶段 7 套餐 B 完成

- ✅ B1 测试: +11 case (allocation_batch 4 / customer_stage lost 1 / manager_panorama 4 / follow_up inbox+reply 2)
- ✅ B2 pydantic v2: 8 文件 13 处 ConfigDict (warnings 42→29)
- ✅ B3 删 _ensure_*: main.py -199 行; customer_status 加 deprecation 注释 (102 处不真删)
- ✅ pytest: 134 passed, 5 skipped (+11 vs 套餐 A 的 123)

阶段 8 (前端 V2 上线) ✅ 在阶段 6 merge 时顺便完成。
下一步: commit + push + merge → 阶段 9 线上 QA
