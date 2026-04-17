# CLAUDE.md — xiaoshou 销售系统定性与产品规则

本文档记录用户（产品负责人）对系统定性、角色分工和核心产品规则的决策。Claude / agent 在做任何改动前应先读这里。

## 一、系统定性

**销售为主，运营为辅**。功能取舍以此优先级判断。

## 二、角色分工（3 种）

### 1. 销售主管（sales-manager）
- **独立页面**，普通用户不可见
- 关注指标：**商业机会**、**转化率**、**增长率**、**回款率**
- 对团队做管理（销售成员、分配规则、订单审批）

### 2. 销售（sales）
- 日常主要工作页面
- 关注：
  - 是否还有**货源**（可分配）
  - 哪些客户需要**达成用量承诺**
  - **预设用量警告** + **回款提醒**
  - **全年销售目标达成情况** —— 销售主管给该销售设的年度目标 vs 销售自己 YTD 业绩（进度条 / 缺口 / 到年末还差多少）
- 商机挖掘（了解客户）应**自动化**完成：
  - AI 辅助客户信息收集
  - 客户详情的 **AI 洞察**不仅含互联网信息，**也要包含销售自己填写的数据**
    （跟进记录 / 备注 / 合同 / 历史订单）

### 3. 运营（operations）
- 只关心**账单中心** + **客户详细用量**
- 用量视角：每个客户在哪个货源用了多少、具体金额
- 不直接看云管平台 UI，但数据**通过云管拉**

## 三、产品规则（强制，任何改动必须遵守）

### 3.1 订单
- **新建订单需要审批**（不是即时生效）
- 新建订单入口**不在订单管理页**，**放在客户管理**里
- 新建客户流程提供两个选项：
  - **新建客户**（空客户）
  - **新建客户 + 新建订单**（一步到位）
- 订单可以关联**多个货源**（非 1 对 1）
- 订单的货源仍然以**云管为准**（resource 数据从云管拉）
- **新建订单时必须上传合同文件**（PDF / Word / 图片，走 Azure Blob 存储）。合同落在该订单的"合同"记录下，该客户的合同列表也能看到。
- **客户详情的"合同"tab 只读**（查看 + 下载），新建合同只能在新建订单流程里一步完成

### 3.2 货源
- **货源以云管 (cloudcost) 为准**
- 云管 `ServiceAccount` 只有 `id/name/provider/supplier_name/external_project_id/status`，**无数量/配额字段**
- 货源看板显示 **status 维度聚合**（AVAILABLE / STANDBY / ...），不展示本地凑的 total/allocated/available 数字列

### 3.3 账单中心
- 月度账单表 = **云厂商汇总粒度**（provider × month × category），不要强行按客户/货源过滤
- "按客户/货源筛选费用" 走 `cc_usage` 表（天然有 customer_id + resource_id + usage_cost），即
  - `/api/usage/customer/{id}` 查某客户的费用明细
  - `/api/usage/resource/{id}` 查某货源的费用明细
- 运营关心的"某客户在哪些货源用了多少"直接落到 `cc_usage` 下钻
- **折扣计算器**：账单中心提供交互式工具，输入原始成本 + 折扣率（或 markup）→ 算出最终价格 / 毛利 / 毛利率
- **导出功能**：账单中心支持导出 CSV / Excel（至少含 月份 / 客户 / 货源 / 原始成本 / 调价 / 最终金额 / 状态）

### 3.4 客户时间线
- `/api/customers/{id}/timeline` **不展示** "从 gongdan 同步客户" 这类系统自动同步事件
- 只展示真实业务动作（跟进、分配、合同、订单、AI 洞察运行、审批等）

### 3.5 商机挖掘（Leads 页）
- **前端移除菜单入口 + 路由 + 页面代码**
- 该功能并入**客户详情 AI 洞察**（自动化的客户信息收集）

### 3.6 客户来源 & 客户类型（转介绍 / 渠道）

**业务事实**：xiaoshou 的客户大多数通过**转介绍**获得，部分走**渠道商**（渠道方不一定告诉我们终端用户是谁）。因此数据模型需要能表达：

- **直客 `direct`**：我们直接服务的客户（有 customer_name + 联系人 + 完整信息）
- **渠道客户 `channel`**：我们服务的是渠道商；渠道的终端客户对我们模糊/未知
- **转介绍来源**：不管是直客还是渠道客，都要能标记是谁转介绍过来的（可选填）

**数据模型（需扩展）**：

| 字段 | 表 | 用途 |
|---|---|---|
| `customer_type` | `customer` | `direct` / `channel`（枚举） |
| `referrer` | `customer` | 转介绍来源的文本标签（"老客户 XXX 转介绍" / "合作伙伴 YYY 推荐"），不强约束实体 |
| `channel_notes` | `customer` | 渠道客户专用：渠道方给的终端用户说明（JSON 或 free text） |

