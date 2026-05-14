"""
旅游行程规划系统 - Flask 后端 API
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt, decode_token
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
from datetime import timedelta, datetime, date
import json
import urllib.parse
import urllib.request
import os
import secrets
import hashlib
from dotenv import load_dotenv
import re
from poi_api import POIAPIError, POIService

load_dotenv()

app = Flask(__name__)

# JWT 配置
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)

jwt = JWTManager(app)
CORS(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet",
    ping_interval=25,
    ping_timeout=60
)
socket_user_map = {}

db_initialized = False

# 第三方服务密钥
AMAP_API_KEY = os.getenv('AMAP_API_KEY', '')

# 管理员配置
ADMIN_EMAILS = os.getenv('ADMIN_EMAILS', '')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '管理员')

# MySQL 数据库连接配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '123456'),
    'database': os.getenv('DB_NAME', 'tour_planning'),
    'raise_on_warnings': True
}

# 页面注册、登录功能
def get_db_connection():
    """获取数据库连接"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as err:
        print(f"数据库连接错误: {err}")
        return None


def get_admin_emails():
    """获取管理员邮箱列表"""
    emails = [item.strip().lower() for item in ADMIN_EMAILS.split(',') if item.strip()]
    if ADMIN_EMAIL:
        emails.append(ADMIN_EMAIL.strip().lower())
    return list(dict.fromkeys(emails))


def is_admin_email(email):
    """判断是否管理员邮箱"""
    if not email:
        return False
    return email.lower() in get_admin_emails()


def is_admin_login(email, password):
    """校验管理员登录信息"""
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return False
    return email.strip().lower() == ADMIN_EMAIL.strip().lower() and password == ADMIN_PASSWORD


def ensure_admin_user():
    """确保管理员用户存在，返回用户记录"""
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email FROM users WHERE email = %s", (ADMIN_EMAIL,))
    admin_user = cursor.fetchone()

    if not admin_user:
        hashed_password = generate_password_hash(ADMIN_PASSWORD)
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (ADMIN_USERNAME, ADMIN_EMAIL, hashed_password)
        )
        conn.commit()
        admin_id = cursor.lastrowid
        admin_user = {
            'id': admin_id,
            'username': ADMIN_USERNAME,
            'email': ADMIN_EMAIL
        }

    cursor.close()
    conn.close()
    return admin_user


def init_db():
    """初始化数据库表"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # 创建旅游行程表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tour_plans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                destination VARCHAR(255) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                budget DECIMAL(10, 2),
                preferences JSON,
                plan_data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 创建交通路线表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS route_plans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                origin_address VARCHAR(255),
                destination_address VARCHAR(255),
                origin_lnglat VARCHAR(64) NOT NULL,
                destination_lnglat VARCHAR(64) NOT NULL,
                mode VARCHAR(32) NOT NULL,
                distance INT DEFAULT 0,
                duration INT DEFAULT 0,
                cost DECIMAL(10, 2) DEFAULT 0,
                steps JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 创建用户行程记录表（用于管理员查看）
        ensure_itinerary_records_table(conn)
        ensure_collaboration_tables(conn)
        ensure_poi_tables(conn)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("数据库初始化成功")
        return True
    except Error as err:
        print(f"数据库初始化失败: {err}")
        return False


@app.before_request
def ensure_db_initialized():
    """在服务启动后首次请求前初始化数据库"""
    global db_initialized
    if db_initialized:
        return
    if init_db():
        db_initialized = True


def validate_email(email):
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """验证密码强度"""
    if len(password) < 6:
        return False, "密码长度至少为6个字符"
    return True, "密码有效"


def fetch_json(url, params):
    """请求外部服务并返回 JSON 数据"""
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}"
    with urllib.request.urlopen(request_url, timeout=10) as response:
        payload = response.read().decode('utf-8')
        return json.loads(payload)


def normalize_lnglat(value):
    """规范化经纬度字符串为 'lng,lat'"""
    if isinstance(value, dict):
        lng = value.get('lng')
        lat = value.get('lat')
        if lng is None or lat is None:
            return ''
        return f"{lng},{lat}"
    if not isinstance(value, str):
        return ''
    text = value.strip()
    if ',' not in text:
        return ''
    parts = [item.strip() for item in text.split(',') if item.strip()]
    if len(parts) != 2:
        return ''
    return f"{parts[0]},{parts[1]}"


poi_service = POIService(fetch_json, normalize_lnglat, AMAP_API_KEY)


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or '').strip().lower()
    return text in ('1', 'true', 'yes', 'y', 'on')


def safe_create_table(cursor, ddl):
    """执行幂等建表，兼容 raise_on_warnings=True 时的常见告警抛错"""
    try:
        cursor.execute(ddl)
    except Error as err:
        errno = getattr(err, 'errno', None)
        # 1050: Table already exists
        # 1681: Integer display width is deprecated (MySQL 8+)
        # 1364: Field 'column_name' doesn't have a default value
        if errno in (1050, 1681, 1364):
            return
        if 'Integer display width is deprecated' in str(err):
            return
        if 'Field' in str(err) and 'doesn\'t have a default value' in str(err):
            return
        raise


def has_table_column(cursor, table_name, column_name):
    """检查当前数据库中某个表字段是否存在"""
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name)
    )
    return cursor.fetchone() is not None


def ensure_table_column(cursor, table_name, column_name, definition_sql):
    """为历史表补齐缺失字段，兼容重复添加场景"""
    if has_table_column(cursor, table_name, column_name):
        return False

    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition_sql}")
        return True
    except Error as err:
        errno = getattr(err, 'errno', None)
        if errno == 1060:
            return False
        if 'Duplicate column name' in str(err):
            return False
        raise


def ensure_column_definition(cursor, table_name, column_name, definition_sql):
    """当字段已存在但定义不符合预期时，执行列定义矫正"""
    if not has_table_column(cursor, table_name, column_name):
        return False
    cursor.execute(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {definition_sql}")
    return True


def ensure_poi_legacy_schema(cursor):
    """兼容旧版本 POI 表结构，避免线上升级时字段缺失"""
    poi_cache_columns = [
        ('raw_cost', 'DECIMAL(10, 2)'),
        ('estimated_cost', 'DECIMAL(10, 2) NOT NULL DEFAULT 0'),
        ('cost_source', "VARCHAR(64) NOT NULL DEFAULT 'fallback'"),
        ('raw_payload', 'JSON'),
        ('last_fetched_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
        ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ]
    for column_name, definition_sql in poi_cache_columns:
        ensure_table_column(cursor, 'poi_cache', column_name, definition_sql)

    # 兼容历史库：estimated_cost 可能已存在但缺少默认值/可空约束不一致
    if has_table_column(cursor, 'poi_cache', 'estimated_cost'):
        try:
            cursor.execute(
                """
                UPDATE poi_cache
                SET estimated_cost = 0
                WHERE estimated_cost IS NULL
                """
            )
        except Error:
            pass
        ensure_column_definition(
            cursor,
            'poi_cache',
            'estimated_cost',
            'DECIMAL(10, 2) NOT NULL DEFAULT 0'
        )

    default_cost_added = ensure_table_column(
        cursor,
        'poi_cost_rules',
        'default_cost',
        'DECIMAL(10, 2) NOT NULL DEFAULT 0'
    )
    ensure_table_column(cursor, 'poi_cost_rules', 'priority', 'INT NOT NULL DEFAULT 100')
    ensure_table_column(cursor, 'poi_cost_rules', 'enabled', 'TINYINT NOT NULL DEFAULT 1')
    ensure_table_column(cursor, 'poi_cost_rules', 'remark', 'VARCHAR(255)')
    ensure_table_column(cursor, 'poi_cost_rules', 'created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ensure_table_column(cursor, 'poi_cost_rules', 'updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')

    if default_cost_added and has_table_column(cursor, 'poi_cost_rules', 'cost'):
        try:
            cursor.execute(
                """
                UPDATE poi_cost_rules
                SET default_cost = cost
                WHERE cost IS NOT NULL
                """
            )
        except Error:
            # 历史库中 cost 列类型可能不一致，失败时保持默认值 0 即可
            pass


def ensure_itinerary_records_table(conn):
    """确保 itinerary_records 表存在，避免因历史库缺表导致接口报错"""
    cursor = conn.cursor()
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS itinerary_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            destination VARCHAR(255) NOT NULL,
            days INT NOT NULL,
            has_edited_destination TINYINT NOT NULL DEFAULT 0,
            edited_from VARCHAR(255),
            edited_to VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_itinerary_records_user_id (user_id),
            INDEX idx_itinerary_records_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cursor.close()


def ensure_collaboration_tables(conn):
    """确保轻量协作相关表存在"""
    cursor = conn.cursor()
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS collab_itineraries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_user_id INT NOT NULL,
            title VARCHAR(255),
            destination VARCHAR(255) NOT NULL,
            days INT NOT NULL,
            plan_data JSON NOT NULL,
            share_token VARCHAR(64) NOT NULL UNIQUE,
            version INT NOT NULL DEFAULT 1,
            last_editor_user_id INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (last_editor_user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_collab_owner_user_id (owner_user_id),
            INDEX idx_collab_share_token (share_token)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS collab_itinerary_members (
            id INT AUTO_INCREMENT PRIMARY KEY,
            itinerary_id INT NOT NULL,
            user_id INT NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'editor',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (itinerary_id) REFERENCES collab_itineraries(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE KEY uniq_collab_itinerary_user (itinerary_id, user_id),
            INDEX idx_collab_member_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS collab_itinerary_changes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            itinerary_id INT NOT NULL,
            version INT NOT NULL,
            editor_user_id INT,
            summary VARCHAR(255),
            change_payload JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (itinerary_id) REFERENCES collab_itineraries(id) ON DELETE CASCADE,
            FOREIGN KEY (editor_user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_collab_change_itinerary_version (itinerary_id, version),
            INDEX idx_collab_change_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cursor.close()


def ensure_poi_tables(conn):
    """确保 POI 缓存与费用规则表存在，并初始化默认规则"""
    cursor = conn.cursor()
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS poi_cache (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            city VARCHAR(120) NOT NULL,
            category VARCHAR(32) NOT NULL,
            query_keyword VARCHAR(255) NOT NULL,
            amap_poi_id VARCHAR(80) NOT NULL,
            name VARCHAR(255) NOT NULL,
            address VARCHAR(255),
            location VARCHAR(64),
            poi_type VARCHAR(255),
            pname VARCHAR(120),
            cityname VARCHAR(120),
            adname VARCHAR(120),
            rating DECIMAL(3, 1),
            raw_cost DECIMAL(10, 2),
            estimated_cost DECIMAL(10, 2) NOT NULL DEFAULT 0,
            cost_source VARCHAR(64) NOT NULL DEFAULT 'fallback',
            raw_payload JSON,
            last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_poi_cache_amap_id (amap_poi_id),
            INDEX idx_poi_cache_city_category (city, category),
            INDEX idx_poi_cache_last_fetched (last_fetched_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    safe_create_table(cursor, """
        CREATE TABLE IF NOT EXISTS poi_cost_rules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(32) NOT NULL,
            type_keyword VARCHAR(120) NOT NULL,
            default_cost DECIMAL(10, 2) NOT NULL,
            priority INT NOT NULL DEFAULT 100,
            enabled TINYINT NOT NULL DEFAULT 1,
            remark VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_poi_cost_rule (category, type_keyword),
            INDEX idx_poi_cost_rules_category_priority (category, priority)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    ensure_poi_legacy_schema(cursor)

    default_rules = [
        ('景点', '博物馆', 60, 10, 1, '景点费用映射'),
        ('景点', '景区', 90, 20, 1, '景点费用映射'),
        ('景点', '公园', 35, 30, 1, '景点费用映射'),
        ('景点', '古镇', 70, 40, 1, '景点费用映射'),
        ('餐饮', '火锅', 95, 10, 1, '餐饮费用映射'),
        ('餐饮', '餐厅', 75, 20, 1, '餐饮费用映射'),
        ('餐饮', '小吃', 38, 30, 1, '餐饮费用映射'),
        ('餐饮', '咖啡', 45, 40, 1, '餐饮费用映射'),
        ('住宿', '五星', 620, 10, 1, '住宿费用映射'),
        ('住宿', '酒店', 360, 20, 1, '住宿费用映射'),
        ('住宿', '民宿', 280, 30, 1, '住宿费用映射'),
        ('住宿', '客栈', 240, 40, 1, '住宿费用映射'),
        ('通用', '商场', 80, 10, 1, '通用费用映射'),
        ('通用', '广场', 50, 20, 1, '通用费用映射')
    ]
    cursor.executemany(
        """
        INSERT INTO poi_cost_rules
        (category, type_keyword, default_cost, priority, enabled, remark)
        VALUES (%s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            default_cost = new.default_cost,
            priority = new.priority,
            enabled = new.enabled,
            remark = new.remark
        """,
        default_rules
    )
    conn.commit()
    cursor.close()


