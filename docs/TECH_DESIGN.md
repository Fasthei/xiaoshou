# 销售系统技术实施方案

## 1. 系统架构设计

### 1.1 整体架构

采用**微服务架构 + 前后端分离**的设计模式：

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  销售端 Web  │  │  管理端 Web  │  │  移动端 H5   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTPS/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      API 网关层                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Kong / Nginx  (认证、鉴权、限流、路由、日志)            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      业务服务层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │客户服务  │ │货源服务  │ │分配服务  │ │用量服务  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │CRM服务   │ │账单服务  │ │预警服务  │ │Agent服务 │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      数据集成层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │工单系统  │ │云管系统  │ │交付表    │ │CRM系统   │      │
│  │适配器    │ │适配器    │ │适配器    │ │适配器    │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      数据存储层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │PostgreSQL│ │Redis     │ │MongoDB   │ │ClickHouse│      │
│  │(业务数据)│ │(缓存)    │ │(日志)    │ │(分析)    │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      基础设施层                               │
│  消息队列(RabbitMQ)  定时任务(XXL-Job)  监控(Prometheus)    │
│  日志(ELK)  链路追踪(Jaeger)  配置中心(Nacos)               │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 架构特点

- **微服务化**：按业务领域拆分服务，独立部署、独立扩展
- **数据集成层**：统一管理外部系统对接，降低耦合
- **缓存优先**：高频查询数据使用 Redis 缓存
- **异步处理**：数据同步、预警计算等使用消息队列异步处理
- **读写分离**：分析型查询使用 ClickHouse，业务查询使用 PostgreSQL

---

## 2. 技术栈选型

### 2.1 前端技术栈

**推荐方案：Vue 3 + TypeScript + Element Plus**

- **框架**：Vue 3 (Composition API)
- **语言**：TypeScript
- **UI 组件库**：Element Plus
- **状态管理**：Pinia
- **路由**：Vue Router 4
- **HTTP 客户端**：Axios
- **图表**：ECharts
- **构建工具**：Vite
- **代码规范**：ESLint + Prettier

**选型理由**：
- Vue 3 生态成熟，学习曲线平缓
- TypeScript 提供类型安全
- Element Plus 组件丰富，适合企业级应用
- Vite 构建速度快，开发体验好

### 2.2 后端技术栈

**推荐方案：Spring Boot + Java 17**

- **框架**：Spring Boot 3.x
- **语言**：Java 17
- **ORM**：MyBatis Plus
- **API 文档**：Knife4j (Swagger)
- **安全框架**：Spring Security + JWT
- **参数校验**：Hibernate Validator
- **工具库**：Hutool、Lombok
- **JSON 处理**：Jackson

**选型理由**：
- Spring Boot 生态完善，企业级应用首选
- Java 17 LTS 版本，性能和稳定性好
- MyBatis Plus 简化 CRUD 操作
- 团队技术栈匹配度高

### 2.3 数据存储技术栈

| 存储类型 | 技术选型 | 用途 |
|---------|---------|------|
| 关系型数据库 | PostgreSQL 14+ | 业务主数据存储 |
| 缓存 | Redis 7.x | 热点数据缓存、分布式锁 |
| 文档数据库 | MongoDB 6.x | 日志、Agent 分析结果 |
| 分析型数据库 | ClickHouse | 用量数据、报表分析 |
| 对象存储 | MinIO / 阿里云 OSS | 文件、账单附件 |

### 2.4 中间件技术栈

- **消息队列**：RabbitMQ 3.x
- **任务调度**：XXL-Job
- **API 网关**：Kong / Spring Cloud Gateway
- **配置中心**：Nacos
- **服务注册发现**：Nacos
- **分布式事务**：Seata (按需)

### 2.5 DevOps 技术栈

- **容器化**：Docker + Docker Compose
- **容器编排**：Kubernetes (生产环境)
- **CI/CD**：GitLab CI / Jenkins
- **监控**：Prometheus + Grafana
- **日志**：ELK (Elasticsearch + Logstash + Kibana)
- **链路追踪**：Jaeger / SkyWalking

## 3. 核心服务设计

### 3.1 客户服务 (Customer Service)

**职责**：
- 客户主档管理
- 客户信息同步
- 客户标签与分类
- 客户联系人管理

**核心接口**：
- `POST /api/customers` - 创建客户
- `GET /api/customers/{id}` - 查询客户详情
- `PUT /api/customers/{id}` - 更新客户信息
- `GET /api/customers` - 客户列表查询（支持分页、筛选）
- `POST /api/customers/sync` - 从工单系统同步客户

**数据库表**：
- `customer` - 客户主表
- `customer_contact` - 客户联系人
- `customer_tag` - 客户标签
- `customer_sync_log` - 同步日志

### 3.2 货源服务 (Resource Service)

**职责**：
- 货源池管理
- 货源状态跟踪
- 货源分类与标识
- 成本信息管理

