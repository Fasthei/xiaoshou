# 任务计划 (task_plan.md)

> 目标:**修复别的 session 没改完的 → 合并 main → 部署上线 → /agent-browser 端到端验收 → CI 全 docker 化(本地 + GH Actions)**
>
> 创建时间: 2026-04-18
> 当前分支: `feat/v2-lifecycle-rebuild-test-0417`
> 用户硬约束: CI 必须在 docker 中跑(否则裸 runner 产物会塞满硬盘)

---

## 阶段 0:盘点 + 锁定基线

**目标**:把工作树里"别的 session 留下的半成品"全部识别清楚,避免误删/误覆盖。

**步骤**:
- [ ] 0.1 列全部 untracked / modified 文件,逐项归属到 session 或归类
- [ ] 0.2 读 `.claude/worktrees/dreamy-darwin/` 看那个 session 的最新提交,确认未完成范围
- [ ] 0.3 把发现写进 `findings.md`
- [ ] **决策点 A**(等用户回复):
  - 别的 session 的改动 → 全收编 / 部分收编 / 全丢弃?
  - 我接手后是否允许直接动那些文件?

**Exit criteria**:findings.md 列表完整,用户对决策点 A 给了答复。

---

## 阶段 1:把别的 session 的工作"修完"

**前提**:阶段 0 决策点 A 已回复。

**已知未完成项**(初判,详见 findings.md):
- `app/models/allocation.py` `+unit_price_after_discount` 列(模型加了,迁移没写,API/schema/前端没用上)
- `app/models/sales.py` `+profit_margin_target` 列(同上)
- `alembic/versions/003_customer_code_nullable.py` (新迁移,未 commit,需对应模型 + 端点改造)
- `AGENTS.md` (Codex 版规则文档,内容看似完整,只缺 commit)
- `docs/BUSINESS_FLOW_CHECKLIST.md` (业务流程核对稿,内容看似完整,只缺 commit)
- 我自己写的 4 个 (ci.yml + alembic 004 + 2 个 sync 脚本) 也未 commit

**步骤**:
- [ ] 1.1 验证模型 + 迁移 + schema + API + 前端的链路完整(若链路有缺口,补足或回退)
- [ ] 1.2 修必要测试,本地 `pytest -q` 跑过
- [ ] 1.3 docker compose 本地起,`alembic upgrade head` 成功(004 + 003 都跑)
- [ ] 1.4 `git add` 决策点 A 同意收编的文件,**禁止 add `.env`**
- [ ] 1.5 commit (按逻辑拆 commit,例如 "feat(model): unit_price_after_discount + profit_margin_target")
- [ ] **决策点 B**(等用户回复):commit 信息和拆分是否 OK?

**Exit criteria**:工作树干净(只剩 `.env` 等 gitignored),pytest 绿,本地浏览器能进 `/customers` 看到数据。

---

## 阶段 2:本地全功能验收(/agent-browser)

**步骤**:
- [ ] 2.1 docker compose up -d 全 4 容器 healthy
- [ ] 2.2 `bash scripts/sync_from_prod.sh` 拉云端真实数据(18 客户)
- [ ] 2.3 `agent-browser` 走全部菜单 + 客户详情 6 Tab + 关键交互(折扣计算器/审批/CSV 导出/跟进留言)
- [ ] 2.4 后端 15 个核心端点 smoke,期望 0 个 5xx
- [ ] 2.5 写 QA 报告进 `progress.md`
- [ ] **决策点 C**(等用户验收):本地验收是否通过?发现的非阻塞瑕疵列出来给用户拍板。

**Exit criteria**:用户对决策点 C 答 "OK"。

---

## 阶段 3:CI 全 docker 化(本地 + GitHub Actions)

**步骤**:
- [ ] 3.1 写 `docker-compose.ci.yml`(可选)或直接在 `.github/workflows/ci.yml` 用 `docker run`
- [ ] 3.2 后端 CI:`docker build` api 镜像 → `docker run` 跑 ruff + pytest(挂 PG/Redis sidecar)
- [ ] 3.3 前端 CI:`docker build ./frontend` 验证构建
- [ ] 3.4 写本地 `bash scripts/ci_local.sh` 让开发也能在本机一键跑 docker 化 CI(避免硬盘塞满)
- [ ] 3.5 commit + push feat 分支触发 GitHub Actions
- [ ] 3.6 watch CI 直到绿;失败就改

**Exit criteria**:GitHub Actions 的 ci 任务绿;本地 `bash scripts/ci_local.sh` 在 docker 内跑完 pytest。

