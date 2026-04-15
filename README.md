# 销售系统 API

基于 FastAPI 开发的销售系统后端服务，提供客户管理、货源管理、分配管理和用量查询等核心功能。

## 功能模块

- **客户管理**：客户主档、联系人管理、客户列表查询
- **货源管理**：货源池管理、可分配货源查询
- **分配管理**：货源分配、毛利计算
- **用量查询**：客户用量、用量趋势、用量汇总

## 技术栈

- **框架**：FastAPI 0.109.0
- **数据库**：PostgreSQL + SQLAlchemy
- **缓存**：Redis
- **Python**：3.10+

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置数据库连接等信息。

### 3. 初始化数据库

```bash
# 创建数据库
createdb sales_system

# 运行数据库迁移（需要先安装 alembic）
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

### 4. 启动服务

```bash
# 开发模式
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或者直接运行
python main.py
```

### 5. 访问 API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 接口

### 客户管理

- `POST /api/customers` - 创建客户
- `GET /api/customers/{id}` - 查询客户详情
- `PUT /api/customers/{id}` - 更新客户信息
- `GET /api/customers` - 客户列表查询
- `POST /api/customers/{id}/contacts` - 添加客户联系人

### 货源管理

- `POST /api/resources` - 创建货源
- `GET /api/resources/{id}` - 查询货源详情
- `PUT /api/resources/{id}` - 更新货源信息
- `GET /api/resources` - 货源列表查询
- `GET /api/resources/available` - 查询可分配货源

### 分配管理

- `POST /api/allocations` - 创建分配
- `GET /api/allocations/{id}` - 查询分配详情
- `PUT /api/allocations/{id}` - 更新分配信息
- `GET /api/allocations` - 分配列表查询
- `GET /api/allocations/{id}/profit` - 查询分配毛利

### 用量查询

- `GET /api/usage/customer/{id}` - 查询客户用量
- `GET /api/usage/resource/{id}` - 查询货源用量
- `GET /api/usage/customer/{id}/summary` - 客户用量汇总
- `GET /api/usage/customer/{id}/trend` - 客户用量趋势

## 项目结构

```
xiaoshou/
├── app/
│   ├── api/              # API 路由
│   │   ├── customer.py
│   │   ├── resource.py
│   │   ├── allocation.py
│   │   └── usage.py
│   ├── models/           # 数据库模型
│   │   ├── customer.py
│   │   ├── resource.py
│   │   ├── allocation.py
│   │   └── usage.py
│   ├── schemas/          # Pydantic 模型
│   │   ├── customer.py
│   │   ├── resource.py
│   │   ├── allocation.py
│   │   └── usage.py
│   ├── config.py         # 配置管理
│   └── database.py       # 数据库连接
├── main.py               # 应用入口
├── requirements.txt      # 依赖列表
├── .env.example          # 环境变量示例
└── README.md             # 项目说明
```

## 开发说明

### 数据库模型

所有模型都继承自 `Base`，使用 SQLAlchemy ORM。

### API 响应格式

成功响应：
```json
{
  "id": 1,
  "customer_name": "测试客户",
  ...
}
```

错误响应：
```json
{
  "detail": "错误信息"
}
```

### 分页查询

列表接口支持分页，参数：
- `page`: 页码（从1开始）
- `page_size`: 每页数量（默认20，最大100）

响应格式：
```json
{
  "total": 100,
  "items": [...]
}
```

## 后续开发计划

- [ ] 用户认证与权限管理
- [ ] 预警功能
- [ ] CRM 商机管理
- [ ] 账单生成
- [ ] Agent 智能分析
- [ ] 数据同步功能
- [ ] 报表与看板

## 许可证

MIT
