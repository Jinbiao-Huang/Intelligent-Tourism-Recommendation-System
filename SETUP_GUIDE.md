# 旅游行程规划系统 - 快速开始指南

## 项目结构

```
vue-graduation-design/
├── src/
│   ├── views/
│   │   ├── AuthView.vue          # 登录/注册页面
│   │   ├── TourPlan.vue          # 行程规划页面
│   ├── stores/
│   │   ├── user.ts              # 用户 Pinia 存储
│   ├── api/
│   │   ├── user.ts              # 用户 API 服务
│   ├── router/
│   │   ├── index.ts             # 路由配置（带守卫）
│   ├── App.vue
│   └── main.ts

backend/
├── app.py                         # Flask 后端应用
├── requirements.txt               # Python 依赖
└── .env                          # 环境配置
```

## 前置要求

1. **Node.js** (v16+)
2. **Python** (v3.8+)
3. **MySQL** (v5.7+ 或 MySQL 8.0+)

## 安装步骤

### 1. 前端设置

```bash
cd vue-graduation-design

# 安装依赖（包括 axios）
npm install axios

# 启动开发服务器
npm run dev
```

访问 `http://localhost:5173` (或显示的端口)

### 2. 后端设置

#### 创建 MySQL 数据库

```sql
-- 登录 MySQL
mysql -u root -p

-- 创建数据库
CREATE DATABASE tour_planning CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### 配置后端环境

```bash
cd backend

.\venv\Scripts\python.exe

# 创建 Python 虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 安装 Python 依赖
pip install -r requirements.txt

# 修改 .env 文件中的数据库配置（如果需要）
# DB_HOST=localhost
# DB_USER=root
# DB_PASSWORD=（你的密码）
# DB_NAME=tour_planning

# 启动后端服务
python app.py
```

后端服务将运行在 `http://localhost:5000`

#### 使用 Navicat 执行数据库迁移脚本

当需要新增路线规划表时，请执行迁移脚本 [backend/migrate_route_plans.sql](backend/migrate_route_plans.sql)。

1. 打开 Navicat，连接到你的 MySQL。
2. 在左侧数据库列表中选择 `tour_planning`。
3. 右键数据库名称，选择“新建查询”。
4. 打开脚本文件并复制内容，粘贴到查询窗口。
5. 点击“运行”，执行成功后刷新表列表，确认出现 `route_plans` 表。

### 3. 测试认证流程

1. 打开浏览器访问前端：`http://localhost:5173`
2. 点击"注册"，创建新账户
3. 输入用户名、邮箱、密码，完成注册
4. 注册成功后自动跳转到行程规划页面
5. 点击用户名下拉菜单，选择"登出"

## 数据库说明

### users 表

存储用户信息：
- `id`: 用户 ID (自增主键)
- `username`: 用户名 (唯一)
- `email`: 邮箱 (唯一)
- `password`: 加密密码
- `created_at`: 创建时间
- `updated_at`: 更新时间

### tour_plans 表

存储用户的旅游行程：
- `id`: 行程 ID (自增主键)
- `user_id`: 用户 ID (外键)
- `destination`: 目的地
- `start_date`: 开始日期
- `end_date`: 结束日期
- `budget`: 预算
- `preferences`: 偏好设置 (JSON)
- `plan_data`: 行程数据 (JSON)
- `created_at`: 创建时间
- `updated_at`: 更新时间

## API 端点

### 认证相关

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/auth/me` | 获取当前用户信息（需要 JWT token） |

### 行程相关

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/tours` | 创建行程（需要 JWT token） |
| GET | `/api/tours` | 获取用户所有行程（需要 JWT token） |
| POST | `/api/itinerary/generate` | 生成智能行程（POI 推荐算法） |
| POST | `/api/poi/recommend` | 独立 POI 推荐接口 |
| POST | `/api/poi/pull` | 拉取高德 POI 并入库缓存 |

### 接口字段说明（简版）

#### 1) POST `/api/itinerary/generate`