def load_poi_cost_rules(conn):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT category, type_keyword, default_cost, priority
        FROM poi_cost_rules
        WHERE enabled = 1
        ORDER BY category ASC, priority ASC, id ASC
        """
    )
    rows = cursor.fetchall()
    cursor.close()

    rules = {}
    for row in rows:
        category = str(row.get('category') or '').strip() or '通用'
        rules.setdefault(category, []).append({
            'type_keyword': str(row.get('type_keyword') or '').strip(),
            'default_cost': float(row.get('default_cost') or 0),
            'priority': to_int(row.get('priority'), 100)
        })
    return rules


def normalize_numeric_cost(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if match:
            return float(match.group())
    return None


def build_poi_cache_id(destination, raw_poi, item):
    raw_id = str((raw_poi or {}).get('id') or (item or {}).get('amap_id') or '').strip()
    if raw_id:
        return raw_id

    seed_parts = [
        str(destination or '').strip(),
        str((item or {}).get('name') or (raw_poi or {}).get('name') or '').strip(),
        str((item or {}).get('address') or (raw_poi or {}).get('address') or '').strip(),
        str((item or {}).get('location') or (raw_poi or {}).get('location') or '').strip(),
        str((item or {}).get('type') or (raw_poi or {}).get('type') or '').strip()
    ]
    digest = hashlib.sha1('|'.join(seed_parts).encode('utf-8')).hexdigest()
    return f"local-{digest[:24]}"


def estimate_poi_cost_with_rules(raw_poi, category, rules_by_category, budget_target):
    raw_cost = poi_service.extract_poi_cost(raw_poi)
    if raw_cost is not None:
        return int(round(float(raw_cost))), 'amap_raw'

    normalized_category = str(category or '').strip() or poi_service.map_amap_type_to_category((raw_poi or {}).get('type', ''))
    haystack = ' '.join([
        str((raw_poi or {}).get('type') or ''),
        str((raw_poi or {}).get('tag') or ''),
        str((raw_poi or {}).get('name') or ''),
        str((raw_poi or {}).get('address') or '')
    ]).lower()

    category_rules = rules_by_category.get(normalized_category, []) + rules_by_category.get('通用', [])
    for rule in category_rules:
        keyword = str(rule.get('type_keyword') or '').strip().lower()
        if keyword and keyword in haystack:
            return int(round(float(rule.get('default_cost') or 0))), f"rule:{keyword}"

    category_fallback = {
        '景点': 88,
        '餐饮': 62,
        '住宿': 320
    }
    default_cost = category_fallback.get(normalized_category, 80)
    target_cost = normalize_numeric_cost(budget_target)
    if target_cost is not None:
        if normalized_category == '住宿':
            default_cost = max(default_cost, int(round(target_cost)))
        else:
            default_cost = max(default_cost, int(round(target_cost * 0.9)))

    return int(default_cost), f"fallback:{normalized_category}"


def upsert_poi_cache(cursor, destination, category, query_keyword, raw_poi, item):
    amap_poi_id = build_poi_cache_id(destination, raw_poi, item)
    rating = normalize_numeric_cost((item or {}).get('rating'))
    raw_cost = normalize_numeric_cost((item or {}).get('cost'))
    estimated_cost = normalize_numeric_cost((item or {}).get('estimated_cost')) or 0

    cursor.execute(
        """
        INSERT INTO poi_cache
        (city, category, query_keyword, amap_poi_id, name, address, location,
         poi_type, pname, cityname, adname, rating, raw_cost, estimated_cost,
         cost_source, raw_payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            city = new.city,
            category = new.category,
            query_keyword = new.query_keyword,
            amap_poi_id = new.amap_poi_id,
            name = new.name,
            address = new.address,
            location = new.location,
            poi_type = new.poi_type,
            pname = new.pname,
            cityname = new.cityname,
            adname = new.adname,
            rating = new.rating,
            raw_cost = new.raw_cost,
            estimated_cost = new.estimated_cost,
            cost_source = new.cost_source,
            raw_payload = new.raw_payload,
            last_fetched_at = CURRENT_TIMESTAMP
        """,
        (
            destination,
            category,
            query_keyword,
            amap_poi_id,
            str((item or {}).get('name') or (raw_poi or {}).get('name') or '').strip(),
            str((item or {}).get('address') or (raw_poi or {}).get('address') or '').strip() or None,
            str((item or {}).get('location') or (raw_poi or {}).get('location') or '').strip() or None,
            str((item or {}).get('type') or (raw_poi or {}).get('type') or '').strip() or None,
            str((raw_poi or {}).get('pname') or '').strip() or None,
            str((raw_poi or {}).get('cityname') or '').strip() or None,
            str((raw_poi or {}).get('adname') or '').strip() or None,
            rating,
            raw_cost,
            estimated_cost,
            str((item or {}).get('cost_source') or 'fallback').strip(),
            json.dumps(raw_poi or {}, ensure_ascii=False)
        )
    )


def extract_activity_address(tips):
    """从行程提示文本中提取地址信息"""
    text = str(tips or '').strip()
    if not text:
        return ''

    match = re.search(r"地址[:：]\s*([^|｜]+)", text)
    if not match:
        return ''
    return str(match.group(1) or '').strip()


def cache_generated_itinerary(conn, destination, plans):
    """将已生成行程中的活动写入 POI 缓存表"""
    safe_destination = str(destination or '').strip()
    if not safe_destination or not isinstance(plans, list):
        return 0

    cursor = conn.cursor()
    upserted = 0
    try:
        for day_plan in plans:
            if not isinstance(day_plan, dict):
                continue

            day_no = max(1, to_int(day_plan.get('day'), 1))
            activities = day_plan.get('activities', [])
            if not isinstance(activities, list):
                continue

            for activity in activities:
                if not isinstance(activity, dict):
                    continue

                category = str(activity.get('category') or '').strip()
                if category not in ('景点', '餐饮', '住宿'):
                    continue

                name = str(activity.get('content') or '').strip()
                if not name:
                    continue

                location = str(activity.get('location') or '').strip()
                poi_type = str(activity.get('poi_type') or '').strip()
                address = extract_activity_address(activity.get('tips'))

                raw_poi = {
                    'name': name,
                    'address': address,
                    'location': location,
                    'type': poi_type,
                    'cityname': safe_destination
                }
                item = {
                    'name': name,
                    'address': address,
                    'location': location,
                    'type': poi_type,
                    'rating': activity.get('rating'),
                    'cost': activity.get('cost'),
                    'estimated_cost': activity.get('cost'),
                    'cost_source': 'itinerary_plan'
                }

                upsert_poi_cache(
                    cursor=cursor,
                    destination=safe_destination,
                    category=category,
                    query_keyword=f'itinerary-day-{day_no}',
                    raw_poi=raw_poi,
                    item=item
                )
                upserted += 1

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cursor.close()

    return upserted


def fetch_and_cache_poi_candidates(
    destination,
    category,
    preferences,
    budget_input,
    days,
    recommend_focus,
    limit,
    keyword,
    visit_weekday=None,
    visit_date='',
    visit_time='',
    visit_time_slot=''
):
    conn = get_db_connection()
    if not conn:
        raise POIAPIError('数据库连接失败', 500)

    cursor = None
    try:
        ensure_poi_tables(conn)
        rules_by_category = load_poi_cost_rules(conn)
        cursor = conn.cursor()
        cache_stats = {'upserted': 0}

        def cost_resolver(raw_poi, poi_category, budget_target):
            return estimate_poi_cost_with_rules(raw_poi, poi_category, rules_by_category, budget_target)

        def cache_callback(raw_poi, item, context):
            upsert_poi_cache(
                cursor=cursor,
                destination=context.get('destination', ''),
                category=context.get('category', ''),
                query_keyword=context.get('query', ''),
                raw_poi=raw_poi,
                item=item
            )
            cache_stats['upserted'] += 1

        payload = poi_service.recommend_pois(
            destination=destination,
            category=category,
            preferences=preferences,
            budget_input=budget_input,
            days=days,
            recommend_focus=recommend_focus,
            limit=limit,
            keyword=keyword,
            visit_weekday=visit_weekday,
            visit_date=visit_date,
            visit_time=visit_time,
            visit_time_slot=visit_time_slot,
            cost_resolver=cost_resolver,
            item_callback=cache_callback
        )
        conn.commit()
        payload['cache_upserted'] = cache_stats['upserted']
        return payload
    except POIAPIError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Error as err:
        try:
            conn.rollback()
        except Exception:
            pass
        raise POIAPIError('POI 缓存入库失败', 500, str(err))
    except Exception as err:
        try:
            conn.rollback()
        except Exception:
            pass
        raise POIAPIError(f'POI 拉取失败: {str(err)}', 500)
    finally:
        if cursor:
            cursor.close()
        conn.close()


def parse_json_value(value, fallback):
    """兼容 MySQL JSON 字段的字典/字符串两种返回形式"""
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def generate_share_token(length=18):
    """生成用于加入协作会话的短令牌"""
    while True:
        token = secrets.token_urlsafe(length)
        if token:
            return token[:32]


def get_collab_members(cursor, itinerary_id):
    cursor.execute(
        """
        SELECT m.user_id, m.role, m.created_at AS joined_at, u.username
        FROM collab_itinerary_members m
        INNER JOIN users u ON u.id = m.user_id
        WHERE m.itinerary_id = %s
        ORDER BY m.created_at ASC, m.id ASC
        """,
        (itinerary_id,)
    )
    return cursor.fetchall()


def get_collab_changes(cursor, itinerary_id, since_version=0, limit=50):
    safe_limit = max(1, min(to_int(limit, 50), 200))
    cursor.execute(
        """
        SELECT c.id, c.version, c.editor_user_id, u.username AS editor_username,
               c.summary, c.change_payload, c.created_at
        FROM collab_itinerary_changes c
        LEFT JOIN users u ON u.id = c.editor_user_id
        WHERE c.itinerary_id = %s AND c.version > %s
        ORDER BY c.version ASC
        LIMIT %s
        """,
        (itinerary_id, max(0, to_int(since_version, 0)), safe_limit)
    )
    rows = cursor.fetchall()
    for row in rows:
        row['change_payload'] = parse_json_value(row.get('change_payload'), {})
    return rows


def get_collab_session_row(cursor, itinerary_id, user_id):
    cursor.execute(
        """
        SELECT i.id, i.owner_user_id, i.title, i.destination, i.days,
               i.plan_data, i.share_token, i.version, i.updated_at,
               i.last_editor_user_id, m.role,
               owner.username AS owner_username,
               editor.username AS last_editor_username
        FROM collab_itineraries i
        INNER JOIN collab_itinerary_members m ON m.itinerary_id = i.id AND m.user_id = %s
        LEFT JOIN users owner ON owner.id = i.owner_user_id
        LEFT JOIN users editor ON editor.id = i.last_editor_user_id
        WHERE i.id = %s
        """,
        (user_id, itinerary_id)
    )
    return cursor.fetchone()


def build_collab_session_response(cursor, session_row, since_version=None, include_plan_if_unchanged=False):
    current_version = to_int(session_row.get('version'), 1)
    normalized_since = None
    if since_version is not None:
        normalized_since = max(0, to_int(since_version, 0))

    has_updates = True if normalized_since is None else normalized_since < current_version
    plan_data = parse_json_value(session_row.get('plan_data'), [])

    if normalized_since is not None and not has_updates and not include_plan_if_unchanged:
        plan_data = None

    changes_since = normalized_since if normalized_since is not None else max(current_version - 20, 0)
    response = {
        'id': session_row.get('id'),
        'role': session_row.get('role'),
        'title': session_row.get('title') or f"{session_row.get('destination', '')} 协作行程",
        'destination': session_row.get('destination', ''),
        'days': to_int(session_row.get('days'), 1),
        'share_token': session_row.get('share_token', ''),
        'version': current_version,
        'updated_at': session_row.get('updated_at'),
        'has_updates': has_updates,
        'last_editor': {
            'id': session_row.get('last_editor_user_id'),
            'username': session_row.get('last_editor_username')
        } if session_row.get('last_editor_user_id') else None,
        'members': get_collab_members(cursor, session_row.get('id')),
        'changes': get_collab_changes(cursor, session_row.get('id'), changes_since, 60)
    }

    if plan_data is not None:
        response['plan_data'] = plan_data

    return response


def json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def extract_socket_token(auth):
    token = ''
    if isinstance(auth, dict):
        token = str(auth.get('token') or auth.get('Authorization') or '').strip()
    if not token:
        token = str(request.args.get('token', '')).strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    return token


def get_socket_user_id_from_auth(auth):
    token = extract_socket_token(auth)
    if not token:
        return None
    try:
        payload = decode_token(token)
        return int(payload.get('sub'))
    except Exception:
        return None


def get_current_socket_user_id():
    return socket_user_map.get(request.sid)


def collab_room_name(itinerary_id):
    return f"collab:{to_int(itinerary_id, 0)}"


def apply_collab_update(user_id, itinerary_id, base_version, destination, days, plan_data, summary):
    summary = (str(summary or '').strip() or '更新行程内容')[:255]

    conn = get_db_connection()
    if not conn:
        return 500, {'message': '数据库连接失败'}, None

    cursor = None
    try:
        ensure_collaboration_tables(conn)
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        cursor.execute(
            """
            SELECT i.id, i.version, i.plan_data, i.destination, i.days,
                   i.last_editor_user_id, m.role,
                   editor.username AS last_editor_username
            FROM collab_itineraries i
            INNER JOIN collab_itinerary_members m ON m.itinerary_id = i.id AND m.user_id = %s
            LEFT JOIN users editor ON editor.id = i.last_editor_user_id
            WHERE i.id = %s
            FOR UPDATE
            """,
            (user_id, itinerary_id)
        )
        current = cursor.fetchone()

        if not current:
            conn.rollback()
            return 404, {'message': '协作会话不存在或无权限'}, None

        if current.get('role') not in ('owner', 'editor'):
            conn.rollback()
            return 403, {'message': '无编辑权限'}, None

        server_version = to_int(current.get('version'), 1)
        if base_version != server_version:
            conflict_payload = {
                'message': '版本冲突：当前内容已被其他协作者更新',
                'code': 'VERSION_CONFLICT',
                'server_version': server_version,
                'server_plan_data': parse_json_value(current.get('plan_data'), []),
                'server_destination': current.get('destination', ''),
                'server_days': to_int(current.get('days'), 1),
                'last_editor': {
                    'id': current.get('last_editor_user_id'),
                    'username': current.get('last_editor_username')
                } if current.get('last_editor_user_id') else None,
                'changes_since_base': get_collab_changes(cursor, itinerary_id, base_version, 60)
            }
            conn.rollback()
            return 409, conflict_payload, None

        next_version = server_version + 1
        cursor.execute(
            """
            UPDATE collab_itineraries
            SET destination = %s,
                days = %s,
                plan_data = %s,
                version = %s,
                last_editor_user_id = %s
            WHERE id = %s
            """,
            (
                destination,
                days,
                json.dumps(plan_data, ensure_ascii=False),
                next_version,
                user_id,
                itinerary_id
            )
        )
        cursor.execute(
            """
            INSERT INTO collab_itinerary_changes
            (itinerary_id, version, editor_user_id, summary, change_payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                itinerary_id,
                next_version,
                user_id,
                summary,
                json.dumps({'destination': destination, 'days': days}, ensure_ascii=False)
            )
        )
        conn.commit()

        session_row = get_collab_session_row(cursor, itinerary_id, user_id)
        response = build_collab_session_response(cursor, session_row)
        realtime_payload = {
            'itinerary_id': itinerary_id,
            'version': response.get('version', next_version),
            'destination': response.get('destination', destination),
            'days': response.get('days', days),
            'plans': response.get('plan_data', plan_data),
            'summary': summary,
            'last_editor': response.get('last_editor')
        }
        return 200, response, realtime_payload
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return 500, {'message': f'更新协作会话失败: {str(e)}'}, None
    finally:
        if cursor:
            cursor.close()
        conn.close()


