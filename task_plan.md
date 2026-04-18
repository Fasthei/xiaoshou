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
