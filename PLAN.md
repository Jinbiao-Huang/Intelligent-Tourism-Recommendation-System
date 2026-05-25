# 旅游行程规划系统 — 项目计划文档

## 1. 项目概述

一个基于 Vue 3 + Flask 的旅游行程规划系统，支持智能推荐 POI、多日行程生成、路线规划、实时协作编辑等功能，集成高德地图 API 提供地理与 POI 数据。

## 2. 技术栈

| 层 | 技术 |
|---|------|
| 前端框架 | Vue 3 + TypeScript + Vite |
| 状态管理 | Pinia |
| 路由 | Vue Router 4（含路由守卫） |
| UI 组件 | Element Plus |
| 后端框架 | Flask + Flask-SocketIO |
| 数据库 | MySQL 8.0+ |
| 认证 | JWT（Flask-JWT-Extended） |
| 实时通信 | Socket.IO（WebSocket + HTTP 轮询双通道） |
| 第三方服务 | 高德地图 API（POI 搜索、地理编码、路线规划、天气） |
| 测试 | Playwright（E2E 功能测试 + 性能测试） |

## 3. 系统架构

```
┌─────────────────────────────────────────────────┐
│                  前端 (Vue 3)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  视图层   │ │  路由层   │ │    状态层 Pinia   │ │
│  │ AuthView  │ │ /auth    │ │ user / tripHistory│ │
│  │ TourPlan  │ │ /        │ └──────────────────┘ │
│  │ AdminView │ │ /admin   │ ┌──────────────────┐ │
│  │ TripHist. │ │ /history │ │ 服务层 api/*.ts   │ │
│  └──────────┘ └──────────┘ │ collabSocket.ts  │ │
│                            └──────────────────┘ │
└──────────────────┬──────────────────────────────┘
                   │ HTTP REST + WebSocket
┌──────────────────▼──────────────────────────────┐
│               后端 (Flask)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ 认证(JWT) │ │ 行程引擎  │ │ 协作(SocketIO)   │ │
│  │ auth API  │ │ POI推荐  │ │ 房间/版本/冲突   │ │
│  │ admin API │ │ 预算约束  │ │ 变更追溯         │ │
│  └──────────┘ │ 多日编排  │ └──────────────────┘ │
│               │ 路线规划  │                       │
│               │ 天气查询  │                       │
│               └──────────┘                       │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│              数据层 (MySQL)                       │
│  users / tour_plans / route_plans                │
│  itinerary_records                               │
│  collab_itineraries / members / changes          │
│  poi_cache / poi_cost_rules                      │
└─────────────────────────────────────────────────┘
```

## 4. 核心功能模块

### 4.1 用户认证
- 注册、登录、JWT 鉴权
- 路由守卫控制未登录访问
- 管理员角色分离

### 4.2 智能行程生成
- 多关键词 POI 搜索聚合
- 综合评分排序（评分、距离、兴趣、预算、营业时间）
- 类型分桶轮询多样化
- 多日行程编排 + 预算约束
- 费用估算与校准机制
- 城市消费因子校正

### 4.3 POI 推荐
- 按城市/分类/偏好推荐
- 缓存落库（poi_cache 表）
- 可解释推荐理由输出

### 4.4 路线规划
- 高德 API 四模式（驾车/步行/骑行/公交）
- 路线保存与历史查询

### 4.5 实时协作编辑
- Socket.IO 长连接 + HTTP 轮询双通道
- 版本控制 + 冲突检测
- 变更日志与可追溯
- WebSocket 房间管理

### 4.6 管理后台
- 用户列表查看
- 行程记录查看

### 4.7 天气查询
- 高德实时天气

## 5. 数据库核心表

| 表 | 用途 |
|----|------|
| users | 用户账户 |
| tour_plans | 保存的行程方案 |
| route_plans | 保存的交通路线 |
| itinerary_records | 行程生成记录 |
| collab_itineraries | 协作行程会话 |
| collab_itinerary_members | 协作成员 |
| collab_itinerary_changes | 协作变更日志 |
| poi_cache | POI 缓存 |
| poi_cost_rules | 费用映射规则 |

## 6. API 端点一览

### 认证
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### 行程
- `POST /api/tours` / `GET /api/tours`
- `POST /api/itinerary/generate`（智能生成）
- `POST /api/itinerary/records`

### POI
- `POST /api/poi/recommend`
- `POST /api/poi/pull`（拉取+缓存）

### 协作
- `POST /api/collab/itineraries`（创建）
- `POST /api/collab/itineraries/join`（加入）
- `GET/PUT /api/collab/itineraries/<id>`
- `GET /api/collab/itineraries/<id>/changes`
- WebSocket: `collab:join/leave/patch/updated/conflict/ack`

### 地图 & 路线
- `GET /api/maps/geocode`
- `GET /api/maps/place-check`
- `POST /api/maps/route`
- `POST /api/routes` / `GET /api/routes`

### 管理
- `GET /api/admin/users`
- `GET /api/admin/itinerary-records`

### 其他
- `GET /api/weather/current`
- `GET /api/health`

## 7. POI 推荐算法要点

综合评分公式：`S = w_r·s_r + w_d·s_d + w_i·s_i + w_b·s_b + w_o·s_o`

- **评分得分**: `rating/5`，缺失时用中性值 0.70
- **距离得分**: 线性衰减，12000 米以上归零
- **兴趣得分**: 偏好关键词命中率
- **预算得分**: 低于目标高分，超过逐步惩罚
- **开放时间得分**: 匹配营业时段

推荐侧重可切换：`rating`（口碑优先）或 `distance`（距离优先）。

## 8. 重要文件说明

### 8.1 Python 后端文件