def parse_drive_route(data):
    route = data.get('route', {})
    paths = route.get('paths', [])
    path = paths[0] if paths else {}
    steps = []
    for step in path.get('steps', []) or []:
        steps.append({
            'instruction': step.get('instruction', ''),
            'distance': to_int(step.get('distance')),
            'duration': to_int(step.get('duration')),
            'road': step.get('road', ''),
            'action': step.get('action', ''),
            'assistant_action': step.get('assistant_action', ''),
            'type': 'drive'
        })
    return {
        'distance': to_int(path.get('distance')),
        'duration': to_int(path.get('duration')),
        'cost': float(path.get('tolls') or 0),
        'steps': steps
    }


def parse_walk_route(data):
    route = data.get('route', {})
    paths = route.get('paths', [])
    path = paths[0] if paths else {}
    steps = []
    for step in path.get('steps', []) or []:
        steps.append({
            'instruction': step.get('instruction', ''),
            'distance': to_int(step.get('distance')),
            'duration': to_int(step.get('duration')),
            'road': step.get('road', ''),
            'action': step.get('action', ''),
            'type': 'walk'
        })
    return {
        'distance': to_int(path.get('distance')),
        'duration': to_int(path.get('duration')),
        'cost': 0,
        'steps': steps
    }


def parse_bicycle_route(data):
    path = ((data.get('data') or {}).get('paths') or [{}])[0]
    steps = []
    for step in path.get('steps', []) or []:
        steps.append({
            'instruction': step.get('instruction', ''),
            'distance': to_int(step.get('distance')),
            'duration': to_int(step.get('duration')),
            'road': step.get('road', ''),
            'type': 'bicycle'
        })
    return {
        'distance': to_int(path.get('distance')),
        'duration': to_int(path.get('duration')),
        'cost': 0,
        'steps': steps
    }


