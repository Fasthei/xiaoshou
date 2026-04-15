# 共享角色定义（Shared Role Catalog）

所有系统（销售 / 工单 / 超级运营中心 / 云管）共用下表角色。**在 Casdoor 的 Organization `xingyun` 层级定义**，每个系统从 JWT `roles` 字段读取，不硬编码在代码里。

## 一、角色矩阵

| 角色 Code | 中文名 | 销售 xiaoshou | 工单 | 运营中心 | 云管 |
|---|---|---|---|---|---|
| `admin` | 系统管理员 | 全部 | 全部 | 全部 | 全部 |
| `sales` | 销售 | 自己负责的客户/分配/用量 R/W | 为自己客户开工单 R/W | 看自己 KPI | 只读，关联客户的资源 |
| `sales_manager` | 销售主管 | 团队全部客户 R/W、审批分配 | 团队工单看板 | 团队 KPI + 审批 | 只读 |
| `ops` | 运营 | 自己负责的客户 R/W、货源只读 | 工单流转执行 | 全部看板 | 资源分配/调整 R/W |
| `ops_manager` | 运营主管 | 团队客户 R/W + 分配审批 | 工单升级/派单 | 全部看板 + 规则配置 | 资源池 R/W + 审批 |
| `finance` | 财务 | 只读 + 毛利/账单 R/W | 只读 | 报表只读 | 成本只读 |
| `support` | 客服/支持 | 客户只读 | 工单 R/W | 只读 | 资源只读 |
| `auditor` | 审计 | 全只读 | 全只读 | 全只读 | 全只读 |
| `readonly` | 只读用户 | 全只读 | 全只读 | 全只读 | 全只读 |

> **原则**：能力以 `code` 为准（不区分大小写）；中文名仅用于 UI 展示。
> **扩展**：未来如需 `sales_bd` / `ops_l2` 等子角色，在 Casdoor 里挂为 `sub role of sales / ops`，继承父权限。

## 二、在各系统代码里怎么用

### Python（本仓库 xiaoshou）

```python
# app/auth/roles.py  (约定放这里)
ADMIN          = "admin"
SALES          = "sales"
SALES_MANAGER  = "sales_manager"
OPS            = "ops"
OPS_MANAGER    = "ops_manager"
FINANCE        = "finance"
SUPPORT        = "support"
AUDITOR        = "auditor"
READONLY       = "readonly"
```

路由保护示例：

```python
from fastapi import Depends, HTTPException
from app.auth import require_auth, CurrentUser
from app.auth import roles

def require_roles(*required: str):
    def _dep(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
        if not any(user.has_role(r) for r in required):
            raise HTTPException(403, f"requires one of: {required}")
        return user
    return _dep

@router.post("/allocations", dependencies=[Depends(require_roles(roles.SALES, roles.SALES_MANAGER, roles.OPS_MANAGER))])
def create_allocation(...): ...
```

### Go（给云管参考）

```go
const (
    RoleAdmin        = "admin"
    RoleSales        = "sales"
    RoleSalesManager = "sales_manager"
    RoleOps          = "ops"
    RoleOpsManager   = "ops_manager"
    // ...
)

func RequireRole(roles ...string) gin.HandlerFunc { ... }
```

## 三、Casdoor 后台操作

1. **Roles → Add** 逐个建上面 9 个，Owner 都填 `xingyun`
2. 嵌套关系（可选，建议）：
   - `admin` 的 "Sub roles" 勾选 `sales_manager`, `ops_manager`, `finance`, `auditor`
   - `sales_manager` 的 "Sub roles" 勾选 `sales`
   - `ops_manager` 的 "Sub roles" 勾选 `ops`
3. **Applications → 每个 App → Token fields** 勾选 `roles`（这样 JWT 才会带）
4. **Users → 任意用户 → Roles** 分配

## 四、迁移/变更策略

- 新增角色：先在 Casdoor 建，再分批在各系统代码里加判定；老 token 不识别新角色会降级为"没权限"，安全
- 下线角色：Casdoor 移除分配，各系统继续校验，老 token 过期后自动失效
- 跨系统权限同步：只要 4 个系统读的是同一份 Casdoor，无需额外同步任务