---

## 阶段 4:合并 main + 部署上线

**步骤**:
- [ ] 4.1 `gh pr create` feat → main(标题 + 描述含变更摘要 + 验收清单)
- [ ] 4.2 **决策点 D**(等用户审 PR):用户在 GitHub 点 merge
- [ ] 4.3 merge 后 `deploy.yml` 自动跑,build → ACR push → Container App update
- [ ] 4.4 deploy.yml 跑 `alembic upgrade head` 自动应用 003+004 迁移
- [ ] 4.5 `frontend-deploy.yml` 自动跑(若有前端改动)
- [ ] 4.6 等部署完成,`scripts/smoke-test.sh` 跑线上冒烟

**Exit criteria**:云端 4 个 workflow 都绿,smoke-test 200。

---

## 阶段 5:线上 /agent-browser 验收

**步骤**:
- [ ] 5.1 `agent-browser --session-name xs-prod open https://purple-rock-072562e00.7.azurestaticapps.net`
- [ ] 5.2 真实 Casdoor 登录(`admin / Admin@123456`),走 9 个路由 + 客户详情
- [ ] 5.3 后端 prod /docs 抽样跑 5-10 个端点
- [ ] 5.4 写线上 QA 报告
- [ ] **决策点 E**(等用户拍板):线上是否通过?有问题回滚还是热修?

**Exit criteria**:用户对决策点 E 签字。

---

## 决策点汇总(等待用户输入)

| ID | 时机 | 内容 |
|---|---|---|
| A | 阶段 0 完成后 | 别的 session 的改动是否收编 |
| B | 阶段 1 commit 前 | commit 拆分和信息 |
| C | 阶段 2 完成后 | 本地验收通过否 |
| D | 阶段 4 PR 后 | 用户在 GitHub 点 merge |
| E | 阶段 5 完成后 | 线上验收通过否 |

---

## 风险登记

1. ⚠️ **prod DB 缺 v2 列**:阶段 4 deploy 之前必须确保 003+004 迁移在 entrypoint 自动跑成功(已有 docker-entrypoint.sh 跑 alembic upgrade)。
2. ⚠️ **dreamy-darwin worktree 还在跑**:可能仍有别的 session 在编辑;commit 前要再 git status 一次防丢失。
3. ⚠️ **CI docker 化可能要改几轮**:Dockerfile 里没装 pytest/ruff,需要 pip install at runtime;镜像层缓存策略要调。
4. ⚠️ **线上数据风险**:不会动 prod DB / Redis,但 deploy 触发的 alembic 迁移会改 schema —— 必须可逆(004 downgrade 已写)。

---

# 第二轮规划 — A→B→C 串行 + 多 agent + 线上 QA

> 用户决策:套餐 A → B → C 顺序执行,**线上环境** /agent-browser 验收
> 创建时间: 2026-04-18(阶段 5 通过后)

## 阶段 6:套餐 A — 生产功能闭环

**目标**:让销售真正能用上 #5 合同上传 + #4 用量预警两个功能。