def parse_transit_route(data):
    route = data.get('route', {})
    transits = route.get('transits', [])
    transit = transits[0] if transits else {}
    steps = []
    for segment in transit.get('segments', []) or []:
        walking = segment.get('walking') or {}
        for step in walking.get('steps', []) or []:
            steps.append({
                'instruction': step.get('instruction', '') or '步行',
                'distance': to_int(step.get('distance')),
                'duration': to_int(step.get('duration')),
                'type': 'walk'
            })

        bus = segment.get('bus') or {}
        for line in bus.get('buslines', []) or []:
            name = line.get('name') or '公交'
            departure = (line.get('departure_stop') or {}).get('name')
            arrival = (line.get('arrival_stop') or {}).get('name')
            if departure and arrival:
                instruction = f"从 {departure} 上车，乘坐 {name} 至 {arrival}"
            else:
                instruction = f"乘坐 {name}"
            steps.append({
                'instruction': instruction,
                'distance': to_int(line.get('distance')),
                'duration': to_int(line.get('duration')),
                'type': 'transit'
            })

        railway = segment.get('railway') or {}
        if railway:
            name = railway.get('name') or railway.get('trip') or '铁路'
            depart_station = (railway.get('departure_stop') or {}).get('name')
            arrive_station = (railway.get('arrival_stop') or {}).get('name')
            if depart_station and arrive_station:
                instruction = f"从 {depart_station} 乘坐 {name} 至 {arrive_station}"
            else:
                instruction = f"乘坐 {name}"
            steps.append({
                'instruction': instruction,
                'distance': to_int(railway.get('distance')),
                'duration': to_int(railway.get('duration')),
                'type': 'railway'
            })

    return {
        'distance': to_int(transit.get('distance')),
        'duration': to_int(transit.get('duration')),
        'cost': float(transit.get('cost') or 0),
        'steps': steps
    }