**货源记录**：

- 渠道客户的 cloudcost 资源仍然落到**渠道的 customer_code** 下（维持现有 customer_resources 行为）
- 每个 allocation 可加一个 `end_user_label` 字段（free text）记录"这个货源给渠道的哪个终端用"——不强管控，**只做备忘**
- 对运营账单："某渠道用了多少"和现在一样（按 customer_code 聚合）；若渠道愿意告诉我们 end_user_label，可以再按那个细分

**UI 上**：
- 新建客户流程第一步就让选 `direct` 或 `channel`
- 渠道客户在客户列表加一个 Tag "渠道" 标记
- 新建订单（含多货源）每行货源旁可选填 `end_user_label`

### 3.6 销售成员管理
- 来自 Casdoor 的销售用户**不可彻底删除**（只能停用）
- 手工新增的销售用户可彻底删除，但要先回收客户 + 清理规则

## 四、AI 洞察数据源

客户详情 AI 洞察是**多源综合**，不是只爬公网：

- **外部互联网**：Jina 搜索 + LinkedIn 查询（行业、新闻、关键人）
- **本地销售数据**（必须纳入 agent 的上下文）：
  - `customer_profile` / `note` / `customer_short_name` / `industry` / `region` 等字段
  - `follow_up_record` 跟进记录
  - `contract` 合同内容
  - `allocation` 历史订单
  - 未来：销售备注字段

- 持久化到 `customer_insight_run` + `customer_insight_fact`，下次运行做增量

## 五、约定

- 改动前先对照本文档第三节的产品规则
- 产品规则有冲突时，以**销售主管/销售/运营**三视角优先级为准（销售主管先权重最高）
- 新增功能要能判断归哪个角色，放在对应的页面分组里

### 5.1 前端改动的 QA 流程（强制）

**所有前端改动完成后**，必须由 qa-tester 用 `/agent-browser` 工具走一遍：
- 导航到改动的路由
- 截图 before / after 状态
- 触发改动的交互（如果有）
- `read_console_messages` + `read_network_requests` 看没有新的报错
- 报告通过 / 失败

lead 派 frontend-dev 任务时默认把 qa 复查作为下一步，不要漏。

### 5.2 系统角色与 Casdoor 认证中心集成

- **三个业务角色**（sales-manager / sales / ops）统一在 **Casdoor `operation/sales` 应用**下配置 Role 管理
- 后端 `require_auth` dependency 从 JWT 解出 `roles` claim；各 endpoint 按角色授权（`require_role("sales-manager")` 之类）
- 前端登录后读取 `xs_user.roles`，做**角色路由守卫**（销售主管页 `/manager/*` 只允许 sales-manager 访问，以此类推）
- 新增 Casdoor 角色时不需要改 xiaoshou 代码，只要后端 `require_role` 能识别新角色名即可
- 角色来源**只**从 Casdoor 取，xiaoshou 本地不再维护独立的"角色表"

---

## 六、Sprint 历史（持久化给下次 agent 读）

> 规则性结论放第 3 节；这里只记已完成的改动和进行中的任务，给下一次 session 快速恢复状态。

### 已完成（2026-04-16 晚）

**PR #29**（分支 `claude/prod-qa-fixes-20260416`，3 commits，CI 绿）：
- `Dashboard.tsx` 近14天趋势: `last-first` → `((last-first)/first)*100`，带符号变色 + FallOutlined
- `CustomerDetailDrawer.tsx` 状态 labelMap 补 `formal: '正式'` / colorMap 补 `formal: 'blue'`
- `Allocations.tsx` 删 "新建订单" 按钮 + 加 Alert "订单由云管同步自动生成"
  - **注**：此规则已被后续 3.1 覆盖：新建订单回归，但入口挪到"客户管理"新建下拉里 + 走审批。订单管理页本身仍只做查看
- `Resources` 看板 + `/api/resources/summary` 重构: provider 按 status 分桶（去掉本地凑的 allocated/available/rate）；top_available 去掉 available_quantity
- 防御性加固 7 处 (Customers/Leads/SalesTeam/CustomerDetailDrawer/CustomerProfileTab/Allocations 的 try/catch+message.error；CustomerInsightPanel SSE onComplete/onError 都清 spinner；customer_insight_agent.py DB 查询 try/except + GeneratorExit 捕获)
- `tests/test_resource_summary.py` 跟新契约对齐

### 本批（xs-dev-loop 团队，未 commit）

