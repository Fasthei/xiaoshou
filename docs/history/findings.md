# 发现 (findings.md)

> 调查记录:当前仓库状态、drift、阻塞、外部依赖。
> 创建时间: 2026-04-18

---

## 1. 仓库 / 分支事实

- **远端**:`https://github.com/Fasthei/xiaoshou`
- **远端分支**:`main`(HEAD `365a444`,已包含上一次 feat→main 合并) + `feat/v2-lifecycle-rebuild-test-0417`(HEAD `773722e`)
- **本地**:在 `feat/v2-lifecycle-rebuild-test-0417`,已与远端 `feat/v2-lifecycle-rebuild-test-0417` 同步
- **本地多余分支**:`claude/confident-nash-f659af` / `claude/dreamy-darwin` / `claude/great-torvalds-f48d44` / `claude/prod-qa-fixes-20260416` / `claude/youthful-tu` —— 都是其他 session 自动建的,可以无视

---

## 2. 工作树未 commit 改动(按归属分类)

### 2.1 我(本 session)写的 4 个文件 — 等阶段 1 commit
- `.github/workflows/ci.yml`(覆写)→ CI 改 docker
- `alembic/versions/004_v2_lifecycle_columns.py`(新)→ allocation.discount_rate / unit_price_after_discount + customer_follow_up.to_sales_user_id / parent_follow_up_id + sales_user.annual_*_target / profit_margin_target + 数据迁移
- `scripts/sync_from_prod.sh`(新)→ 云端 PG → 本地容器
- `scripts/sync_env_from_prod.sh`(新)→ 云端 Container App env → 本地 .env

### 2.2 别的 session(`claude/dreamy-darwin` worktree)留下的 — 等用户决策 A
- `app/models/allocation.py` (modified) `+unit_price_after_discount Numeric(15,2) nullable`
- `app/models/sales.py` (modified) `+profit_margin_target Numeric(5,2) nullable`
- `alembic/versions/003_customer_code_nullable.py` (new) → `customer.customer_code` 改 nullable + `customer.customer_status` 长度从 20→32
- `AGENTS.md` (new, 187 行) → Codex 版规则文档,内容近似 CLAUDE.md
- `docs/BUSINESS_FLOW_CHECKLIST.md` (new, 212 行) → 业务流程核对稿

### 2.3 系统 / 工具产生的 — 不入库
- `.claude/`(本地 Claude session 工作区,gitignored 应该)
- `.env`(本地配置,gitignored 已确认)

---

## 3. Schema Drift 详情

### 3.1 本地 docker PG vs SQLAlchemy 模型
- 本地容器是 postgres:16-alpine(`docker-compose.yml` 写的),但**云上是 PG 18.3**
- 上次本 session 验证:本地数据从云端 dump 后,因为 PG 16 的 pg_dump 不能读 PG 18 server,需要把本地升 18-alpine
- **当前 docker-compose.yml** 还是 16,因为之前的 reset 把这个改动丢了
- → 阶段 1 需要重新改 16 → 18 + 重建数据卷

### 3.2 SQLAlchemy 模型 vs 云端 prod DB
模型有但 prod DB 缺(下次 deploy 会爆 5xx):
- `allocation.discount_rate Numeric(5,2)` — 模型已有 (line 22)
- `allocation.unit_price_after_discount Numeric(15,2)` — 模型 staged 新增(2.2 节)
- `customer_follow_up.to_sales_user_id BigInteger` — 模型已有
- `customer_follow_up.parent_follow_up_id BigInteger` — 模型已有
- `sales_user.annual_sales_target Numeric(15,2)` — 模型已有
- `sales_user.annual_profit_target Numeric(15,2)` — 模型已有
- `sales_user.profit_margin_target Numeric(5,2)` — 模型 staged 新增(2.2 节)
- `customer.customer_code` 应允许 NULL — 003 迁移负责
- `customer.customer_status` 长度 20→32 — 003 迁移负责

→ 我写的 004 迁移已覆盖以上(用 `ADD COLUMN IF NOT EXISTS` 形式幂等)。链 003 → 004 链不能断。

---

## 4. CI / 部署链现状

- `.github/workflows/ci.yml`:**裸 ubuntu-latest**(违反用户硬约束)→ 我已覆写为 docker 版,等 commit
- `.github/workflows/deploy.yml`:走 OIDC 登 Azure → ACR build push → Container App update。生产部署用 `docker build`,**已经是 docker**,符合规则。
- `.github/workflows/frontend-deploy.yml`:`actions/setup-node` + `npm ci` + `npm run build` → SWA 部署。**未 docker 化**,但属于部署不属于 CI,优先级低。

---

## 5. 本地环境现状

- 4 容器(postgres / redis / api / web)运行中
- `AUTH_ENABLED=false`,可用 localStorage 注 dev token 进所有页面
- 本地 PG 有 18 个真实客户(从云端 dump 同步过)
- `.env` 含完整云端 secrets(28 个 env 1:1 镜像)

---

## 6. 已知阻塞 / 风险

| ID | 描述 | 应对 |
|---|---|---|
| BL-1 | 子 agent 的 Bash 工具被沙箱拦截(即使 bypassPermissions) | 主 session 直接做,放弃多 agent 并行 |
| BL-2 | dreamy-darwin worktree 可能还在跑别的 session 编辑文件 | 阶段 1 commit 前再 git status,必要时单独跟用户确认 |
| BL-3 | 本地 docker-compose 仍是 PG 16,跟云端 PG 18 不一致 | 阶段 1 改回 18 + 重建数据卷 |
| BL-4 | prod 上 alembic 003 / 004 迁移没跑过,deploy 时 entrypoint 跑 `alembic upgrade head` 是首次执行 | 必须可回滚(004 downgrade 已写) |

---

## 7. 待补充的调查项

- [ ] dreamy-darwin worktree 的 HEAD 提交是什么(已知最新可见 `8cf63bb`,可能有更新)
- [ ] AGENTS.md / BUSINESS_FLOW_CHECKLIST.md 完整内容是否需要修订(初判直接合并即可)
- [ ] 003 迁移和模型字段定义是否完全一致
- [ ] 前端是否有任何文件已经引用了 `unit_price_after_discount` / `profit_margin_target`(链路完整性)