# ==================== 认证相关 API ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        
        # 验证输入
        if not all(k in data for k in ['username', 'email', 'password']):
            return jsonify({'message': '缺少必要的参数'}), 400
        
        username = data['username'].strip()
        email = data['email'].strip()
        password = data['password']
        
        # 验证输入
        if not username or len(username) < 3:
            return jsonify({'message': '用户名长度至少为3个字符'}), 400
        
        if not validate_email(email):
            return jsonify({'message': '邮箱格式不正确'}), 400
        
        is_valid, msg = validate_password(password)
        if not is_valid:
            return jsonify({'message': msg}), 400
        
        # 检查用户是否已存在
        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500
        
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s OR username = %s", (email, username))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'message': '用户邮箱或用户名已存在'}), 400
        
        # 创建新用户
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_password)
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        # 生成 JWT token
        access_token = create_access_token(
            identity=str(user_id),
            additional_claims={'is_admin': is_admin_email(email)}
        )
        
        return jsonify({
            'id': user_id,
            'username': username,
            'email': email,
            'token': access_token,
            'is_admin': is_admin_email(email)
        }), 201
    
    except Exception as e:
        return jsonify({'message': f'注册失败: {str(e)}'}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        
        if not all(k in data for k in ['email', 'password']):
            return jsonify({'message': '缺少必要的参数'}), 400
        
        email = data['email'].strip()
        password = data['password']
        
        if is_admin_login(email, password):
            admin_user = ensure_admin_user()
            if not admin_user:
                return jsonify({'message': '管理员账户初始化失败'}), 500

            access_token = create_access_token(
                identity=str(admin_user['id']),
                additional_claims={'is_admin': True}
            )
            return jsonify({
                'id': admin_user['id'],
                'username': admin_user['username'],
                'email': admin_user['email'],
                'token': access_token,
                'is_admin': True
            }), 200

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or not check_password_hash(user['password'], password):
            return jsonify({'message': '邮箱或密码错误'}), 401

        # 生成 JWT token
        access_token = create_access_token(
            identity=str(user['id']),
            additional_claims={'is_admin': is_admin_email(user['email'])}
        )

        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'token': access_token,
            'is_admin': is_admin_email(user['email'])
        }), 200
    
    except Exception as e:
        return jsonify({'message': f'登录失败: {str(e)}'}), 500


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """获取当前用户信息"""
    try:
        user_id = int(get_jwt_identity())

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_itinerary_records_table(conn)
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            return jsonify({'message': '用户不存在'}), 404
        
        user['is_admin'] = is_admin_email(user.get('email'))
        return jsonify(user), 200
    
    except Exception as e:
        return jsonify({'message': f'获取用户信息失败: {str(e)}'}), 500


@app.route('/api/admin/users', methods=['GET'])
@jwt_required()
def get_admin_users():
    """管理员查看用户列表"""
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        has_admin_claim = bool(claims.get('is_admin'))
        has_admin_email = bool(current_user and is_admin_email(current_user.get('email')))

        if not current_user or (not has_admin_claim and not has_admin_email):
            cursor.close()
            conn.close()
            return jsonify({'message': '无管理员权限'}), 403

        cursor.execute("SELECT id, username, email, created_at, updated_at FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify(users), 200
    except Exception as e:
        return jsonify({'message': f'获取用户列表失败: {str(e)}'}), 500


@app.route('/api/admin/itinerary-records', methods=['GET'])
@jwt_required()
def get_admin_itinerary_records():
    """管理员查看所有用户的行程记录"""
    try:
        user_id = int(get_jwt_identity())
        claims = get_jwt()

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        has_admin_claim = bool(claims.get('is_admin'))
        has_admin_email = bool(current_user and is_admin_email(current_user.get('email')))

        if not current_user or (not has_admin_claim and not has_admin_email):
            cursor.close()
            conn.close()
            return jsonify({'message': '无管理员权限'}), 403

        cursor.execute(
            """
            SELECT r.id, r.user_id, u.username, r.destination, r.days,
                   r.has_edited_destination, r.edited_from, r.edited_to, r.created_at
            FROM itinerary_records r
            INNER JOIN users u ON u.id = r.user_id
            ORDER BY r.created_at DESC, r.id DESC
            """
        )
        records = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify(records), 200
    except Exception as e:
        return jsonify({'message': f'获取行程记录失败: {str(e)}'}), 500


# ==================== 旅游行程相关 API ====================

@app.route('/api/tours', methods=['POST'])
@jwt_required()
def create_tour_plan():
    """创建旅游行程"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        
        # 验证输入
        if not all(k in data for k in ['destination', 'start_date', 'end_date']):
            return jsonify({'message': '缺少必要的参数'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_itinerary_records_table(conn)
        
        preferences = data.get('preferences')
        plan_data = data.get('plan_data')
        if isinstance(preferences, (list, dict)):
            preferences = json.dumps(preferences, ensure_ascii=False)
        if isinstance(plan_data, (list, dict)):
            plan_data = json.dumps(plan_data, ensure_ascii=False)

        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tour_plans (user_id, destination, start_date, end_date, budget, preferences, plan_data)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, data['destination'], data['start_date'], data['end_date'],
             data.get('budget'), preferences, plan_data)
        )
        conn.commit()
        
        tour_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': tour_id, 'message': '行程创建成功'}), 201
    
    except Exception as e:
        return jsonify({'message': f'创建行程失败: {str(e)}'}), 500


@app.route('/api/tours', methods=['GET'])
@jwt_required()
def get_user_tours():
    """获取用户的所有旅游行程"""
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tour_plans WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        tours = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(tours), 200
    
    except Exception as e:
        return jsonify({'message': f'获取行程失败: {str(e)}'}), 500


@app.route('/api/itinerary/records', methods=['POST'])
@jwt_required()
def create_itinerary_record():
    """记录用户行程生成/可编辑目的地修改行为"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        destination = str(data.get('destination', '')).strip()
        days = to_int(data.get('days'))
        has_edited_destination = to_bool(data.get('has_edited_destination'))
        edited_from = str(data.get('edited_from', '')).strip() or None
        edited_to = str(data.get('edited_to', '')).strip() or None

        if not destination:
            return jsonify({'message': '缺少 destination 参数'}), 400
        if days <= 0:
            return jsonify({'message': 'days 参数不合法'}), 400
        if has_edited_destination and (not edited_from or not edited_to):
            return jsonify({'message': '可编辑目的地修改记录缺少 from/to 参数'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO itinerary_records
            (user_id, destination, days, has_edited_destination, edited_from, edited_to)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                destination,
                days,
                1 if has_edited_destination else 0,
                edited_from,
                edited_to
            )
        )
        conn.commit()
        record_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({'id': record_id, 'message': '行程记录保存成功'}), 201
    except Exception as e:
        return jsonify({'message': f'保存行程记录失败: {str(e)}'}), 500


@app.route('/api/collab/itineraries', methods=['POST'])
@jwt_required()
def create_collab_itinerary():
    """创建协作行程会话"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        destination = str(data.get('destination', '')).strip()
        days = to_int(data.get('days'))
        plan_data = data.get('plans')
        title = str(data.get('title', '')).strip() or f"{destination} 协作行程"

        if not destination:
            return jsonify({'message': '缺少 destination 参数'}), 400
        if days <= 0:
            return jsonify({'message': 'days 参数不合法'}), 400
        if not isinstance(plan_data, list) or not plan_data:
            return jsonify({'message': 'plans 参数不合法'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_collaboration_tables(conn)

        cursor = conn.cursor()
        itinerary_id = None
        share_token = ''
        for _ in range(5):
            share_token = generate_share_token()
            try:
                cursor.execute(
                    """
                    INSERT INTO collab_itineraries
                    (owner_user_id, title, destination, days, plan_data, share_token, version, last_editor_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, %s)
                    """,
                    (
                        user_id,
                        title,
                        destination,
                        days,
                        json.dumps(plan_data, ensure_ascii=False),
                        share_token,
                        user_id
                    )
                )
                itinerary_id = cursor.lastrowid
                break
            except Error as err:
                if getattr(err, 'errno', None) == 1062:
                    continue
                raise

        if not itinerary_id:
            cursor.close()
            conn.close()
            return jsonify({'message': '创建协作会话失败，请稍后重试'}), 500

        cursor.execute(
            """
            INSERT INTO collab_itinerary_members (itinerary_id, user_id, role)
            VALUES (%s, %s, 'owner')
            """,
            (itinerary_id, user_id)
        )
        cursor.execute(
            """
            INSERT INTO collab_itinerary_changes (itinerary_id, version, editor_user_id, summary, change_payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                itinerary_id,
                1,
                user_id,
                '创建协作会话',
                json.dumps({'destination': destination, 'days': days}, ensure_ascii=False)
            )
        )
        conn.commit()

        cursor = conn.cursor(dictionary=True)
        session_row = get_collab_session_row(cursor, itinerary_id, user_id)
        response = build_collab_session_response(cursor, session_row)
        cursor.close()
        conn.close()
        return jsonify(response), 201
    except Exception as e:
        return jsonify({'message': f'创建协作会话失败: {str(e)}'}), 500