**已完成的改动（等待 batch commit）**：
- `frontend/src/pages/Leads.tsx` 删除；App.tsx / AppLayout.tsx 删路由+菜单
- `frontend/src/pages/Customers.tsx` "新建客户" 改 Dropdown，两个选项（新建客户 / 新建客户+新建订单）
- `frontend/src/components/CustomerOrderWizardModal.tsx` 新增（2 步骨架，multi-resource 占位 + 合同 Upload + pending banner）
- `frontend/src/pages/ManagerDashboard.tsx` 新增（4 KPI 卡 + 待审批订单 + 销售团队业绩）
- `frontend/src/pages/ManagerApprovals.tsx` 新增（审批全表页）
- `frontend/src/components/DiscountCalculatorDrawer.tsx` 新增（折扣计算器）
- `frontend/src/pages/Bills.tsx` 加工具栏（折扣计算器按钮 + CSV 导出按钮）
- `app/api/customer_timeline.py` 去 gongdan sync 事件
- `app/agents/customer_insight_agent.py` + `tests/test_customer_insight_agent.py` 注入本地销售数据到 system prompt（+新测试 case）

**进行中**：
- `frontend/src/components/MultiResourceSelector.tsx` (Task #2-B)
- `app/models/allocation.py` + endpoint 审批字段 (Task #3)
- `app/api/bills_export.py` + `app/api/manager.py` (Task #6)

### 待派队列

- Task #4：customer 表加 `customer_type / referrer / channel_notes` + allocation 加 `end_user_label`（等 #3）
- 角色守卫：前端按 roles claim 守卫 `/manager/*`；后端 `require_role` helper
- 销售个人 YTD 目标进度模块（前后端）
- 合同上传后端 endpoint（multipart → Azure Blob，附加到合同表 + 关联 allocation_id）
- qa-tester `/agent-browser` 复查所有前端改动（部署后再做）
- git commit + push + open PR（本批完成后）

### 约定（给下次 agent）

- 团队名 `xs-dev-loop`；成员 frontend-dev / frontend-dev-2 / backend-dev / backend-dev-2 / qa-tester
- worker preamble 在 `/tmp/xs-dev-team-preamble.txt`（临时文件，agent 启动时读，不进 git）
- agent 跑 tsc / pytest 大概率会被权限拦；lead 统一在本 session 跑 + 记录结果
- prod URL: 前端 `https://purple-rock-072562e00.7.azurestaticapps.net` / 后端 `https://xiaoshou-api.braveglacier-e1a32a70.eastasia.azurecontainerapps.io/api`

---

## 七、V2 业务流程重构（2026-04-17 日落）

### 已完成（commit `2707650` on branch `feat/v2-lifecycle-rebuild`）

**lifecycle_stage 3 阶段**（替代老 customer_status）：
- `lead` 商机池 🧊 / `contacting` 沟通中 📞 / `active` 正式服务中 🎯 / `lost` 瞬态（审批通过自动回 lead 带回流标记）
- 自动化：首次跟进 lead→contacting；gongdan sync 正式编号 contacting→active
- 手动改走 stage_request 审批流（申请修改 Stage Modal + 主管审批中心）

**UI 瘦身**：
- 客户抽屉 12+ Tab → 6 Tab：基本信息 / 时间线(含 stage history) / 分配(含健康分) / 档案(Collapse: 基本资料/工单/过往账单/AI洞察/合同) / 跟进 / 关联货源
- 销售菜单 8 项 `/home`(代办+KPI) / `/customers` / `/follow-ups` / `/resources` / `/allocations` / `/alerts` / `/bills`
- 主管菜单 7 项 `/dashboard`(全景图) / `/manager`(Tab 销售团队+审批中心) / `/customers` / `/follow-ups` / `/resources` / `/allocations` / `/bills`
- 删除：订单审批中 / 订单生效 stage，预警中心的云管预警 Tab，客户抽屉的退回商机池按钮，销售团队成员邮箱/电话/区域/行业列

**订单审批**：
- 销售发起 `/api/allocations/batch`（支持折扣明细多行：货源/数量/原价/折扣率/折后单价/小计）
- 主管审批 `/api/allocations/{id}/approval`（require_roles('sales-manager','admin')）
- 审批 approved 不再自动升客户 stage（与 lifecycle 解耦）
- 订单管理页仅查看，入口在客户管理

**账单中心**：
- 月度账单（本地聚合）`/api/bills/by-customer`：按 customer_resource 关联的货源聚合 cc_bill
- CSV 导出 `/api/bills/export`：8 列含折前金额/折扣率/折后金额/毛利
- 删「月度账单(云管代理)」整块

**跟进**：
- 全局列表 `/api/follow-ups`
- 收件箱 `/api/follow-ups/inbox`（to_sales_user_id=我）
- 留言 + 回复（parent_follow_up_id 线程）
- 🔁 转分配 仅 sales-manager / admin 可见
- 销售默认筛选自己（casdoor_user_id=my.sub 匹配）

**主管 dashboard / 团队目标**：
- ManagerPanorama: 5 KPI(新增商机/转化率/签单率/增长率/回款率) + 团队漏斗对比(3 段) + 异常告警
- 新「销售团队利润 概览」区块：利润率目标 vs 实际 / 销售额 YTD vs 目标 / 利润 YTD vs 目标
- `/api/metrics/team-profit`、`/api/metrics/my-kpi`、`/api/metrics/my-todos` 新端点
- 销售团队 Tab 每行编辑 annual_sales_target / annual_profit_target

**AI 洞察**：
- 历史记录 Timeline + 单次 run 展开 facts
- `/api/customer/{id}/insight/runs` 带 fact_count / duration_ms

**客户关联货源**：
- customer_resource 表（FK customer_id + resource_id + end_user_label）
- 客户抽屉「关联货源」Tab 多选 Modal（按厂商筛选 + 搜索）

**本地 dev 基建**：
- Docker stack: postgres / redis / api / web
- nginx `/api/` 反代到 api:8000（固化进 `frontend/Dockerfile`）
- `AUTH_ENABLED=false` 本地绕过认证（线上仍 true）
- AuthContext `local-dev` token 短路**仅 import.meta.env.DEV 时启用**（prod build 关闭）
- 删除 `frontend/public/as-*.html` dev 入口（避免线上角色提权漏洞）
- 本地 DB 数据：从线上 pg_dump 同步（18 formal 客户），脚本见 notepad

### 遗留 TODO（下次 agent 接手）

#### 1. CI/CD 强制走 Docker（用户明确要求 "CI 必须在 docker 中实现，不是本机"）
- 现有 `.github/workflows/ci.yml` / `deploy*.yml` 可能用的是 `runs-on: ubuntu-latest` + 直接 python/npm
- 改成：`docker compose -f docker-compose.ci.yml up --build --exit-code-from runner`（或 GitHub Actions 的 `services: docker` 模式）
- 后端 pytest 跑在 api container 里；前端 build 跑在 web builder stage
- 参考：既有 `Dockerfile` + `frontend/Dockerfile` 已能满足

#### 2. 测试漏补
- `/api/allocations/batch` 测试未加
- `/api/customer_stage/approve` lost 瞬态分支未覆盖
- ManagerPanorama 团队目标（annual_sales_target 聚合）测试未加
- 跟进 inbox / reply 流程测试未加

#### 3. 后端 schema 瘦身
- `app/schemas/customer.py` 仍含老 `customer_status` 字段（向后兼容期；未来删）
- pydantic v1 class Config → v2 ConfigDict 迁移（一批 deprecation 警告）

#### 4. 用量激增预警（用户让先展示不实现，已有调研但代码未落）
- `.omc/usage-design.md` 有完整设计
- 方案 A：service 级聚合（不含 sku）+ usage_surge alert_rule
- 触发逻辑补到 `/api/alert-rules/triggered`

#### 5. 合同上传闭环
- 当前 wizard Step 2 的合同文件只 console.debug，没真实上传到 Azure Blob
- 需要后端 `POST /api/contracts/{id}/upload` 已有但 wizard 未调用

#### 6. 数据迁移 SQL
- 上生产前必须跑：`UPDATE customer SET lifecycle_stage='contacting' WHERE lifecycle_stage IN ('order_pending','order_approved')`
- `ALTER TABLE allocation ADD COLUMN IF NOT EXISTS discount_rate NUMERIC(5,2)`
- `ALTER TABLE customer_follow_up ADD COLUMN IF NOT EXISTS to_sales_user_id BIGINT`
- `ALTER TABLE customer_follow_up ADD COLUMN IF NOT EXISTS parent_follow_up_id BIGINT`
- `ALTER TABLE sales_user ADD COLUMN IF NOT EXISTS annual_sales_target NUMERIC(15,2)`
- 本地已跑；线上 alembic 003 迁移需要写

#### 7. Casdoor 角色
- 线上 operation 组织有 `sales`、`sales-manager`、`ops`、`admin`、`customer`、`engineer-l1/2/3` 角色
- 本地测试账号：`admin / Admin@123456`(超管, 已改过密码)、`sales01 / Sales@123456`、`manager01 / Manager@123456`
- 线上 admin 回调 URI 已含 `http://localhost:5173/auth/callback` 如需本地真实登录

### 合并到 main 前的验收清单

- [ ] CI 改 Docker 后跑绿
- [ ] 线上 DB 迁移脚本写好（alembic 003）
- [ ] 线上部署前 dev 入口（.html + AUTH_ENABLED=false）确认已清
- [ ] 核心路径回归测试：新建客户+订单 / 审批 / 跟进留言 / 账单导出
- [ ] 产品负责人验收 5 个关键视图：销售 /home、主管 /dashboard、/manager Tab、客户抽屉、/bills