### 6.1 #5 合同上传闭环
- [ ] 6.1.1 后端:确认 `POST /api/contracts/{id}/upload` 已存在(CLAUDE.md TODO #5 说有),没有就补 multipart upload → Azure Blob
- [ ] 6.1.2 前端 wizard step 2:把 `console.debug` 换成真实 `axios.post` 调用(用 FormData)
- [ ] 6.1.3 上传成功 toast / 失败兜底 + spinner
- [ ] 6.1.4 在客户详情"档案/跟进"tab 的"合同"区能列出已上传文件 + 下载链接(只读,新建只能在 wizard)
- [ ] 6.1.5 单元测试:上传 endpoint 200 + 错误分支

### 6.2 #4 用量激增预警
- [ ] 6.2.1 读 `.omc/usage-design.md`(若不存在,从 CLAUDE.md 提到的"方案 A:service 级聚合 + usage_surge alert_rule"开始设计)
- [ ] 6.2.2 后端:`alert_rule.rule_type` 加 `usage_surge` 枚举值
- [ ] 6.2.3 触发逻辑:扫描 `cc_usage` 当月 vs 上月按 service 聚合,超阈值落 `cc_alert`
- [ ] 6.2.4 endpoint:`/api/alert-rules/triggered` 返回最近触发清单
- [ ] 6.2.5 前端:`/alerts` 页面"我的规则" + 新增 "usage_surge" 类型的创建表单
- [ ] 6.2.6 单元测试:阈值边界 / 跨月对比

**Exit criteria**:本地 docker 跑 + pytest 绿 + 手测合同上传 + 手测预警触发。

**决策点 F**(套餐 A 完成后):commit + push 走 PR → main → deploy。你点 merge 还是我直接合?

---

## 阶段 7:套餐 B — 代码质量护栏

**前提**:阶段 6 merge 进 main 完成。

### 7.1 #2 测试漏补 4 处
- [ ] 7.1.1 `tests/test_allocation_batch.py` 新增 — `/api/allocations/batch` 多货源 + 折扣
- [ ] 7.1.2 `tests/test_customer_stage.py` 补 lost 瞬态分支
- [ ] 7.1.3 `tests/test_manager_panorama.py` 新增 — 团队目标 annual_sales_target 聚合
- [ ] 7.1.4 `tests/test_follow_up_global.py` 补 inbox/reply 流程

### 7.2 #3 代码瘦身
- [ ] 7.2.1 pydantic v1 `class Config: from_attributes = True` → v2 `model_config = ConfigDict(from_attributes=True)`(全 schema 文件遍历)
- [ ] 7.2.2 删 `customer_status` 老字段(模型 + schema + API 全链路;新代码只读 `lifecycle_stage`)
- [ ] 7.2.3 删 `main.py` 里的 `_ensure_*_column()` helper 函数(alembic 003+004 已替代)

**Exit criteria**:pytest 通过数 ≥ 121(117 + 4 新),deprecation warning < 5,main.py 净减 30+ 行。

**决策点 G**:merge 节奏(同 F)。

---

## 阶段 8:套餐 C — 前端 V2 上线

**前提**:阶段 7 merge 完成。

注意:目前线上 SWA 还跑老前端(线上 drawer 5 tab,本地 6 tab)。

- [ ] 8.1 摸清线上前端版本:linkedin / SHA / build time
- [ ] 8.2 写一个无害的 frontend 改动(比如 README 加一行 + 版本 bump)触发 `frontend-deploy.yml`
- [ ] 8.3 或直接 `gh workflow run frontend-deploy.yml` 手动触发
- [ ] 8.4 等部署完成
- [ ] 8.5 verify:线上 drawer 应该有 6 tab(基本/时间线/分配/档案/跟进/关联货源)

**Exit criteria**:线上前端版本与 main HEAD 一致。

---

## 阶段 9:线上 /agent-browser 全功能 QA

**前提**:阶段 6+7+8 都 merge 上线。

### 9.1 准备
- [ ] 9.1.1 `pkill chrome` + 全新 session `xs-prod-final`
- [ ] 9.1.2 真实 Casdoor 登录 admin/manager01/sales01 三角色各一遍
- [ ] 9.1.3 验证角色守卫:sales01 不能进 `/manager/*`,sales-manager 能

### 9.2 9 路由 + 6 tab + 关键交互
- [ ] 9.2.1 9 个菜单路由全开,截图 + console err 计数
- [ ] 9.2.2 客户详情 6 tab 全切换
- [ ] 9.2.3 折扣计算器抽屉
- [ ] 9.2.4 CSV 导出(账单 + 客户)
- [ ] 9.2.5 跟进留言 + 回复线程
- [ ] 9.2.6 主管审批中心 Tab

### 9.3 阶段 6 新功能验收
- [ ] 9.3.1 客户管理 → 新建客户+订单 wizard → 上传合同 PDF/DOC → 看 Azure Blob 收到
- [ ] 9.3.2 客户详情合同 tab 能下载
- [ ] 9.3.3 创建一条 usage_surge 预警规则 → 等触发 → 看 `/alerts` 出现

### 9.4 后端 prod /docs smoke
- [ ] 9.4.1 健康检查 + 15 个核心 endpoint 抽查(都需带 token)

**决策点 H**(终极验收):
- 验收通过 → 项目交付,关单
- 有 P0 bug → 紧急修 → 重 deploy
- 有 P1+ 累计成 sprint → 下轮 planning

---

## 第二轮决策点汇总

| ID | 时机 | 内容 |
|---|---|---|
| F | 阶段 6 完成后 | 合同上传 + 用量预警 PR merge 节奏 |
| G | 阶段 7 完成后 | 代码瘦身 PR merge 节奏 |
| H | 阶段 9 完成后 | 线上终极验收签字 |

## 多 agent 编排策略(给未来的我看)

由于 sub-agent 的 Bash 工具被沙箱拦,**纯 file-edit 的工作可以派 agent 并行**(写新测试、写新 schema、写新组件),**git/docker/gh 必须主 session 自己跑**。

阶段 6 派 agent 模式:
- agent A1: 写后端 contract upload endpoint (Python/FastAPI)
- agent A2: 写前端 wizard step 2 真实上传逻辑 (React/TS)
- agent A3: 写后端 usage_surge 触发器 (Python)
- (并行,主 session 收齐后跑测试 + commit + push)

阶段 7 派 agent 模式:
- agent B1: 写 4 个测试文件
- agent B2: pydantic v2 迁移(全 schema)
- agent B3: 删 customer_status 老字段(全链路)
- (并行)

阶段 8 / 9 不派 agent(主要是 ops + browser test)。


---

# 第三轮规划 — CLAUDE.md 剩余 sprint 多 agent 并行 + 线上第一轮测试

> 用户决策(阶段 9 通过后):把 CLAUDE.md 还没实现的 sprint 全派 agent 做完,然后线上第一轮测试。
> 创建时间: 2026-04-18

## 阶段 10:多 agent 并行实施 sprint

| agent | 任务 | 范围 |
|---|---|---|
| **S1** | 销售个人 YTD 目标进度模块(前后端) | sales home 加进度条 / 缺口 / 到年末差距 + 后端 endpoint |
| **S2** | 角色守卫完整化 | 前端 RoleGuard 守卫 `/manager/*` 防越权 + 后端 `require_role` helper |
| **S3** | usage_surge 4 真测试 + customer_status 真代码迁移 7 处 | 把 skip 骨架填实数据 + 7 处 customer_status 用法切到 lifecycle_stage |
| **S4** | dev 入口残留 audit + 用量预警 cron 触发器 | grep dev_html / as-*.html;新增 cron 端点定时跑 evaluator |

## 阶段 11:线上第一轮测试

- 收齐 → 合并 commit → push → CI 绿 → auto-merge → deploy
- agent-browser 跑全功能(含 sprint 新功能):YTD 进度、角色守卫拦截、新建规则、cron 触发
- 报告


---

# 第四轮规划 — 复杂报表/BI + 合同到期提醒

> 用户需求(阶段 11 完成后):"复杂报表/数据 BI 和客户合同到期提醒可以做"
> 创建时间: 2026-04-18

## 阶段 12:多 agent 并行实施

### D1 复杂报表/BI 后端
- 加 `app/api/reports.py` 新 router:
  - `/api/reports/sales-trend?dim=month|customer|sales|region|industry&from=&to=`
  - `/api/reports/profit-analysis?dim=...&breakdown=customer_level|industry`
  - `/api/reports/funnel?from=&to=` (lead→contacting→active 各步耗时 + 转化率)
  - `/api/reports/yoy?metric=sales|profit&period=month` (同比/环比)
  - `/api/reports/export?type=sales-trend&format=csv|xlsx`
- 用 SQLAlchemy 聚合 allocation + customer + cc_usage
- 测试 4 case (覆盖维度 / 切片 / 边界 / 导出格式)

### D2 复杂报表/BI 前端
- `frontend` `npm install recharts`(轻量 + 兼容 antd 主题)
- 新页面 `/reports`(主管菜单)
- Tab: 销售趋势 / 利润分析 / 漏斗 / 同比环比
- 每个 tab: 维度切换器 + 时间范围 + 主图(line/bar/pie) + 数据表
- 导出按钮调 `/api/reports/export`

### D3 合同到期提醒
- 后端:
  - `_RULE_TYPES` 加 `contract_expiring`(threshold_value = 提前天数,如 30/60/90)
  - `app/services/contract_expiry_trigger.py`: 扫 contract.end_date 在阈值窗口内的 + 还 active 的
  - 触发写 alert_event (alert_type='contract_expiring',message='合同 XXX 还有 N 天到期')
  - GET `/api/alert-rules/triggered` 已存在,加 contract_expiring 过滤支持
  - POST `/api/internal/cron/contract-expiring`(M2M 鉴权)
- 前端:
  - `/alerts` 页面新建规则表单加 `contract_expiring` 类型
  - 销售工作台 / 主管 dashboard 加"合同到期"卡片(读 triggered 事件)
- 测试 3 case (在窗口内 / 窗口外 / 已 expired)

## 阶段 13:线上验收
- 跑 cron / 手测前端报表
- agent-browser 截图 + 报告

## 决策点 I:同 F=是,我自动 merge