@app.route('/api/collab/itineraries/join', methods=['POST'])
@jwt_required()
def join_collab_itinerary():
    """通过 share_token 加入协作会话"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        share_token = str(data.get('share_token', '')).strip()

        if not share_token:
            return jsonify({'message': '缺少 share_token 参数'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_collaboration_tables(conn)

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM collab_itineraries WHERE share_token = %s",
            (share_token,)
        )
        itinerary = cursor.fetchone()
        if not itinerary:
            cursor.close()
            conn.close()
            return jsonify({'message': '协作会话不存在'}), 404

        cursor.execute(
            """
            INSERT INTO collab_itinerary_members (itinerary_id, user_id, role)
            VALUES (%s, %s, 'editor')
            ON DUPLICATE KEY UPDATE role = role
            """,
            (itinerary['id'], user_id)
        )
        conn.commit()

        session_row = get_collab_session_row(cursor, itinerary['id'], user_id)
        response = build_collab_session_response(cursor, session_row)
        cursor.close()
        conn.close()
        return jsonify(response), 200
    except Exception as e:
        return jsonify({'message': f'加入协作会话失败: {str(e)}'}), 500


@app.route('/api/collab/itineraries/<int:itinerary_id>', methods=['GET'])
@jwt_required()
def get_collab_itinerary(itinerary_id):
    """获取协作会话状态（支持 since_version 轮询增量同步）"""
    try:
        user_id = int(get_jwt_identity())
        has_since_version = request.args.get('since_version') is not None
        since_version = to_int(request.args.get('since_version'), 0)

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_collaboration_tables(conn)

        cursor = conn.cursor(dictionary=True)
        session_row = get_collab_session_row(cursor, itinerary_id, user_id)
        if not session_row:
            cursor.close()
            conn.close()
            return jsonify({'message': '协作会话不存在或无权限'}), 404

        response = build_collab_session_response(
            cursor,
            session_row,
            since_version if has_since_version else None,
            include_plan_if_unchanged=False
        )
        cursor.close()
        conn.close()
        return jsonify(response), 200
    except Exception as e:
        return jsonify({'message': f'获取协作会话失败: {str(e)}'}), 500


@app.route('/api/collab/itineraries/<int:itinerary_id>', methods=['PUT'])
@jwt_required()
def update_collab_itinerary(itinerary_id):
    """更新协作会话内容（带 version 冲突检测）"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        base_version = to_int(data.get('base_version'), 0)
        destination = str(data.get('destination', '')).strip()
        days = to_int(data.get('days'))
        plan_data = data.get('plans')
        summary = str(data.get('summary', '')).strip() or '更新行程内容'

        if base_version <= 0:
            return jsonify({'message': '缺少 base_version 参数'}), 400
        if not destination:
            return jsonify({'message': '缺少 destination 参数'}), 400
        if days <= 0:
            return jsonify({'message': 'days 参数不合法'}), 400
        if not isinstance(plan_data, list) or not plan_data:
            return jsonify({'message': 'plans 参数不合法'}), 400

        status_code, payload, realtime_payload = apply_collab_update(
            user_id=user_id,
            itinerary_id=itinerary_id,
            base_version=base_version,
            destination=destination,
            days=days,
            plan_data=plan_data,
            summary=summary
        )

        if status_code == 200 and realtime_payload:
            socketio.emit(
                'collab:updated',
                json_safe(realtime_payload),
                room=collab_room_name(itinerary_id)
            )

        return jsonify(payload), status_code
    except Exception as e:
        return jsonify({'message': f'更新协作会话失败: {str(e)}'}), 500


@app.route('/api/collab/itineraries/<int:itinerary_id>/changes', methods=['GET'])
@jwt_required()
def get_collab_itinerary_changes(itinerary_id):
    """获取协作变更日志"""
    try:
        user_id = int(get_jwt_identity())
        since_version = to_int(request.args.get('since_version'), 0)
        limit = to_int(request.args.get('limit'), 50)

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        ensure_collaboration_tables(conn)

        cursor = conn.cursor(dictionary=True)
        session_row = get_collab_session_row(cursor, itinerary_id, user_id)
        if not session_row:
            cursor.close()
            conn.close()
            return jsonify({'message': '协作会话不存在或无权限'}), 404

        changes = get_collab_changes(cursor, itinerary_id, since_version, limit)
        cursor.close()
        conn.close()
        return jsonify({
            'itinerary_id': itinerary_id,
            'version': to_int(session_row.get('version'), 1),
            'changes': changes
        }), 200
    except Exception as e:
        return jsonify({'message': f'获取协作变更日志失败: {str(e)}'}), 500
    
@socketio.on('connect')
def socket_connect(auth):
    user_id = get_socket_user_id_from_auth(auth)
    if not user_id:
        return False
    socket_user_map[request.sid] = user_id


@socketio.on('disconnect')
def socket_disconnect():
    socket_user_map.pop(request.sid, None)


@socketio.on('collab:join')
def socket_collab_join(data):
    user_id = get_current_socket_user_id()
    itinerary_id = to_int((data or {}).get('itinerary_id') or (data or {}).get('planId'), 0)

    if not user_id:
        emit('collab:error', {'code': 'UNAUTHORIZED', 'message': '未登录或 token 无效'})
        return
    if itinerary_id <= 0:
        emit('collab:error', {'code': 'INVALID_PARAM', 'message': 'itinerary_id 参数不合法'})
        return

    conn = get_db_connection()
    if not conn:
        emit('collab:error', {'code': 'DB_ERROR', 'message': '数据库连接失败'})
        return

    cursor = None
    try:
        ensure_collaboration_tables(conn)
        cursor = conn.cursor(dictionary=True)
        session_row = get_collab_session_row(cursor, itinerary_id, user_id)
        if not session_row:
            emit('collab:error', {'code': 'NO_PERMISSION', 'message': '协作会话不存在或无权限'})
            return

        join_room(collab_room_name(itinerary_id))
        emit('collab:joined', json_safe(build_collab_session_response(cursor, session_row, None, True)))
        emit(
            'collab:presence',
            {'itinerary_id': itinerary_id, 'user_id': user_id, 'event': 'join'},
            room=collab_room_name(itinerary_id),
            include_self=False
        )
    finally:
        if cursor:
            cursor.close()
        conn.close()