#### `backend/app.py`
Flask 主应用入口（~2400 行）。包含：
- 所有 RESTful API 路由：认证（注册/登录/获取用户）、行程（创建/查询/智能生成）、POI（推荐/拉取写入缓存）、协作（创建/加入/更新/变更日志）、地图（地理编码/地点校验/路线规划/天气）、管理后台（用户列表/行程记录）、健康检查
- 数据库连接管理、数据表初始化（users、tour_plans、route_plans、itinerary_records、collab_*、poi_*）
- JWT 认证配置与鉴权装饰器
- Socket.IO 事件处理（connect/disconnect、collab:join/leave/patch）
- 协作冲突检测（基于版本号乐观锁）与实时广播
- 高德 API 调用封装（驾车/步行/骑行/公交四种路线解析）
- POI 费用估算、缓存更新（upsert_poi_cache）、行程缓存回写

#### `backend/poi_api.py`
POI 推荐算法引擎（~1800 行）。包含：
- **POI 聚合**：多关键词查询计划、分页检索、周边搜索补量、去重
- **综合评分系统**：`S = w_r·s_r + w_d·s_d + w_i·s_i + w_b·s_b + w_o·s_o`，支持 rating/distance 两种侧重模式
- **类型分桶轮询**：多样化抽样，避免同质化堆叠
- **多日行程编排**：按节奏模式（闲游/正常/特种兵）分配每日时间段，从候选池轮换消费 POI
- **预算分配**：日预算波浪分配、类别预算目标、城市消费因子校正
- **费用估算**：关键词锚点 + 可复现波动 + 异常值校准
- **营业时间解析**：支持多段、跨天、中英文 weekday，匹配到访时段评分
- **可解释推荐理由**：基于评分、距离、偏好匹配动态生成

### 8.2 Vue 前端文件

#### 入口与配置
| 文件 | 作用 |
|------|------|
| `src/main.ts` | Vue 应用入口，注册 Pinia、Vue Router、Element Plus 及其图标库 |
| `src/App.vue` | 根组件，整体布局框架，含导航栏与路由插槽 |
| `src/router/index.ts` | 路由表（/auth、/、/admin、/trip-history）+ 路由守卫（未登录跳转登录页、非管理员拦截管理页） |

#### 视图页面
| 文件 | 作用 |
|------|------|
| `src/views/AuthView.vue` | 登录/注册双标签页面，支持邮箱密码登录与用户名邮箱注册 |
| `src/views/TourPlan.vue` | **核心页面**（~700 行）。集成行程表单、智能生成、每日行程卡片展示、协作会话面板、路线规划与保存、实时天气、地点校验与编辑（含活动增删改、名称/地址/类型的就地编辑与后台持久化） |
| `src/views/AdminView.vue` | 管理员页面，展示用户表格（ID/用户名/邮箱/创建时间/更新时间） |
| `src/views/TripHistoryView.vue` | 行程历史记录，支持查看与清空 |
| `src/views/HomeView.vue` | 首页 |
| `src/views/AboutView.vue` | 关于页面 |

#### 状态管理（Pinia Stores）
| 文件 | 作用 |
|------|------|
| `src/stores/user.ts` | 用户状态：sessionStorage 持久化、登录/注册/登出方法、管理员标识 |
| `src/stores/tripHistory.ts` | 行程历史记录：加载列表、清空、响应式状态管理 |

#### API 服务层
| 文件 | 作用 |
|------|------|
| `src/api/user.ts` | 认证 API：register、login、getCurrentUser |
| `src/api/tour.ts` | 行程 API：createTour、getTours、generateItinerary、createRecord、collabCRUD（创建/加入/获取/更新/变更日志）+ TypeScript 接口定义（PlanItem、DayPlan、CollabSessionResponse 等） |
| `src/api/map.ts` | 地图 API：geocode（地理编码）、placeCheck（地点校验）、planRoute（路线规划）、saveRoute/getRoutes（路线保存与查询） |
| `src/api/admin.ts` | 管理员 API：getUsers（用户列表）、getItineraryRecords（行程记录） |
| `src/api/weather.ts` | 天气 API：getCurrentWeather（实时天气） |

#### 协作服务
| 文件 | 作用 |
|------|------|
| `src/services/collabSocket.ts` | Socket.IO 客户端封装：连接/断开/重连、token 鉴权、房间加入/离开、`collab:patch` 实时补丁发送、各事件监听（joined/updated/conflict/ack/error/presence） |

## 9. 测试

- 功能测试：未登录重定向、已登录首页渲染（Playwright）
- 性能测试：DOMContentLoaded < 5s, Load < 8s, FCP < 4s

## 10. 项目目录结构

```
D:\my-graduation-design\
├── backend/                    # Flask 后端
│   ├── app.py                  # 主应用（API + WebSocket）
│   ├── poi_api.py              # POI 推荐算法引擎
│   └── requirements.txt
├── vue-graduation-design/      # Vue 3 前端
│   ├── src/
│   │   ├── views/              # 页面组件
│   │   ├── api/                # API 服务层
│   │   ├── stores/             # Pinia 状态
│   │   ├── router/             # 路由配置
│   │   └── services/           # WebSocket 服务
│   ├── e2e/                    # Playwright 测试
│   └── playwright.config.ts
├── realtime-collab-app/        # 独立协作子应用（React + Node）
├── SETUP_GUIDE.md              # 快速开始指南
└── graduation.md               # 毕业论文
```

## 11. 开发路线图

- [x] 用户认证系统（JWT + 注册/登录）
- [x] POI 搜索聚合与缓存
- [x] 多日行程生成引擎
- [x] 路线规划（高德多模式）
- [x] 实时协作编辑（WebSocket + 轮询）
- [x] 管理后台
- [x] 功能测试 + 性能测试
- [ ] 部署与生产优化
- [ ] 移动端适配