**核心接口**：
- `GET /api/resources` - 货源列表（支持按类型、状态筛选）
- `GET /api/resources/{id}` - 货源详情
- `GET /api/resources/available` - 可分配货源查询
- `POST /api/resources/sync` - 从云管系统同步货源
- `PUT /api/resources/{id}/status` - 更新货源状态

**数据库表**：
- `resource` - 货源主表
- `resource_cost` - 成本信息
- `resource_sync_log` - 同步日志

### 3.3 分配服务 (Allocation Service)

**职责**：
- 货源分配管理
- 分配关系维护
- 分配历史记录
- 价格与毛利计算

**核心接口**：
- `POST /api/allocations` - 创建分配
- `GET /api/allocations/{id}` - 分配详情
- `GET /api/allocations/customer/{customerId}` - 客户分配列表
- `GET /api/allocations/resource/{resourceId}` - 货源分配历史
- `PUT /api/allocations/{id}/status` - 更新分配状态
- `GET /api/allocations/{id}/profit` - 毛利计算

**数据库表**：
- `allocation` - 分配主表
- `allocation_price` - 价格信息
- `allocation_history` - 分配历史

### 3.4 用量服务 (Usage Service)

**职责**：
- 用量数据采集
- 用量趋势分析
- 用量预测
- 异常检测

**核心接口**：
- `GET /api/usage/customer/{customerId}` - 客户用量查询
- `GET /api/usage/resource/{resourceId}` - 货源用量查询
- `GET /api/usage/trend` - 用量趋势分析
- `GET /api/usage/forecast` - 用量预测
- `POST /api/usage/sync` - 从云管系统同步用量数据
- `GET /api/usage/breakdown` - 三层下钻：客户 → 货源 → 服务（按类目 compute/ai/database/storage/network/other 分桶）；数据源 `cc_usage.raw.accounts[]`，前端在**预警中心**「用量查看」Tab 消费

**数据库表**：
- `usage_record` - 用量记录（ClickHouse）
- `usage_summary` - 用量汇总（PostgreSQL）
- `usage_sync_log` - 同步日志

### 3.5 CRM 服务 (CRM Service)

**职责**：
- 商机管理
- 跟进记录
- 客户画像
- 潜客评分

**核心接口**：
- `POST /api/crm/opportunities` - 创建商机
- `GET /api/crm/opportunities` - 商机列表
- `PUT /api/crm/opportunities/{id}` - 更新商机
- `POST /api/crm/follow-ups` - 添加跟进记录
- `GET /api/crm/customers/{id}/profile` - 客户画像
- `GET /api/crm/leads/score` - 潜客评分

**数据库表**：
- `opportunity` - 商机表
- `follow_up` - 跟进记录
- `customer_profile` - 客户画像
- `lead_score` - 潜客评分

### 3.6 账单服务 (Billing Service)

**职责**：
- 费用计算
- 折扣管理
- 账单生成
- 报价管理

**核心接口**：
- `POST /api/billing/calculate` - 费用计算
- `POST /api/billing/quotes` - 生成报价单
- `POST /api/billing/invoices` - 生成账单
- `GET /api/billing/invoices/{id}` - 账单详情
- `POST /api/billing/discounts` - 创建折扣规则
- `GET /api/billing/profit/{customerId}` - 客户毛利分析

**数据库表**：
- `invoice` - 账单表
- `quote` - 报价单
- `discount_rule` - 折扣规则
- `billing_item` - 账单明细

### 3.7 预警服务 (Alert Service)

**职责**：
- 预警规则配置
- 预警触发检测
- 预警通知推送
- 预警历史记录

**核心接口**：
- `POST /api/alerts/rules` - 创建预警规则
- `GET /api/alerts` - 预警列表
- `GET /api/alerts/{id}` - 预警详情
- `PUT /api/alerts/{id}/status` - 更新预警状态
- `POST /api/alerts/check` - 手动触发预警检测

**数据库表**：
- `alert_rule` - 预警规则
- `alert_record` - 预警记录
- `alert_notification` - 通知记录

### 3.8 Agent 服务 (Agent Service)

**职责**：
- AI 能力集成
- 客户资料补全
- 潜客评估
- 智能分析

**核心接口**：
- `POST /api/agent/enrich-customer` - 补全客户资料
- `POST /api/agent/score-lead` - 潜客评分
- `POST /api/agent/analyze-opportunity` - 商机分析
- `GET /api/agent/tasks/{id}` - 任务状态查询

**数据库表**：
- `agent_task` - Agent 任务
- `agent_result` - 分析结果（MongoDB）
- `agent_config` - Agent 配置

---

## 4. 数据库设计

### 4.1 核心表结构设计

#### 4.1.1 客户表 (customer)