@socketio.on('collab:leave')
def socket_collab_leave(data):
    user_id = get_current_socket_user_id()
    itinerary_id = to_int((data or {}).get('itinerary_id') or (data or {}).get('planId'), 0)
    if not user_id or itinerary_id <= 0:
        return
    leave_room(collab_room_name(itinerary_id))
    emit(
        'collab:presence',
        {'itinerary_id': itinerary_id, 'user_id': user_id, 'event': 'leave'},
        room=collab_room_name(itinerary_id),
        include_self=False
    )


@socketio.on('collab:patch')
def socket_collab_patch(data):
    user_id = get_current_socket_user_id()
    data = data or {}

    itinerary_id = to_int(data.get('itinerary_id') or data.get('planId'), 0)
    base_version = to_int(data.get('base_version') or data.get('version'), 0)
    destination = str(data.get('destination', '')).strip()
    days = to_int(data.get('days'))
    plan_data = data.get('plans') if data.get('plans') is not None else data.get('plan_data')
    summary = str(data.get('summary', '')).strip() or '实时协作更新'

    if not user_id:
        emit('collab:error', {'code': 'UNAUTHORIZED', 'message': '未登录或 token 无效'})
        return
    if itinerary_id <= 0 or base_version <= 0:
        emit('collab:error', {'code': 'INVALID_PARAM', 'message': 'itinerary_id/base_version 参数不合法'})
        return
    if not destination or days <= 0 or not isinstance(plan_data, list) or not plan_data:
        emit('collab:error', {'code': 'INVALID_PAYLOAD', 'message': 'destination/days/plans 参数不合法'})
        return

    status_code, payload, realtime_payload = apply_collab_update(
        user_id=user_id,
        itinerary_id=itinerary_id,
        base_version=base_version,
        destination=destination,
        days=days,
        plan_data=plan_data,
        summary=summary
    )

    if status_code == 200:
        emit('collab:ack', {'itinerary_id': itinerary_id, 'version': payload.get('version')})
        emit(
            'collab:updated',
            json_safe(realtime_payload),
            room=collab_room_name(itinerary_id),
            include_self=False
        )
    elif status_code == 409:
        emit('collab:conflict', json_safe(payload))
    else:
        emit('collab:error', json_safe(payload))


# ==================== 地图 & 天气 API ====================

@app.route('/api/maps/geocode', methods=['GET'])
def geocode_address():
    """地理编码：地址 -> 经纬度（高德 API）"""
    try:
        address = request.args.get('address', '').strip()
        if not address:
            return jsonify({'message': '缺少 address 参数'}), 400

        if not AMAP_API_KEY:
            return jsonify({'message': '未配置 AMAP_API_KEY'}), 500

        data = fetch_json(
            'https://restapi.amap.com/v3/geocode/geo',
            {
                'address': address,
                'key': AMAP_API_KEY
            }
        )
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'message': f'地理编码失败: {str(e)}'}), 500


@app.route('/api/maps/place-check', methods=['GET'])
def place_check_in_city():
    """地点校验：校验关键词地点是否在指定城市范围内存在（高德 API）"""
    try:
        keyword = request.args.get('keyword', '').strip()
        city = request.args.get('city', '').strip()
        category = request.args.get('category', '').strip()

        if not keyword:
            return jsonify({'message': '缺少 keyword 参数'}), 400
        if not city:
            return jsonify({'message': '缺少 city 参数'}), 400
        if not AMAP_API_KEY:
            return jsonify({'message': '未配置 AMAP_API_KEY'}), 500

        data = fetch_json(
            'https://restapi.amap.com/v3/place/text',
            {
                'keywords': keyword,
                'city': city,
                'citylimit': 'true',
                'offset': 10,
                'page': 1,
                'key': AMAP_API_KEY
            }
        )

        if data.get('status') != '1':
            return jsonify({'message': '高德地点校验失败', 'detail': data}), 502

        pois = data.get('pois', []) or []
        matched = next((poi for poi in pois if poi_service.is_place_match(keyword, poi)), None)
        exists = bool(matched)

        suggestions = []
        if not exists:
            center = poi_service.geocode_city_center(city)
            if center:
                keywords = poi_service.map_category_keywords(category)
                around_data = poi_service.amap_around_search(center, keywords, 5000, 5)
                if around_data.get('status') == '1':
                    for poi in around_data.get('pois', []) or []:
                        suggestions.append({
                            'name': poi.get('name', ''),
                            'address': poi.get('address', ''),
                            'location': poi.get('location', ''),
                            'distance_m': to_int(poi.get('distance'))
                        })

        return jsonify({
            'keyword': keyword,
            'city': city,
            'exists': exists,
            'matched': {
                'name': matched.get('name', ''),
                'address': matched.get('address', ''),
                'location': matched.get('location', ''),
                'type': matched.get('type', ''),
                'pname': matched.get('pname', ''),
                'cityname': matched.get('cityname', ''),
                'adname': matched.get('adname', ''),
                'category': poi_service.map_amap_type_to_category(matched.get('type', '')),
                'rating': poi_service.extract_poi_rating(matched),
                'cost': poi_service.extract_poi_cost(matched)
            } if matched else None,
            'suggestions': suggestions
        }), 200
    except Exception as e:
        return jsonify({'message': f'地点校验失败: {str(e)}'}), 500


@app.route('/api/maps/route', methods=['POST'])
def plan_route():
    """路线规划：出发地 -> 目的地（高德 API）"""
    try:
        data = request.get_json() or {}
        origin = normalize_lnglat(data.get('origin'))
        destination = normalize_lnglat(data.get('destination'))
        mode = str(data.get('mode', 'driving')).strip().lower()
        city = str(data.get('city', '')).strip()
        cityd = str(data.get('cityd', '')).strip()
        strategy = str(data.get('strategy', '')).strip()

        if not origin or not destination:
            return jsonify({'message': '缺少 origin 或 destination'}), 400
        if not AMAP_API_KEY:
            return jsonify({'message': '未配置 AMAP_API_KEY'}), 500

        if mode == 'driving':
            url = 'https://restapi.amap.com/v3/direction/driving'
            params = {
                'origin': origin,
                'destination': destination,
                'extensions': 'all',
                'key': AMAP_API_KEY
            }
            if strategy:
                params['strategy'] = strategy
            data = fetch_json(url, params)
            if data.get('status') != '1':
                return jsonify({'message': '高德驾车规划失败', 'detail': data}), 502
            route = parse_drive_route(data)
        elif mode == 'walking':
            url = 'https://restapi.amap.com/v3/direction/walking'
            data = fetch_json(url, {
                'origin': origin,
                'destination': destination,
                'key': AMAP_API_KEY
            })
            if data.get('status') != '1':
                return jsonify({'message': '高德步行规划失败', 'detail': data}), 502
            route = parse_walk_route(data)
        elif mode == 'bicycling':
            url = 'https://restapi.amap.com/v4/direction/bicycling'
            data = fetch_json(url, {
                'origin': origin,
                'destination': destination,
                'key': AMAP_API_KEY
            })
            if data.get('errcode') not in (0, '0'):
                return jsonify({'message': '高德骑行规划失败', 'detail': data}), 502
            route = parse_bicycle_route(data)
        else:
            if not city:
                return jsonify({'message': '公交/地铁/高铁规划需要 city'}), 400
            url = 'https://restapi.amap.com/v3/direction/transit/integrated'
            params = {
                'origin': origin,
                'destination': destination,
                'city': city,
                'extensions': 'all',
                'key': AMAP_API_KEY
            }
            if cityd:
                params['cityd'] = cityd
            if strategy:
                params['strategy'] = strategy
            data = fetch_json(url, params)
            if data.get('status') != '1':
                return jsonify({'message': '高德公交/地铁/高铁规划失败', 'detail': data}), 502
            route = parse_transit_route(data)

        return jsonify({
            'mode': mode,
            'route': route
        }), 200
    except Exception as e:
        return jsonify({'message': f'路线规划失败: {str(e)}'}), 500