请求体（JSON）：
- `destination` (string, 必填): 目的地城市，如 `西安`
- `days` (number, 必填): 出游天数，必须大于 0
- `budget` (number|string, 选填): 总预算金额，默认 `1800`
- `preferences` (string[], 选填): 兴趣偏好数组
- `recommend_focus` (string, 选填): 推荐侧重，`rating|distance`，默认 `rating`

响应体（JSON）：
- `destination` (string): 目的地
- `days` (number): 天数
- `recommend_focus` (string): 本次生效的推荐侧重
- `budget` (number): 解析后的预算金额
- `estimated_cost` (number): 行程预计消费总金额
- `plans` (DayPlan[]): 每日行程

`DayPlan` 结构：
- `day` (number): 第几天
- `activities` (PlanItem[]): 当天活动列表

`PlanItem` 常用字段：
- `time` (string): 时间段
- `content` (string): 地点名称
- `category` (string): 类型（景点/餐饮/住宿）
- `cost` (number): 该活动预计消费
- `rating` (number|null): 评分
- `location` (string): 经纬度 `lng,lat`
- `poi_type` (string): POI 类型
- `recommend_reason` (string): 推荐理由
- `tips` (string): 行程建议
- `next_distance` (number|null): 到下一地点距离（米）

#### 2) POST `/api/poi/recommend`

请求体（JSON）：
- `destination` (string, 必填): 目的地城市
- `category` (string, 选填): 推荐分类，建议 `景点|餐饮|住宿`，默认 `景点`
- `budget` (number|string, 选填): 总预算金额，默认 `1800`
- `days` (number, 选填): 用于折算日预算，默认 `1`
- `preferences` (string[], 选填): 兴趣偏好
- `recommend_focus` (string, 选填): `rating|distance`，默认 `rating`
- `limit` (number, 选填): 返回数量，范围 `1-25`，默认 `10`
- `keyword` (string, 选填): 自定义检索词

响应体（JSON）：
- `destination` (string): 目的地
- `category` (string): 分类
- `recommend_focus` (string): 推荐侧重
- `query` (string): 实际检索词
- `budget_target` (number): 当前分类预算目标
- `cache_upserted` (number): 本次写入/更新缓存条数
- `items` (array): POI 推荐列表

`items[]` 常用字段：
- `name` (string): 名称
- `address` (string): 地址
- `location` (string): 经纬度
- `type` (string): 高德类型
- `category` (string): 业务分类
- `rating` (number|null): 评分
- `cost` (number|null): 高德原始费用（若有）
- `estimated_cost` (number): 费用映射/兜底后的预估费用
- `cost_source` (string): 预估费用来源（`amap_raw|rule:*|fallback:*`）
- `score` (number): 综合评分
- `recommend_reason` (string): 推荐理由

#### 3) POST `/api/poi/pull`

请求体与 `/api/poi/recommend` 相同。

响应体与 `/api/poi/recommend` 基本一致，并额外返回：
- `message` (string): 固定为 `POI 拉取并入库成功`

## 环境变量配置

### 前端 (.env)

```
VITE_API_URL=http://localhost:5000/api
```

### 后端 (.env)

```
FLASK_ENV=development
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=tour_planning

JWT_SECRET_KEY=your-secret-key-change-this-in-production
```

## 生产环境建议

1. **JWT_SECRET_KEY**: 修改为强密钥
2. **CORS**: 限制允许的域名
3. **密码**: 使用更强的密码加密算法
4. **HTTPS**: 在生产环境使用 HTTPS
5. **数据库**: 定期备份数据库

## 常见问题

### 前端无法连接后端

- 确保后端服务正在运行（`python app.py`）
- 检查后端地址配置是否正确（`.env` 文件）
- 检查浏览器控制台的网络错误

### 数据库连接失败

- 确保 MySQL 服务正在运行
- 检查数据库连接参数（用户名、密码、数据库名）
- 确保已创建 `tour_planning` 数据库

### 注册/登录失败

- 检查邮箱格式是否正确
- 确保密码长度至少 6 个字符
- 查看后端日志获取详细错误信息

## 联系支持

如有问题，请查阅相关文档或提交 Issue。