```sql
CREATE TABLE customer (
    id BIGSERIAL PRIMARY KEY,
    customer_code VARCHAR(50) UNIQUE NOT NULL COMMENT '客户编号',
    customer_name VARCHAR(200) NOT NULL COMMENT '客户名称',
    customer_short_name VARCHAR(100) COMMENT '客户简称',
    industry VARCHAR(50) COMMENT '所属行业',
    region VARCHAR(50) COMMENT '所属地区',
    customer_level VARCHAR(20) COMMENT '客户级别',
    customer_status VARCHAR(20) NOT NULL COMMENT '客户状态',
    sales_user_id BIGINT COMMENT '所属销售',
    operation_user_id BIGINT COMMENT '所属运营',
    first_deal_time TIMESTAMP COMMENT '首次成交时间',
    last_follow_time TIMESTAMP COMMENT '最近跟进时间',
    current_resource_count INT DEFAULT 0 COMMENT '当前在用资源数',
    current_month_consumption DECIMAL(15,2) DEFAULT 0 COMMENT '当前月消耗',
    next_month_forecast DECIMAL(15,2) COMMENT '预计下月消耗',
    source_system VARCHAR(50) COMMENT '来源系统',
    source_id VARCHAR(100) COMMENT '来源系统ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by BIGINT,
    updated_by BIGINT,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_customer_code ON customer(customer_code);
CREATE INDEX idx_customer_status ON customer(customer_status);
CREATE INDEX idx_sales_user ON customer(sales_user_id);
```

#### 4.1.2 客户联系人表 (customer_contact)

```sql
CREATE TABLE customer_contact (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    contact_name VARCHAR(100) NOT NULL COMMENT '联系人姓名',
    contact_title VARCHAR(50) COMMENT '职位',
    contact_phone VARCHAR(20) COMMENT '电话',
    contact_email VARCHAR(100) COMMENT '邮箱',
    contact_wechat VARCHAR(50) COMMENT '微信',
    is_primary BOOLEAN DEFAULT FALSE COMMENT '是否主联系人',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_contact_customer ON customer_contact(customer_id);
```

#### 4.1.3 货源表 (resource)

```sql
CREATE TABLE resource (
    id BIGSERIAL PRIMARY KEY,
    resource_code VARCHAR(100) UNIQUE NOT NULL COMMENT '货源编号',
    resource_type VARCHAR(20) NOT NULL COMMENT '货源类型：ORIGINAL/OTHER',
    cloud_provider VARCHAR(20) COMMENT '云厂商：AWS/AZURE/GCP',
    identifier_field VARCHAR(200) COMMENT '标识字段',
    account_name VARCHAR(200) COMMENT '账号名称',
    definition_name VARCHAR(200) COMMENT '定义名称',
    cloud_account_id VARCHAR(100) COMMENT '云账号ID',
    total_quantity INT COMMENT '总数量',
    allocated_quantity INT DEFAULT 0 COMMENT '已分配数量',
    available_quantity INT COMMENT '可分配数量',
    unit_cost DECIMAL(15,4) COMMENT '单位成本',
    suggested_price DECIMAL(15,4) COMMENT '建议销售价',
    resource_status VARCHAR(20) NOT NULL COMMENT '状态',
    source_system VARCHAR(50) COMMENT '来源系统',
    source_id VARCHAR(100) COMMENT '来源系统ID',
    last_sync_time TIMESTAMP COMMENT '最近同步时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_resource_type ON resource(resource_type);
CREATE INDEX idx_resource_status ON resource(resource_status);
CREATE INDEX idx_cloud_provider ON resource(cloud_provider);
```

#### 4.1.4 分配表 (allocation)

```sql
CREATE TABLE allocation (
    id BIGSERIAL PRIMARY KEY,
    allocation_code VARCHAR(50) UNIQUE NOT NULL COMMENT '分配编号',
    customer_id BIGINT NOT NULL REFERENCES customer(id),
    resource_id BIGINT NOT NULL REFERENCES resource(id),
    allocated_quantity INT NOT NULL COMMENT '分配数量',
    unit_cost DECIMAL(15,4) COMMENT '单位成本',
    unit_price DECIMAL(15,4) COMMENT '单位售价',
    total_cost DECIMAL(15,2) COMMENT '总成本',
    total_price DECIMAL(15,2) COMMENT '总售价',
    profit_amount DECIMAL(15,2) COMMENT '毛利金额',
    profit_rate DECIMAL(5,2) COMMENT '毛利率',
    allocation_status VARCHAR(20) NOT NULL COMMENT '分配状态',
    allocated_by BIGINT COMMENT '分配人',
    allocated_at TIMESTAMP COMMENT '分配时间',
    delivery_status VARCHAR(20) COMMENT '交付状态',
    delivery_at TIMESTAMP COMMENT '交付时间',
    remark TEXT COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_allocation_customer ON allocation(customer_id);
CREATE INDEX idx_allocation_resource ON allocation(resource_id);
CREATE INDEX idx_allocation_status ON allocation(allocation_status);
```

// __CONTINUE_HERE__
