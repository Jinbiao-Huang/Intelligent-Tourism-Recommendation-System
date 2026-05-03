目录
1绪论	1
1.1研究背景与意义	1
1.2国内外研究现状	2
1.3研究内容与创新点	3
1.4论文结构安排	4
2相关技术介绍	5
2.1开发环境与工具链	5
2.1.1前端开发环境（Vue3/Vite/TypeScript）	6
2.1.2后端开发环境（Flask/Python/MySQL）	7
2.1.3第三方服务与部署环境（高德地图/Socket.IO）	8
2.2关键技术	9
2.2.1前后端分离与RESTful API	9
2.2.2WebSocket实时通信机制	10
2.2.3缓存与数据一致性策略	11
3需求分析	12
3.1业务需求分析	12
3.1.1用户角色与使用场景	13
3.1.2核心功能需求	14
3.2非功能需求分析	15
3.3可行性分析	18
4系统总体设计	21
4.1系统开发流程	21
4.2系统架构设计	22
4.2.1前端架构设计	22
4.2.2后端架构设计	23
4.2.3数据库与核心表设计	24
4.3核心业务流程设计	25
4.3.1行程生成流程	25
4.3.2协作会话流程	26
5POI数据聚合与缓存设计	27
5.1POI数据来源与分类映射策略	27
5.2多关键词与分页聚合策略	28
5.3缓存表结构与写入更新机制	29
5.4费用估算规则与预算映射	30
5.5候选池容量与多样性优化	31
6可解释推荐与预算约束的多日行程生成设计与实现	32
6.1多日行程建模与约束定义	32
6.2推荐排序策略与可解释性输出	33
6.4路线组织与日程节奏生成	35
6.5算法流程与接口实现	36
7行程编辑与轻量实时协作实现	37
7.1协作会话模型与权限设计	37
7.2WebSocket与轮询双通道同步	38
7.3版本控制与冲突检测处理	39
7.4协作变更日志与可追溯机制	40
7.5前端协作交互实现	41
8系统测试与结果分析	42
8.1测试环境与测试数据	42
8.2功能测试	43
8.3性能测试	46
8.4结果分析与问题讨论	48
9总结与展望	49
9.1工作总结	49
9.2不足与改进方向	50
9.3未来展望	51
参考文献	52
致谢	53

# 4 系统总体设计

## 4.2 系统架构设计

系统采用前后端分离的三层架构，分为表现层（Vue3 单页应用）、业务层（Flask API + Socket.IO 实时协作）与数据层（MySQL + POI 缓存），同时通过高德地图服务补充地理与 POI 信息。整体链路是“前端请求 -> 后端聚合/计算 -> 数据库存储 -> 前端展示”，协作链路则是“前端 WebSocket -> 协作房间 -> 变更落库”。

### 4.2.1 前端架构设计

- 视图层：基于 Vue3 组件化组织页面，关键页面包括行程生成、编辑协作、管理后台与历史记录。
- 路由层：使用 Vue Router 管理多视图切换，结合路由守卫完成登录态控制。
- 状态层：使用 Pinia 管理用户信息、行程数据、协作会话状态与缓存数据。
- 服务层：按领域拆分 `api/` 请求模块，统一封装鉴权头、错误处理与重试策略。
- 实时协作：`services/collabSocket.ts` 通过 Socket.IO 与后端建立长连接，支持变更同步与版本校验。

### 4.2.2 后端架构设计

- 接口层：Flask 提供 RESTful API（登录、行程生成、路线规划、POI 查询、管理统计等）。
- 认证层：JWT 负责身份鉴权，区分普通用户与管理员权限范围。
- 业务层：包含行程规划引擎、POI 聚合与缓存写入、协作会话管理、变更记录落库。
- 协作层：Flask-SocketIO 管理房间、成员与广播，支持实时编辑与版本控制。
- 数据层：MySQL 存储用户、行程、路线、协作与 POI 缓存数据，部分字段以 JSON 形式保存结构化结果。

### 4.2.3 数据库与核心表设计

数据库以用户为中心组织数据，核心实体包括：用户、行程方案、路线规划、行程生成记录、协作行程、协作成员、协作变更、POI 缓存与 POI 费用规则。表之间关系如下：

- `users` 与 `tour_plans`、`route_plans`、`itinerary_records` 为一对多。
- `users` 与 `collab_itineraries`（owner_user_id）为一对多；并通过 `collab_itinerary_members` 形成多对多协作关系。
- `collab_itineraries` 与 `collab_itinerary_changes` 为一对多，记录协作变更历史。
- `poi_cache` 与 `poi_cost_rules` 为独立缓存/规则表，不直接依赖用户表。

ER 图如下（关键字段与外键关系已标注）：

```mermaid
erDiagram
	USERS {
		int id PK
		varchar username
		varchar email
		varchar password
		datetime created_at
		datetime updated_at
	}

	TOUR_PLANS {
		int id PK
		int user_id FK
		varchar destination
		date start_date
		date end_date
		decimal budget
		json preferences
		json plan_data
		datetime created_at
		datetime updated_at
	}

	ROUTE_PLANS {
		int id PK
		int user_id FK
		varchar origin_address
		varchar destination_address
		varchar origin_lnglat
		varchar destination_lnglat
		varchar mode
		int distance
		int duration
		decimal cost
		json steps
		datetime created_at
	}

	ITINERARY_RECORDS {
		int id PK
		int user_id FK
		varchar destination
		int days
		tinyint has_edited_destination
		varchar edited_from
		varchar edited_to
		datetime created_at
	}

	COLLAB_ITINERARIES {
		int id PK
		int owner_user_id FK
		varchar title
		varchar destination
		int days
		json plan_data
		varchar share_token
		int version
		int last_editor_user_id FK
		datetime created_at
		datetime updated_at
	}

	COLLAB_ITINERARY_MEMBERS {
		int id PK
		int itinerary_id FK
		int user_id FK
		varchar role
		datetime created_at
	}

	COLLAB_ITINERARY_CHANGES {
		bigint id PK
		int itinerary_id FK
		int version
		int editor_user_id FK
		varchar summary
		json change_payload
		datetime created_at
	}

	POI_CACHE {
		bigint id PK
		varchar city
		varchar category
		varchar query_keyword
		varchar amap_poi_id
		varchar name
		varchar address
		varchar location
		varchar poi_type
		decimal rating
		decimal raw_cost
		decimal estimated_cost
		varchar cost_source
		json raw_payload
		datetime last_fetched_at
		datetime created_at
	}

	POI_COST_RULES {
		int id PK
		varchar category
		varchar type_keyword
		decimal default_cost
		int priority
		tinyint enabled
		varchar remark
		datetime created_at
		datetime updated_at
	}

	USERS ||--o{ TOUR_PLANS : creates
	USERS ||--o{ ROUTE_PLANS : creates
	USERS ||--o{ ITINERARY_RECORDS : logs
	USERS ||--o{ COLLAB_ITINERARIES : owns
	USERS ||--o{ COLLAB_ITINERARIES : last_edits
	USERS ||--o{ COLLAB_ITINERARY_MEMBERS : joins
	USERS ||--o{ COLLAB_ITINERARY_CHANGES : edits
	COLLAB_ITINERARIES ||--o{ COLLAB_ITINERARY_MEMBERS : has
	COLLAB_ITINERARIES ||--o{ COLLAB_ITINERARY_CHANGES : has
```