@app.route('/api/routes', methods=['POST'])
@jwt_required()
def save_route_plan():
    """保存路线规划结果"""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}

        origin_lnglat = normalize_lnglat(data.get('origin_lnglat'))
        destination_lnglat = normalize_lnglat(data.get('destination_lnglat'))
        mode = str(data.get('mode', '')).strip().lower()
        origin_address = str(data.get('origin_address', '')).strip() or None
        destination_address = str(data.get('destination_address', '')).strip() or None
        distance = to_int(data.get('distance'))
        duration = to_int(data.get('duration'))
        cost = float(data.get('cost') or 0)
        steps = data.get('steps')

        if not origin_lnglat or not destination_lnglat or not mode:
            return jsonify({'message': '缺少必要路线参数'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO route_plans
            (user_id, origin_address, destination_address, origin_lnglat, destination_lnglat,
             mode, distance, duration, cost, steps)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                origin_address,
                destination_address,
                origin_lnglat,
                destination_lnglat,
                mode,
                distance,
                duration,
                cost,
                json.dumps(steps, ensure_ascii=False) if steps is not None else None
            )
        )
        conn.commit()
        route_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({'id': route_id, 'message': '路线保存成功'}), 201
    except Exception as e:
        return jsonify({'message': f'保存路线失败: {str(e)}'}), 500


@app.route('/api/routes', methods=['GET'])
@jwt_required()
def get_route_plans():
    """获取用户保存的路线规划"""
    try:
        user_id = int(get_jwt_identity())

        conn = get_db_connection()
        if not conn:
            return jsonify({'message': '数据库连接失败'}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, origin_address, destination_address, origin_lnglat, destination_lnglat,
                   mode, distance, duration, cost, steps, created_at
            FROM route_plans
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        routes = cursor.fetchall()
        cursor.close()
        conn.close()

        for route in routes:
            if route.get('steps') and isinstance(route['steps'], str):
                try:
                    route['steps'] = json.loads(route['steps'])
                except json.JSONDecodeError:
                    route['steps'] = []
            if route.get('cost') is not None:
                route['cost'] = float(route['cost'])

        return jsonify(routes), 200
    except Exception as e:
        return jsonify({'message': f'获取路线失败: {str(e)}'}), 500


@app.route('/api/weather/current', methods=['GET'])
def get_weather_current():
    """实时天气（高德 API）"""
    try:
        city = request.args.get('city', '').strip()
        if not city:
            return jsonify({'message': '缺少 city 参数'}), 400

        if not AMAP_API_KEY:
            return jsonify({'message': '未配置 AMAP_API_KEY'}), 500

        data = fetch_json(
            'https://restapi.amap.com/v3/weather/weatherInfo',
            {
                'city': city,
                'extensions': 'base',
                'key': AMAP_API_KEY
            }
        )
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'message': f'天气查询失败: {str(e)}'}), 500


@app.route('/api/poi/recommend', methods=['POST'])
def recommend_poi_items():
    """POI 推荐：按城市、分类、预算与偏好返回候选地点"""
    try:
        data = request.get_json() or {}
        destination = str(data.get('destination', '')).strip()
        category = str(data.get('category', '景点')).strip() or '景点'
        preferences = data.get('preferences', [])
        recommend_focus = str(data.get('recommend_focus', 'rating')).strip().lower() or 'rating'
        budget_input = data.get('budget', 1800)
        days = to_int(data.get('days'), 1)
        limit = to_int(data.get('limit'), 10)
        keyword = str(data.get('keyword', '')).strip()
        visit_weekday = data.get('visit_weekday')
        visit_date = str(data.get('visit_date', '')).strip()
        visit_time = str(data.get('visit_time', '')).strip()
        visit_time_slot = str(data.get('visit_time_slot', '')).strip()

        payload = fetch_and_cache_poi_candidates(
            destination=destination,
            category=category,
            preferences=preferences,
            budget_input=budget_input,
            days=max(1, days),
            recommend_focus=recommend_focus,
            limit=min(max(1, limit), 25),
            keyword=keyword,
            visit_weekday=visit_weekday,
            visit_date=visit_date,
            visit_time=visit_time,
            visit_time_slot=visit_time_slot
        )
        return jsonify(payload), 200
    except POIAPIError as err:
        body = {'message': err.message}
        if err.detail is not None:
            body['detail'] = err.detail
        return jsonify(body), err.status_code
    except Exception as e:
        return jsonify({'message': f'POI 推荐失败: {str(e)}'}), 500


@app.route('/api/poi/pull', methods=['POST'])
def pull_poi_items():
    """拉取高德 POI 并写入缓存表，返回候选结果"""
    try:
        data = request.get_json() or {}
        destination = str(data.get('destination', '')).strip()
        category = str(data.get('category', '景点')).strip() or '景点'
        preferences = data.get('preferences', [])
        recommend_focus = str(data.get('recommend_focus', 'rating')).strip().lower() or 'rating'
        budget_input = data.get('budget', 1800)
        days = to_int(data.get('days'), 1)
        limit = to_int(data.get('limit'), 10)
        keyword = str(data.get('keyword', '')).strip()
        visit_weekday = data.get('visit_weekday')
        visit_date = str(data.get('visit_date', '')).strip()
        visit_time = str(data.get('visit_time', '')).strip()
        visit_time_slot = str(data.get('visit_time_slot', '')).strip()

        payload = fetch_and_cache_poi_candidates(
            destination=destination,
            category=category,
            preferences=preferences,
            budget_input=budget_input,
            days=max(1, days),
            recommend_focus=recommend_focus,
            limit=min(max(1, limit), 25),
            keyword=keyword,
            visit_weekday=visit_weekday,
            visit_date=visit_date,
            visit_time=visit_time,
            visit_time_slot=visit_time_slot
        )
        payload['message'] = 'POI 拉取并入库成功'
        return jsonify(payload), 200
    except POIAPIError as err:
        body = {'message': err.message}
        if err.detail is not None:
            body['detail'] = err.detail
        return jsonify(body), err.status_code
    except Exception as e:
        return jsonify({'message': f'POI 拉取失败: {str(e)}'}), 500


@app.route('/api/itinerary/generate', methods=['POST'])
def generate_itinerary():
    """根据高德 POI 生成简易行程"""
    try:
        data = request.get_json() or {}
        destination = str(data.get('destination', '')).strip()
        days = data.get('days', 0)
        preferences = data.get('preferences', [])
        recommend_focus = str(data.get('recommend_focus', 'rating')).strip().lower() or 'rating'
        budget_input = data.get('budget', 1800)
        pace = data.get('pace')
        visit_weekday = data.get('visit_weekday')
        visit_date = data.get('visit_date')
        visit_time = data.get('visit_time')
        visit_time_slot = data.get('visit_time_slot')

        payload = poi_service.generate_itinerary(
            destination=destination,
            days=days,
            preferences=preferences,
            budget_input=budget_input,
            recommend_focus=recommend_focus,
            pace=pace,
            visit_weekday=visit_weekday,
            visit_date=visit_date,
            visit_time=visit_time,
            visit_time_slot=visit_time_slot
        )

        cache_upserted = 0
        cache_conn = None
        try:
            cache_conn = get_db_connection()
            if cache_conn:
                ensure_poi_tables(cache_conn)
                cache_upserted = cache_generated_itinerary(
                    cache_conn,
                    destination,
                    payload.get('plans', [])
                )
        except Exception as cache_err:
            app.logger.warning('行程缓存写入失败: %s', str(cache_err))
        finally:
            if cache_conn:
                cache_conn.close()

        payload['cache_upserted'] = cache_upserted
        return jsonify(payload), 200
    except POIAPIError as err:
        body = {'message': err.message}
        if err.detail is not None:
            body['detail'] = err.detail
        return jsonify(body), err.status_code
    except Exception as e:
        return jsonify({'message': f'生成行程失败: {str(e)}'}), 500



# ==================== 健康检查 ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({'status': 'ok'}), 200


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': '资源不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': '服务器错误'}), 500


if __name__ == '__main__':
    # Start backend with Socket.IO transport support.
    init_db()
    socketio.run(
        app,
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', 5000)),
        debug=os.getenv('FLASK_ENV', 'development') == 'development'
    )
