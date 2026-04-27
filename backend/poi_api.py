import math
import re
from difflib import SequenceMatcher
from datetime import datetime


class POIAPIError(Exception):
    def __init__(self, message, status_code=500, detail=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class POIService:
    PREFERENCE_KEYWORDS = {
        '自然风光': '景区 公园 山 海 湖',
        '历史古迹': '博物馆 古城 寺庙 遗址',
        '现代都游': '商圈 地标 广场',
        '户外徒步': '徒步 公园 山林',
        '艺术文化': '美术馆 艺术馆 文化街区',
        '美食品尝': '美食 餐厅 小吃'
    }

    def __init__(self, fetch_json_func, normalize_lnglat_func, amap_api_key):
        self.fetch_json = fetch_json_func
        self.normalize_lnglat = normalize_lnglat_func
        self.amap_api_key = str(amap_api_key or '').strip()

    def _ensure_amap_key(self):
        if not self.amap_api_key:
            raise POIAPIError('未配置 AMAP_API_KEY', 500)

    def amap_text_search(self, keywords, city, offset, page=1):
        self._ensure_amap_key()
        safe_offset = max(1, min(25, int(offset or 10)))
        safe_page = max(1, int(page or 1))
        return self.fetch_json(
            'https://restapi.amap.com/v3/place/text',
            {
                'keywords': keywords,
                'city': city,
                'citylimit': 'true',
                'offset': safe_offset,
                'page': safe_page,
                'key': self.amap_api_key
            }
        )

    def build_category_query_plan(self, category, destination, preferences=None, keyword=''):
        cat = str(category or '景点').strip() or '景点'
        city = str(destination or '').strip()
        explicit_keyword = str(keyword or '').strip()
        prefs = preferences if isinstance(preferences, list) else []

        scenic_preference_query = ' '.join(
            [self.PREFERENCE_KEYWORDS[pref] for pref in prefs if pref in self.PREFERENCE_KEYWORDS]
        ).strip()

        if cat == '景点':
            base_queries = [
                scenic_preference_query,
                explicit_keyword,
                f"{city} 热门景点",
                '景点 公园 博物馆 景区',
                '历史街区 古镇 文化景区',
                '自然风光 山水 公园'
            ]
        elif cat == '餐饮':
            base_queries = [
                explicit_keyword,
                f"{city} 本地美食",
                '餐厅 美食 小吃',
                '特色餐馆 老字号',
                '夜市 小吃街',
                '评分高 人气餐厅'
            ]
        else:
            base_queries = [
                explicit_keyword,
                f"{city} 住宿",
                '酒店 住宿 旅馆',
                '精品酒店 民宿 客栈',
                '高评分酒店',
                '商务酒店 经济酒店'
            ]

        query_plan = []
        seen = set()
        for query in base_queries:
            text = str(query or '').strip()
            if not text:
                continue
            normalized = self.normalize_place_text(text)
            if normalized and normalized in seen:
                continue
            if normalized:
                seen.add(normalized)
            query_plan.append(text)

        if not query_plan:
            query_plan.append(self.map_category_keywords(cat))

        return query_plan

    def collect_pois_by_queries(self, destination, queries, expected_count, center_location=''):
        city = str(destination or '').strip()
        query_list = [str(query).strip() for query in (queries or []) if str(query).strip()]
        if not city or not query_list:
            return []

        expected = max(1, int(expected_count or 1))
        page_size = 25 if expected >= 22 else max(10, min(25, expected))
        max_pages = 3 if expected <= 60 else 4
        cap_count = min(260, max(expected * 2, 50))

        collected = []
        seen_keys = set()

        for query in query_list:
            for page in range(1, max_pages + 1):
                data = self.amap_text_search(query, city, page_size, page=page)
                if data.get('status') != '1':
                    continue
                pois = data.get('pois', []) or []
                if not pois:
                    break

                for poi in pois:
                    key = self.build_poi_unique_key(poi)
                    if key and key in seen_keys:
                        continue
                    if key:
                        seen_keys.add(key)
                    collected.append(poi)

                if len(collected) >= cap_count:
                    return collected
                if len(pois) < page_size:
                    break

        if center_location and len(collected) < expected:
            for radius in (3000, 6000, 10000, 16000):
                for query in query_list[:4]:
                    around_data = self.amap_around_search(center_location, query, radius, 25)
                    if around_data.get('status') != '1':
                        continue
                    around_pois = around_data.get('pois', []) or []
                    for poi in around_pois:
                        key = self.build_poi_unique_key(poi)
                        if key and key in seen_keys:
                            continue
                        if key:
                            seen_keys.add(key)
                        collected.append(poi)
                    if len(collected) >= cap_count:
                        return collected

        return collected

    def get_poi_type_bucket(self, poi):
        text = str((poi or {}).get('type') or '').strip()
        if not text:
            return 'unknown'

        for separator in (';', '|', ',', '，', '>'):
            if separator in text:
                text = text.split(separator)[0].strip()
                break

        normalized = self.normalize_place_text(text)
        return normalized or 'unknown'

    def diversify_ranked_pois(self, ranked_pois, limit):
        safe_limit = max(1, int(limit or 1))
        if not ranked_pois:
            return []

        groups = {}
        bucket_order = []

        for poi in ranked_pois:
            bucket = self.get_poi_type_bucket(poi)
            if bucket not in groups:
                groups[bucket] = []
                bucket_order.append(bucket)
            groups[bucket].append(poi)

        diversified = []
        while len(diversified) < safe_limit:
            progressed = False
            for bucket in bucket_order:
                queue = groups.get(bucket, [])
                if not queue:
                    continue
                diversified.append(queue.pop(0))
                progressed = True
                if len(diversified) >= safe_limit:
                    break
            if not progressed:
                break

        return diversified

    def map_category_keywords(self, category):
        text = str(category or '').strip()
        mapping = {
            '景点': '景点 公园 博物馆 景区',
            '餐饮': '餐厅 美食 小吃',
            '住宿': '酒店 住宿 旅馆'
        }
        if text in mapping:
            return mapping[text]
        return text or '景点 公园'

    def map_amap_type_to_category(self, amap_type):
        text = str(amap_type or '').strip()
        if not text:
            return '景点'
        if '餐饮' in text:
            return '餐饮'
        if '住宿' in text or '酒店' in text:
            return '住宿'
        return '景点'

    def normalize_pace(self, pace):
        text = str(pace or '').strip().lower()
        if not text:
            return 'intense'
        mapping = {
            'leisure': 'leisure',
            '闲游': 'leisure',
            'slow': 'leisure',
            'normal': 'normal',
            '正常旅游': 'normal',
            'standard': 'normal',
            'intense': 'intense',
            '特种兵式旅游': 'intense',
            'hardcore': 'intense',
            'fast': 'intense'
        }
        if text in mapping:
            return mapping[text]
        if '闲游' in text:
            return 'leisure'
        if '正常' in text:
            return 'normal'
        if '特种兵' in text:
            return 'intense'
        return 'intense'

    def get_time_slots_for_pace(self, pace):
        normalized = self.normalize_pace(pace)
        if normalized == 'leisure':
            return [
                {'time': '10:00', 'type': 'poi', 'label': '上午景点'},
                {'time': '12:30', 'type': 'meal', 'label': '午餐时光'},
                {'time': '20:30', 'type': 'hotel', 'label': '酒店入住'}
            ]
        if normalized == 'normal':
            return [
                {'time': '09:30', 'type': 'poi', 'label': '上午景点'},
                {'time': '12:30', 'type': 'meal', 'label': '午餐时光'},
                {'time': '15:00', 'type': 'poi', 'label': '下午景点'},
                {'time': '19:00', 'type': 'meal', 'label': '晚餐与夜景'},
                {'time': '21:30', 'type': 'hotel', 'label': '酒店入住'}
            ]
        return [
            {'time': '08:30', 'type': 'meal', 'label': '早餐补给'},
            {'time': '10:00', 'type': 'poi', 'label': '上午景点'},
            {'time': '12:30', 'type': 'meal', 'label': '午餐时光'},
            {'time': '14:30', 'type': 'poi', 'label': '下午景点'},
            {'time': '19:30', 'type': 'meal', 'label': '晚餐与夜景'},
            {'time': '21:30', 'type': 'hotel', 'label': '酒店入住'}
        ]

    def normalize_place_text(self, value):
        text = str(value or '').strip().lower()
        if not text:
            return ''
        return re.sub(r"[\s\-_,，。；;:：·()（）\[\]{}]+", '', text)

    def is_place_match(self, keyword, poi):
        target = self.normalize_place_text(keyword)
        if not target:
            return False

        candidates = [
            self.normalize_place_text((poi or {}).get('name')),
            self.normalize_place_text((poi or {}).get('address'))
        ]

        for candidate in candidates:
            if not candidate:
                continue
            if target == candidate or target in candidate or candidate in target:
                return True

            ratio = SequenceMatcher(None, target, candidate).ratio()
            if len(target) >= 4 and ratio >= 0.72:
                return True

        return False

    def geocode_city_center(self, city):
        self._ensure_amap_key()
        data = self.fetch_json(
            'https://restapi.amap.com/v3/geocode/geo',
            {
                'address': city,
                'key': self.amap_api_key
            }
        )
        if data.get('status') != '1':
            return None
        geocodes = data.get('geocodes', []) or []
        location = (geocodes[0] or {}).get('location') if geocodes else None
        return self.normalize_lnglat(location)

    def amap_around_search(self, location, keywords, radius, offset):
        self._ensure_amap_key()
        return self.fetch_json(
            'https://restapi.amap.com/v3/place/around',
            {
                'location': location,
                'keywords': keywords,
                'radius': radius,
                'sortrule': 'distance',
                'offset': offset,
                'page': 1,
                'key': self.amap_api_key
            }
        )

    def estimate_cost(self, profile, category, seed, anchor=None, variance=0.30):
        ranges = profile.get(category) or (0, 0)
        low, high = ranges
        if low == high:
            return int(low)

        if anchor is None:
            anchor = (low + high) / 2

        anchor = max(low, min(high, float(anchor)))
        span = max(1.0, float(high - low))

        # 用可复现的波动让每日/每时段费用不再机械固定。
        periodic = math.sin((seed + 5) * 1.618)
        pseudo_random = (((seed * 37) % 19) - 9) / 9
        jitter = (periodic * 0.55 + pseudo_random * 0.45) * span * variance

        value = max(low, min(high, anchor + jitter))
        return int(round(value))

    def build_daily_budget_targets(self, total_budget, days):
        safe_days = max(1, int(days or 1))
        safe_total_budget = float(total_budget or 0)
        if safe_total_budget <= 0:
            return []

        base = safe_total_budget / safe_days
        weights = []
        for day in range(1, safe_days + 1):
            wave = math.sin(day * 1.27) * 0.14
            drift = (((day * 11) % 7) - 3) * 0.018
            weights.append(max(0.78, min(1.24, 1 + wave + drift)))

        total_weight = sum(weights) or 1.0
        scale = safe_days / total_weight
        return [round(base * weight * scale, 2) for weight in weights]

    def normalize_cost_category(self, category):
        text = str(category or '').strip().lower()
        if text in ('poi', '景点'):
            return 'poi'
        if text in ('meal', 'food', '餐饮'):
            return 'meal'
        if text in ('hotel', '住宿'):
            return 'hotel'
        return 'poi'

    def normalize_recommend_focus(self, recommend_focus):
        focus = str(recommend_focus or 'rating').strip().lower()
        if focus in ('rating', 'distance'):
            return focus

        # 兼容历史值 money，统一回退到 rating。
        if focus == 'money':
            return 'rating'
        return 'rating'

    def normalize_city_name(self, destination):
        text = str(destination or '').strip()
        if not text:
            return ''

        aliases = {
            '北京市': '北京',
            '上海市': '上海',
            '广州市': '广州',
            '深圳市': '深圳',
            '天津市': '天津',
            '重庆市': '重庆',
            '香港特别行政区': '香港',
            '澳门特别行政区': '澳门'
        }
        if text in aliases:
            return aliases[text]
        return text

    def infer_city_consumption_tier(self, destination):
        city = self.normalize_city_name(destination)
        if not city:
            return 'tier2'

        tier1_cities = {
            '北京', '上海', '广州', '深圳', '香港', '澳门'
        }
        new_tier1_cities = {
            '成都', '杭州', '重庆', '武汉', '西安', '苏州', '南京', '天津',
            '长沙', '郑州', '宁波', '青岛', '东莞', '无锡', '佛山', '合肥',
            '福州', '厦门', '济南'
        }

        normalized = city.replace('市', '').replace('地区', '').replace('自治州', '').strip()
        for name in tier1_cities:
            if name in normalized:
                return 'tier1'
        for name in new_tier1_cities:
            if name in normalized:
                return 'new_tier1'

        if any(flag in city for flag in ('自治州', '地区', '盟', '县', '旗')):
            return 'tier4'
        if '市' in city or '州' in city:
            return 'tier3'
        return 'tier2'

    def get_city_scenic_cost_factor(self, destination):
        tier = self.infer_city_consumption_tier(destination)
        factors = {
            'tier1': 1.25,
            'new_tier1': 1.12,
            'tier2': 1.00,
            'tier3': 0.88,
            'tier4': 0.76
        }
        return factors.get(tier, 1.00)

    def infer_keyword_cost_anchor(self, poi, category):
        category_key = self.normalize_cost_category(category)
        haystack = ' '.join([
            str((poi or {}).get('name') or ''),
            str((poi or {}).get('type') or ''),
            str((poi or {}).get('tag') or ''),
            str((poi or {}).get('address') or '')
        ]).lower()

        rules = {
            'poi': [
                ('博物馆', 45),
                ('公园', 20),
                ('古镇', 55),
                ('景区', 68),
                ('乐园', 140),
                ('演出', 120)
            ],
            'meal': [
                ('小吃', 35),
                ('快餐', 32),
                ('火锅', 92),
                ('餐厅', 68),
                ('自助', 118)
            ],
            'hotel': [
                ('青年旅舍', 140),
                ('民宿', 240),
                ('快捷', 220),
                ('酒店', 320),
                ('豪华', 620)
            ]
        }

        for keyword, anchor in rules.get(category_key, []):
            if keyword in haystack:
                return float(anchor)
        return None

    def calibrate_activity_cost(self, poi, category, raw_cost, profile, seed, budget_target):
        category_key = self.normalize_cost_category(category)
        bounds = {
            'poi': (0, 220),
            'meal': (18, 260),
            'hotel': (90, 980)
        }
        min_cost, max_cost = bounds.get(category_key, (20, 500))

        budget_anchor = float(budget_target or 0)
        keyword_anchor = self.infer_keyword_cost_anchor(poi, category_key)
        if keyword_anchor is not None:
            budget_anchor = keyword_anchor if budget_anchor <= 0 else (budget_anchor * 0.45 + keyword_anchor * 0.55)
        if budget_anchor <= 0:
            low, high = profile.get(category_key) or (min_cost, max_cost)
            budget_anchor = (low + high) / 2

        fallback_cost = self.estimate_cost(
            profile,
            category_key,
            seed,
            anchor=budget_anchor,
            variance=0.36
        )

        if raw_cost in (None, ''):
            return fallback_cost, '估算'

        try:
            raw_value = float(raw_cost)
        except (TypeError, ValueError):
            return fallback_cost, '估算'

        if raw_value <= 0:
            return fallback_cost, '估算'

        over_limit_ratio_map = {
            'poi': 1.8,
            'meal': 2.3,
            'hotel': 3.2
        }
        over_limit_ratio = over_limit_ratio_map.get(category_key, 2.2)
        hard_over = raw_value > max(max_cost, budget_anchor * over_limit_ratio)
        hard_under = raw_value < min_cost
        if hard_over or hard_under:
            adjusted_cost = self.estimate_cost(
                profile,
                category_key,
                seed + 13,
                anchor=budget_anchor,
                variance=0.32
            )
            return adjusted_cost, '校准'

        soft_low_ratio_map = {
            'poi': 0.40,
            'meal': 0.36,
            'hotel': 0.45
        }
        soft_high_ratio_map = {
            'poi': 1.45,
            'meal': 1.85,
            'hotel': 2.8
        }
        soft_low_ratio = soft_low_ratio_map.get(category_key, 0.35)
        soft_high_ratio = soft_high_ratio_map.get(category_key, 1.8)
        soft_low = max(min_cost, budget_anchor * soft_low_ratio)
        soft_high = min(max_cost, budget_anchor * soft_high_ratio)
        calibrated = max(soft_low, min(soft_high, raw_value))

        normalized = int(round(calibrated))
        if normalized != int(round(raw_value)):
            return normalized, '校准'
        return normalized, '高德'

    def build_poi_unique_key(self, poi):
        if not isinstance(poi, dict):
            return ''

        name = self.normalize_place_text(poi.get('name'))
        address = self.normalize_place_text(poi.get('address'))
        location = self.normalize_place_text(poi.get('location'))

        if name or address or location:
            return f"{name}|{address}|{location}"

        amap_id = str(poi.get('id') or '').strip().lower()
        return f"id:{amap_id}" if amap_id else ''

    def deduplicate_poi_pool(self, pois):
        result = []
        seen = set()
        for poi in pois or []:
            key = self.build_poi_unique_key(poi)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(poi)
        return result

    def consume_next_unique_poi(self, poi_pool, cursor, used_keys):
        index = max(0, int(cursor or 0))
        pool = poi_pool or []

        while index < len(pool):
            candidate = pool[index]
            index += 1
            key = self.build_poi_unique_key(candidate)
            if key and key in used_keys:
                continue
            if key:
                used_keys.add(key)
            return candidate, index

        return None, index

    def extract_poi_cost(self, poi):
        if not poi:
            return None
        cost_keys = ['cost', 'avg_cost', 'average_price', 'avg_price', 'price']
        for key in cost_keys:
            value = poi.get(key)
            if value in (None, ''):
                continue
            match = re.search(r"\d+(?:\.\d+)?", str(value))
            if match:
                return int(float(match.group()))
        return None

    def extract_poi_rating(self, poi):
        if not poi:
            return None

        rating_candidates = [
            poi.get('rating'),
            (poi.get('biz_ext') or {}).get('rating') if isinstance(poi.get('biz_ext'), dict) else None
        ]

        for value in rating_candidates:
            if value in (None, ''):
                continue
            match = re.search(r"\d+(?:\.\d+)?", str(value))
            if not match:
                continue
            rating = float(match.group())
            if rating > 5:
                rating = 5.0
            if rating < 0:
                rating = 0.0
            return rating
        return None

    def parse_lnglat(self, value):
        text = self.normalize_lnglat(value)
        if not text:
            return None
        try:
            lng_text, lat_text = text.split(',')
            return float(lng_text), float(lat_text)
        except (ValueError, TypeError):
            return None

    def haversine_distance_m(self, point_a, point_b):
        if not point_a or not point_b:
            return None

        lng1, lat1 = point_a
        lng2, lat2 = point_b

        rad_lat1 = math.radians(lat1)
        rad_lat2 = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        value_a = math.sin(delta_lat / 2) ** 2 + math.cos(rad_lat1) * math.cos(rad_lat2) * math.sin(delta_lng / 2) ** 2
        value_c = 2 * math.atan2(math.sqrt(value_a), math.sqrt(1 - value_a))
        return 6371000 * value_c

    def normalize_weekday(self, value):
        if value is None:
            return None

        if isinstance(value, (int, float)):
            weekday = int(value)
            if 0 <= weekday <= 6:
                return weekday
            if 1 <= weekday <= 7:
                return (weekday - 1) % 7
            return None

        text = str(value).strip()
        if not text:
            return None

        if re.fullmatch(r"\d+", text):
            number = int(text)
            if 0 <= number <= 6:
                return number
            if 1 <= number <= 7:
                return (number - 1) % 7

        day_map = {
            '周一': 0,
            '星期一': 0,
            '周二': 1,
            '星期二': 1,
            '周三': 2,
            '星期三': 2,
            '周四': 3,
            '星期四': 3,
            '周五': 4,
            '星期五': 4,
            '周六': 5,
            '星期六': 5,
            '周日': 6,
            '星期日': 6,
            '周天': 6,
            '星期天': 6,
            '周末': 6
        }
        if text in day_map:
            return day_map[text]

        try:
            return datetime.strptime(text, '%Y-%m-%d').weekday()
        except ValueError:
            pass

        try:
            return datetime.fromisoformat(text).weekday()
        except ValueError:
            return None

    def normalize_visit_time(self, visit_time):
        if visit_time is None:
            return None

        text = str(visit_time).strip().lower()
        if not text:
            return None

        slot_alias = {
            'morning': '10:00',
            '上午': '10:00',
            '早上': '10:00',
            'forenoon': '10:00',
            'noon': '12:30',
            '中午': '12:30',
            'lunch': '12:30',
            'afternoon': '15:00',
            '下午': '15:00',
            'evening': '19:00',
            '傍晚': '19:00',
            '晚上': '19:00',
            'night': '21:00',
            '晚间': '21:00'
        }
        normalized = slot_alias.get(text, text)

        if re.fullmatch(r"\d{1,2}:\d{1,2}", normalized):
            hour_text, minute_text = normalized.split(':')
            hour = int(hour_text)
            minute = int(minute_text)
            if not (0 <= minute <= 59):
                return None
            if hour == 24 and minute == 0:
                return '24:00'
            if not (0 <= hour <= 23):
                return None
            return f"{hour:02d}:{minute:02d}"

        return None

    def parse_time_minutes(self, value):
        text = str(value or '').strip()
        if not text:
            return None

        match = re.fullmatch(r"(\d{1,2}):(\d{1,2})", text)
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2))
        if minute < 0 or minute > 59:
            return None
        if hour == 24 and minute == 0:
            return 1440
        if hour < 0 or hour > 23:
            return None
        return hour * 60 + minute

    def extract_poi_opening_hours(self, poi):
        if not isinstance(poi, dict):
            return ''

        biz_ext = poi.get('biz_ext') if isinstance(poi.get('biz_ext'), dict) else {}
        candidates = [
            poi.get('business_hours'),
            poi.get('opentime'),
            poi.get('open_time'),
            biz_ext.get('opentime'),
            biz_ext.get('open_time'),
            biz_ext.get('business_hours')
        ]

        for item in candidates:
            text = str(item or '').strip()
            if text:
                return text
        return ''

    def parse_segment_weekdays(self, segment_text):
        text = str(segment_text or '').strip()
        if not text:
            return None

        day_pattern = r"(?:周|星期)\s*[一二三四五六日天]"
        day_map = {
            '周一': 0,
            '星期一': 0,
            '周二': 1,
            '星期二': 1,
            '周三': 2,
            '星期三': 2,
            '周四': 3,
            '星期四': 3,
            '周五': 4,
            '星期五': 4,
            '周六': 5,
            '星期六': 5,
            '周日': 6,
            '星期日': 6,
            '周天': 6,
            '星期天': 6
        }

        def normalize_day_token(token):
            compact = re.sub(r"\s+", '', str(token or ''))
            return day_map.get(compact)

        match = re.search(rf"({day_pattern})\s*(?:-|~|至|到)\s*({day_pattern})", text)
        if match:
            start_day = normalize_day_token(match.group(1))
            end_day = normalize_day_token(match.group(2))
            if start_day is not None and end_day is not None:
                if start_day <= end_day:
                    return set(range(start_day, end_day + 1))
                return set(list(range(start_day, 7)) + list(range(0, end_day + 1)))

        tokens = re.findall(day_pattern, text)
        if not tokens:
            if '工作日' in text:
                return set(range(0, 5))
            if '周末' in text:
                return {5, 6}
            return None

        result = set()
        for token in tokens:
            weekday = normalize_day_token(token)
            if weekday is not None:
                result.add(weekday)
        return result or None

    def parse_segment_time_ranges(self, segment_text):
        text = str(segment_text or '').strip()
        if not text:
            return []

        ranges = []
        matches = re.findall(r"(\d{1,2}:\d{1,2})\s*(?:-|~|—|–|至|到)\s*(\d{1,2}:\d{1,2})", text)
        for start_text, end_text in matches:
            start_minute = self.parse_time_minutes(start_text)
            end_minute = self.parse_time_minutes(end_text)
            if start_minute is None or end_minute is None:
                continue
            ranges.append((start_minute, end_minute))

        return ranges

    def is_time_in_range(self, target_minute, start_minute, end_minute):
        if target_minute is None:
            return False
        if start_minute == end_minute:
            return True
        if end_minute > start_minute:
            return start_minute <= target_minute <= end_minute
        return target_minute >= start_minute or target_minute <= end_minute

    def evaluate_open_match(self, poi, visit_weekday=None, visit_time=None):
        opening_hours = self.extract_poi_opening_hours(poi)

        normalized_weekday = self.normalize_weekday(visit_weekday)
        normalized_time = self.normalize_visit_time(visit_time)
        target_minute = self.parse_time_minutes(normalized_time)

        if normalized_weekday is None and target_minute is None:
            return {
                'status': 'not_specified',
                'is_open': None,
                'score': 0.55,
                'opening_hours': opening_hours
            }

        if not opening_hours:
            return {
                'status': 'unknown',
                'is_open': None,
                'score': 0.45,
                'opening_hours': ''
            }

        cleaned = opening_hours.replace(' ', '')
        if any(keyword in cleaned for keyword in ['全天开放', '24小时营业', '24小时开放', '00:00-24:00', '00:00-00:00']):
            return {
                'status': 'open',
                'is_open': True,
                'score': 1.0,
                'opening_hours': opening_hours
            }

        segments = [seg.strip() for seg in re.split(r"[；;\n]+", opening_hours) if seg.strip()]
        if not segments:
            return {
                'status': 'unknown',
                'is_open': None,
                'score': 0.45,
                'opening_hours': opening_hours
            }

        applicable_seen = False
        for segment in segments:
            weekdays = self.parse_segment_weekdays(segment)
            if normalized_weekday is not None and weekdays is not None and normalized_weekday not in weekdays:
                continue

            applicable_seen = True
            closed_flag = any(flag in segment for flag in ['闭馆', '休息', '暂停营业', '不开放'])
            time_ranges = self.parse_segment_time_ranges(segment)

            if target_minute is None:
                if closed_flag:
                    continue
                return {
                    'status': 'open',
                    'is_open': True,
                    'score': 1.0,
                    'opening_hours': opening_hours
                }

            if not time_ranges:
                if not closed_flag:
                    return {
                        'status': 'open',
                        'is_open': True,
                        'score': 0.90,
                        'opening_hours': opening_hours
                    }
                continue

            in_any_range = any(
                self.is_time_in_range(target_minute, start_minute, end_minute)
                for start_minute, end_minute in time_ranges
            )
            if in_any_range and not closed_flag:
                return {
                    'status': 'open',
                    'is_open': True,
                    'score': 1.0,
                    'opening_hours': opening_hours
                }

        if applicable_seen:
            return {
                'status': 'closed',
                'is_open': False,
                'score': 0.05,
                'opening_hours': opening_hours
            }

        return {
            'status': 'closed',
            'is_open': False,
            'score': 0.10,
            'opening_hours': opening_hours
        }

    def time_distance_to_range(self, target_minute, start_minute, end_minute):
        if target_minute is None:
            return None
        if self.is_time_in_range(target_minute, start_minute, end_minute):
            return 0

        if end_minute > start_minute:
            return min(abs(target_minute - start_minute), abs(target_minute - end_minute))

        # 跨天营业时段，按 24 小时环形距离估算最近边界。
        distance_to_start = min((target_minute - start_minute) % 1440, (start_minute - target_minute) % 1440)
        distance_to_end = min((target_minute - end_minute) % 1440, (end_minute - target_minute) % 1440)
        return min(distance_to_start, distance_to_end)

    def build_opening_hint(self, poi, activity_time=None, visit_weekday=None):
        opening_hours = self.extract_poi_opening_hours(poi)
        if not opening_hours:
            return {
                'opening_hours': '',
                'opening_hint': '',
                'opening_status': 'unknown'
            }

        normalized_weekday = self.normalize_weekday(visit_weekday)
        normalized_time = self.normalize_visit_time(activity_time)
        target_minute = self.parse_time_minutes(normalized_time)
        open_match = self.evaluate_open_match(
            poi,
            visit_weekday=normalized_weekday,
            visit_time=normalized_time
        )

        cleaned = opening_hours.replace(' ', '')
        if any(keyword in cleaned for keyword in ['全天开放', '24小时营业', '24小时开放', '00:00-24:00', '00:00-00:00']):
            return {
                'opening_hours': opening_hours,
                'opening_hint': '全天开放（与当前行程时段匹配）',
                'opening_status': open_match.get('status', 'open')
            }

        segments = [seg.strip() for seg in re.split(r"[；;\n]+", opening_hours) if seg.strip()]
        if not segments:
            return {
                'opening_hours': opening_hours,
                'opening_hint': opening_hours,
                'opening_status': open_match.get('status', 'unknown')
            }

        applicable_segments = []
        for segment in segments:
            weekdays = self.parse_segment_weekdays(segment)
            if normalized_weekday is not None and weekdays is not None and normalized_weekday not in weekdays:
                continue
            applicable_segments.append(segment)

        candidates = applicable_segments or segments
        best_segment = ''
        best_distance = None

        if target_minute is not None:
            for segment in candidates:
                for start_minute, end_minute in self.parse_segment_time_ranges(segment):
                    distance = self.time_distance_to_range(target_minute, start_minute, end_minute)
                    if distance is None:
                        continue
                    if best_distance is None or distance < best_distance:
                        best_distance = distance
                        best_segment = segment

        if not best_segment and candidates:
            best_segment = candidates[0]

        if best_segment and best_distance == 0:
            best_segment = f"{best_segment}（与当前行程时段匹配）"
        elif best_segment and best_distance is not None and best_distance <= 180:
            best_segment = f"{best_segment}（与当前行程时段接近）"

        return {
            'opening_hours': opening_hours,
            'opening_hint': best_segment or opening_hours,
            'opening_status': open_match.get('status', 'unknown')
        }

    def get_recommend_weights(self, recommend_focus):
        focus = self.normalize_recommend_focus(recommend_focus)
        presets = {
            'rating': {
                'rating': 0.50,
                'distance': 0.12,
                'interest': 0.12,
                'budget': 0.10,
                'opening': 0.16
            },
            'distance': {
                'rating': 0.20,
                'distance': 0.38,
                'interest': 0.16,
                'budget': 0.10,
                'opening': 0.16
            }
        }
        return presets.get(focus, presets['rating'])

    def parse_budget_amount(self, budget_input, days):
        if days <= 0:
            days = 1

        legacy_daily_map = {
            'budget': 300,
            'moderate': 600,
            'luxury': 1200
        }

        if isinstance(budget_input, (int, float)):
            return max(100.0, float(budget_input))

        text = str(budget_input or '').strip().lower()
        if not text:
            return 600.0 * days

        if text in legacy_daily_map:
            return float(legacy_daily_map[text] * days)

        match = re.search(r"\d+(?:\.\d+)?", text)
        if match:
            return max(100.0, float(match.group()))

        return 600.0 * days

    def infer_budget_level_from_amount(self, total_budget, days):
        if days <= 0:
            days = 1
        daily_budget = total_budget / days
        if daily_budget <= 450:
            return 'budget'
        if daily_budget <= 900:
            return 'moderate'
        return 'luxury'

    def score_poi(self, poi, center_point, preference_terms, budget_target, recommend_focus, visit_weekday=None, visit_time=None):
        weights = self.get_recommend_weights(recommend_focus)

        rating = self.extract_poi_rating(poi)
        rating_score = (rating / 5.0) if rating is not None else 0.70

        poi_point = self.parse_lnglat((poi or {}).get('location'))
        distance_m = self.haversine_distance_m(center_point, poi_point)
        if distance_m is None:
            distance_score = 0.55
        else:
            distance_score = max(0.0, 1 - min(distance_m, 12000) / 12000)

        terms = [str(term).strip() for term in (preference_terms or []) if str(term).strip()]
        haystack = ' '.join([
            str((poi or {}).get('name') or ''),
            str((poi or {}).get('type') or ''),
            str((poi or {}).get('tag') or ''),
            str((poi or {}).get('address') or '')
        ]).lower()
        if not terms:
            interest_score = 0.55
        else:
            matched = sum(1 for term in terms if term.lower() in haystack)
            interest_score = matched / len(terms)

        cost = self.extract_poi_cost(poi)
        target = max(1.0, float(budget_target or 150))
        if cost is None:
            budget_score = 0.55
        elif cost <= target:
            cheap_ratio = (target - cost) / max(target, 1)
            budget_score = max(0.70, 1 - cheap_ratio * 0.30)
        else:
            over_ratio = (cost - target) / max(target, 1)
            budget_score = max(0.10, 1 - over_ratio)

        open_match = self.evaluate_open_match(
            poi,
            visit_weekday=visit_weekday,
            visit_time=visit_time
        )
        opening_score = open_match.get('score', 0.55)

        total_score = (
            weights['rating'] * rating_score +
            weights['distance'] * distance_score +
            weights['interest'] * interest_score +
            weights['budget'] * budget_score +
            weights['opening'] * opening_score
        )

        return {
            'total_score': total_score,
            'distance_m': int(distance_m) if distance_m is not None else None,
            'open_match': open_match
        }

    def rank_pois(self, pois, center_point, preference_terms, budget_target, recommend_focus, visit_weekday=None, visit_time=None):
        scored_items = []
        for poi in pois or []:
            score_info = self.score_poi(
                poi,
                center_point,
                preference_terms,
                budget_target,
                recommend_focus,
                visit_weekday=visit_weekday,
                visit_time=visit_time
            )
            scored_items.append((score_info['total_score'], poi))

        scored_items.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored_items]

    def attach_next_distances(self, activities):
        if not activities:
            return

        point_indices = []
        for idx, activity in enumerate(activities):
            point = activity.get('_point')
            if point:
                point_indices.append((idx, point))

        for pos, (idx, point) in enumerate(point_indices):
            if pos + 1 >= len(point_indices):
                activities[idx]['next_distance'] = None
                continue
            next_point = point_indices[pos + 1][1]
            distance = self.haversine_distance_m(point, next_point)
            activities[idx]['next_distance'] = int(round(distance)) if distance is not None else None

        for activity in activities:
            if '_point' in activity:
                activity.pop('_point', None)

    def match_preference_labels(self, poi, preferences):
        keyword_map = {
            '自然风光': ['景区', '公园', '山', '海', '湖', '湿地', '森林'],
            '历史古迹': ['博物馆', '古城', '古镇', '寺', '祠', '遗址'],
            '美食品尝': ['美食', '餐饮', '小吃', '餐厅', '火锅', '烧烤'],
            '现代都游': ['商场', '购物', '广场', '地标', '街区'],
            '户外徒步': ['徒步', '步道', '登山', '栈道', '露营'],
            '艺术文化': ['艺术', '美术馆', '文化', '剧院', '展览']
        }

        haystack = ' '.join([
            str((poi or {}).get('name') or ''),
            str((poi or {}).get('type') or ''),
            str((poi or {}).get('tag') or ''),
            str((poi or {}).get('address') or '')
        ]).lower()

        matched = []
        for label in preferences or []:
            terms = keyword_map.get(str(label), [str(label)])
            if any(str(term).lower() in haystack for term in terms if str(term).strip()):
                matched.append(str(label))

        return list(dict.fromkeys(matched))[:2]

    def format_distance_for_reason(self, distance_m):
        if distance_m is None:
            return ''
        if distance_m < 1000:
            return f"约 {int(round(distance_m))} 米"
        return f"约 {distance_m / 1000:.1f} 公里"

    def build_recommend_reason(self, poi, category, recommend_focus, preferences, center_point, budget_target):
        focus = self.normalize_recommend_focus(recommend_focus)
        reason_parts = []
        rating = self.extract_poi_rating(poi)
        cost = self.extract_poi_cost(poi)
        poi_point = self.parse_lnglat((poi or {}).get('location'))
        distance_m = self.haversine_distance_m(center_point, poi_point) if center_point and poi_point else None

        if focus == 'rating' and rating is not None:
            reason_parts.append(f"评分 {rating:.1f}，口碑较好")
        elif focus == 'distance' and distance_m is not None:
            reason_parts.append(f"距离中心{self.format_distance_for_reason(distance_m)}，出行更便捷")

        if rating is not None and all('评分' not in text for text in reason_parts):
            reason_parts.append(f"评分 {rating:.1f}")

        if cost is not None and all('人均' not in text for text in reason_parts):
            reason_parts.append(f"参考人均约￥{cost}")

        matched_preferences = self.match_preference_labels(poi, preferences)
        if matched_preferences:
            reason_parts.append(f"匹配偏好：{'、'.join(matched_preferences)}")

        if distance_m is not None and all('距离中心' not in text for text in reason_parts):
            reason_parts.append(f"距目的地中心{self.format_distance_for_reason(distance_m)}")

        if not reason_parts:
            fallback_map = {
                '景点': '景点热度与行程节奏匹配',
                '餐饮': '用餐时段与补给需求匹配',
                '住宿': '住宿位置与当日行程衔接较好'
            }
            reason_parts.append(fallback_map.get(category, '综合评分后推荐'))

        return '；'.join(reason_parts[:3])

    def build_itinerary_from_pois(
        self,
        destination,
        days,
        pois,
        food_pois,
        hotel_pois,
        budget_level,
        recommend_focus,
        preferences,
        center_point,
        scenic_budget_target,
        food_budget_target,
        hotel_budget_target,
        scenic_city_factor=1.0,
        total_budget=None,
        pace='intense',
        visit_weekday=None
    ):
        budget_profiles = {
            'budget': {
                'daily': (200, 400),
                'poi': (0, 55),
                'meal': (20, 50),
                'hotel': (120, 220)
            },
            'moderate': {
                'daily': (400, 800),
                'poi': (35, 95),
                'meal': (40, 100),
                'hotel': (220, 380)
            },
            'luxury': {
                'daily': (800, 1500),
                'poi': (80, 180),
                'meal': (80, 200),
                'hotel': (380, 680)
            }
        }

        profile = budget_profiles.get(budget_level, budget_profiles['moderate'])
        time_slots = self.get_time_slots_for_pace(pace)
        plans = []
        daily_budget_targets = self.build_daily_budget_targets(total_budget, days)
        daily_range = profile.get('daily') or (400, 800)
        fallback_daily_target = (daily_range[0] + daily_range[1]) / 2

        scenic_cursor = 0
        food_cursor = 0
        hotel_cursor = 0
        used_place_keys = set()

        for day in range(1, days + 1):
            day_budget_target = daily_budget_targets[day - 1] if day - 1 < len(daily_budget_targets) else fallback_daily_target
            scenic_floor = max(12.0, 20.0 * scenic_city_factor)
            scenic_core = min(day_budget_target * 0.16 * scenic_city_factor, scenic_budget_target * 1.6)
            day_scenic_target = max(scenic_floor, scenic_core)
            day_food_target = max(20.0, min(day_budget_target * 0.12, food_budget_target * 2.0))
            day_hotel_target = max(100.0, min(day_budget_target * 0.40, hotel_budget_target * 2.2))
            activities = []

            for idx, slot in enumerate(time_slots):
                if slot['type'] == 'poi':
                    poi, scenic_cursor = self.consume_next_unique_poi(pois, scenic_cursor, used_place_keys)
                    name = (poi or {}).get('name') or f"自由探索{destination}·第{day}天{slot['label']}"
                    address = (poi or {}).get('address') or (poi or {}).get('location') or '位置待确认'
                    point = self.parse_lnglat((poi or {}).get('location'))
                    rating = self.extract_poi_rating(poi)
                    cost, cost_source = self.calibrate_activity_cost(
                        poi=poi,
                        category='poi',
                        raw_cost=self.extract_poi_cost(poi),
                        profile=profile,
                        seed=day * 100 + idx * 7 + 11,
                        budget_target=day_scenic_target
                    )
                    recommend_reason = self.build_recommend_reason(
                        poi,
                        '景点',
                        recommend_focus,
                        preferences,
                        center_point,
                        day_scenic_target
                    )
                    opening_info = self.build_opening_hint(
                        poi,
                        activity_time=slot['time'],
                        visit_weekday=visit_weekday
                    )
                    activities.append({
                        'time': slot['time'],
                        'content': name,
                        'tips': f"地址：{address}｜人均￥{cost}（{cost_source}）｜建议预留 1-2 小时",
                        'category': '景点',
                        'cost': cost,
                        'rating': rating,
                        'location': (poi or {}).get('location', ''),
                        'poi_type': (poi or {}).get('type', ''),
                        'recommend_reason': recommend_reason,
                        'opening_hours': opening_info.get('opening_hours', ''),
                        'opening_hint': opening_info.get('opening_hint', ''),
                        'opening_status': opening_info.get('opening_status', 'unknown'),
                        '_point': point
                    })
                elif slot['type'] == 'meal':
                    food, food_cursor = self.consume_next_unique_poi(food_pois, food_cursor, used_place_keys)
                    name = (food or {}).get('name') or f"第{day}天{slot['label']}"
                    address = (food or {}).get('address') or (food or {}).get('location') or '位置待确认'
                    point = self.parse_lnglat((food or {}).get('location'))
                    rating = self.extract_poi_rating(food)
                    cost, cost_source = self.calibrate_activity_cost(
                        poi=food,
                        category='meal',
                        raw_cost=self.extract_poi_cost(food),
                        profile=profile,
                        seed=day * 100 + idx * 7 + 23,
                        budget_target=day_food_target
                    )
                    recommend_reason = self.build_recommend_reason(
                        food,
                        '餐饮',
                        recommend_focus,
                        preferences,
                        center_point,
                        day_food_target
                    )
                    opening_info = self.build_opening_hint(
                        food,
                        activity_time=slot['time'],
                        visit_weekday=visit_weekday
                    )
                    activities.append({
                        'time': slot['time'],
                        'content': name,
                        'tips': f"地址：{address}｜人均￥{cost}（{cost_source}）",
                        'category': '餐饮',
                        'cost': cost,
                        'rating': rating,
                        'location': (food or {}).get('location', ''),
                        'poi_type': (food or {}).get('type', ''),
                        'recommend_reason': recommend_reason,
                        'opening_hours': opening_info.get('opening_hours', ''),
                        'opening_hint': opening_info.get('opening_hint', ''),
                        'opening_status': opening_info.get('opening_status', 'unknown'),
                        '_point': point
                    })
                elif slot['type'] == 'hotel':
                    hotel, hotel_cursor = self.consume_next_unique_poi(hotel_pois, hotel_cursor, used_place_keys)
                    name = (hotel or {}).get('name') or f"{destination}精选酒店·第{day}天"
                    address = (hotel or {}).get('address') or (hotel or {}).get('location') or '位置待确认'
                    point = self.parse_lnglat((hotel or {}).get('location'))
                    rating = self.extract_poi_rating(hotel)
                    cost, cost_source = self.calibrate_activity_cost(
                        poi=hotel,
                        category='hotel',
                        raw_cost=self.extract_poi_cost(hotel),
                        profile=profile,
                        seed=day * 100 + idx * 7 + 35,
                        budget_target=day_hotel_target
                    )
                    recommend_reason = self.build_recommend_reason(
                        hotel,
                        '住宿',
                        recommend_focus,
                        preferences,
                        center_point,
                        day_hotel_target
                    )
                    opening_info = self.build_opening_hint(
                        hotel,
                        activity_time=slot['time'],
                        visit_weekday=visit_weekday
                    )
                    activities.append({
                        'time': slot['time'],
                        'content': name,
                        'tips': f"地址：{address}｜每晚/每人￥{cost}（{cost_source}）",
                        'category': '住宿',
                        'cost': cost,
                        'rating': rating,
                        'location': (hotel or {}).get('location', ''),
                        'poi_type': (hotel or {}).get('type', ''),
                        'recommend_reason': recommend_reason,
                        'opening_hours': opening_info.get('opening_hours', ''),
                        'opening_hint': opening_info.get('opening_hint', ''),
                        'opening_status': opening_info.get('opening_status', 'unknown'),
                        '_point': point
                    })

            self.attach_next_distances(activities)

            plans.append({
                'day': day,
                'activities': activities
            })

        return plans

    def calc_estimated_cost(self, plans):
        total = 0.0
        for day_plan in plans or []:
            activities = day_plan.get('activities', []) if isinstance(day_plan, dict) else []
            for activity in activities:
                try:
                    total += float(activity.get('cost') or 0)
                except (TypeError, ValueError, AttributeError):
                    continue
        return round(total, 2)

    def build_preference_terms(self, preferences):
        terms = []
        for pref in preferences:
            if pref in self.PREFERENCE_KEYWORDS:
                terms.extend(self.PREFERENCE_KEYWORDS[pref].split())
        return terms

    def generate_itinerary(
        self,
        destination,
        days,
        preferences,
        budget_input,
        recommend_focus,
        pace=None,
        visit_weekday=None,
        visit_date=None,
        visit_time=None,
        visit_time_slot=None
    ):
        destination = str(destination or '').strip()
        if not destination:
            raise POIAPIError('缺少 destination 参数', 400)

        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 0
        if days <= 0:
            raise POIAPIError('days 参数不合法', 400)

        prefs = preferences if isinstance(preferences, list) else []
        focus = self.normalize_recommend_focus(recommend_focus)
        normalized_pace = self.normalize_pace(pace)
        normalized_weekday = self.normalize_weekday(visit_weekday)
        if normalized_weekday is None and str(visit_date or '').strip():
            normalized_weekday = self.normalize_weekday(visit_date)

        normalized_visit_time = self.normalize_visit_time(visit_time)
        if normalized_visit_time is None:
            normalized_visit_time = self.normalize_visit_time(visit_time_slot)

        time_slots = self.get_time_slots_for_pace(normalized_pace)
        per_day_poi_slots = sum(1 for slot in time_slots if slot['type'] == 'poi')
        per_day_food_slots = sum(1 for slot in time_slots if slot['type'] == 'meal')
        baseline_poi = max(3, per_day_poi_slots * 3)
        baseline_food = max(3, per_day_food_slots * 3)

        budget_amount = self.parse_budget_amount(budget_input, days)
        budget_level = self.infer_budget_level_from_amount(budget_amount, days)
        scenic_city_factor = self.get_city_scenic_cost_factor(destination)

        scenic_needed = max(days * per_day_poi_slots * 4, baseline_poi * 3, 24)
        food_needed = max(days * per_day_food_slots * 4, baseline_food * 3, 30)
        hotel_needed = max(days * 3, 12)

        center_location = self.geocode_city_center(destination) or ''
        center_point = self.parse_lnglat(center_location)

        scenic_queries = self.build_category_query_plan('景点', destination, prefs)
        food_queries = self.build_category_query_plan('餐饮', destination, prefs)
        hotel_queries = self.build_category_query_plan('住宿', destination, prefs)

        pois = self.collect_pois_by_queries(destination, scenic_queries, scenic_needed, center_location=center_location)
        food_pois = self.collect_pois_by_queries(destination, food_queries, food_needed, center_location=center_location)
        hotel_pois = self.collect_pois_by_queries(destination, hotel_queries, hotel_needed, center_location=center_location)

        if not pois:
            raise POIAPIError('高德景点搜索失败', 502, {'queries': scenic_queries})
        if not food_pois:
            raise POIAPIError('高德餐饮搜索失败', 502, {'queries': food_queries})
        if not hotel_pois:
            raise POIAPIError('高德酒店搜索失败', 502, {'queries': hotel_queries})

        daily_budget = budget_amount / max(days, 1)
        scenic_floor = max(12.0, 20.0 * scenic_city_factor)
        scenic_budget_target = max(scenic_floor, daily_budget * 0.13 * scenic_city_factor)
        food_budget_target = max(20.0, daily_budget * 0.10)
        hotel_budget_target = max(100.0, daily_budget * 0.34)

        preference_terms = self.build_preference_terms(prefs)

        pois = self.rank_pois(
            pois,
            center_point,
            preference_terms,
            scenic_budget_target,
            focus,
            visit_weekday=normalized_weekday,
            visit_time=normalized_visit_time
        )
        food_pois = self.rank_pois(
            food_pois,
            center_point,
            ['美食', '餐厅', '小吃'],
            food_budget_target,
            focus,
            visit_weekday=normalized_weekday,
            visit_time=normalized_visit_time
        )
        hotel_pois = self.rank_pois(
            hotel_pois,
            center_point,
            ['酒店', '住宿'],
            hotel_budget_target,
            focus,
            visit_weekday=normalized_weekday,
            visit_time=normalized_visit_time
        )

        pois = self.deduplicate_poi_pool(pois)
        food_pois = self.deduplicate_poi_pool(food_pois)
        hotel_pois = self.deduplicate_poi_pool(hotel_pois)

        plans = self.build_itinerary_from_pois(
            destination,
            days,
            pois,
            food_pois,
            hotel_pois,
            budget_level,
            focus,
            prefs,
            center_point,
            scenic_budget_target,
            food_budget_target,
            hotel_budget_target,
            scenic_city_factor=scenic_city_factor,
            total_budget=budget_amount,
            pace=normalized_pace,
            visit_weekday=normalized_weekday
        )
        estimated_cost = self.calc_estimated_cost(plans)

        return {
            'destination': destination,
            'days': days,
            'plans': plans,
            'recommend_focus': focus,
            'budget': round(budget_amount, 2),
            'estimated_cost': estimated_cost,
            'pace': normalized_pace,
            'visit_weekday': normalized_weekday,
            'visit_time': normalized_visit_time
        }

    def recommend_pois(
        self,
        destination,
        category,
        preferences,
        budget_input,
        days,
        recommend_focus,
        limit,
        keyword='',
        visit_weekday=None,
        visit_date=None,
        visit_time=None,
        visit_time_slot=None,
        cost_resolver=None,
        item_callback=None
    ):
        destination = str(destination or '').strip()
        if not destination:
            raise POIAPIError('缺少 destination 参数', 400)

        cat = str(category or '景点').strip() or '景点'
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 1
        days = max(1, days)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = min(max(1, limit), 25)

        prefs = preferences if isinstance(preferences, list) else []
        focus = self.normalize_recommend_focus(recommend_focus)
        budget_amount = self.parse_budget_amount(budget_input, days)
        daily_budget = budget_amount / max(days, 1)
        scenic_city_factor = self.get_city_scenic_cost_factor(destination)

        normalized_weekday = self.normalize_weekday(visit_weekday)
        if normalized_weekday is None and str(visit_date or '').strip():
            normalized_weekday = self.normalize_weekday(visit_date)

        normalized_visit_time = self.normalize_visit_time(visit_time)
        if normalized_visit_time is None:
            normalized_visit_time = self.normalize_visit_time(visit_time_slot)

        query_plan = self.build_category_query_plan(cat, destination, prefs, keyword=keyword)
        primary_query = query_plan[0]

        center_location = self.geocode_city_center(destination) or ''
        center_point = self.parse_lnglat(center_location)

        budget_ratio_map = {
            '景点': 0.13 * scenic_city_factor,
            '餐饮': 0.10,
            '住宿': 0.34
        }
        scenic_floor = max(12.0, 20.0 * scenic_city_factor)
        budget_floor = scenic_floor if cat == '景点' else 20.0
        budget_target = max(budget_floor, daily_budget * budget_ratio_map.get(cat, 0.18))

        if cat == '景点':
            preference_terms = self.build_preference_terms(prefs)
        elif cat == '餐饮':
            preference_terms = ['美食', '餐厅', '小吃']
        else:
            preference_terms = ['酒店', '住宿']

        fetch_target = max(limit * 3, 30)
        raw_pois = self.collect_pois_by_queries(destination, query_plan, fetch_target, center_location=center_location)
        if not raw_pois:
            raise POIAPIError('高德POI推荐失败', 502, {'queries': query_plan})

        ranked = self.rank_pois(
            raw_pois,
            center_point,
            preference_terms,
            budget_target,
            focus,
            visit_weekday=normalized_weekday,
            visit_time=normalized_visit_time
        )
        ranked = self.deduplicate_poi_pool(ranked)
        picked = self.diversify_ranked_pois(ranked, limit)

        items = []
        for poi in picked:
            score_info = self.score_poi(
                poi,
                center_point,
                preference_terms,
                budget_target,
                focus,
                visit_weekday=normalized_weekday,
                visit_time=normalized_visit_time
            )
            poi_category = self.map_amap_type_to_category(poi.get('type', ''))
            raw_cost = self.extract_poi_cost(poi)
            estimated_cost = raw_cost
            cost_source = 'amap_raw' if raw_cost is not None else 'budget_target'

            if callable(cost_resolver):
                resolved_cost, resolved_source = cost_resolver(poi, poi_category, budget_target)
                if resolved_cost is not None:
                    estimated_cost = int(round(float(resolved_cost)))
                if resolved_source:
                    cost_source = str(resolved_source)

            if estimated_cost is None:
                estimated_cost = int(round(max(20.0, budget_target)))

            item = {
                'amap_id': str(poi.get('id', '')).strip(),
                'name': poi.get('name', ''),
                'address': poi.get('address', ''),
                'location': poi.get('location', ''),
                'type': poi.get('type', ''),
                'category': poi_category,
                'rating': self.extract_poi_rating(poi),
                'cost': raw_cost,
                'estimated_cost': int(estimated_cost),
                'cost_source': cost_source,
                'score': round(score_info['total_score'], 4),
                'opening_hours': score_info.get('open_match', {}).get('opening_hours', ''),
                'open_match': score_info.get('open_match', {}),
                'recommend_reason': self.build_recommend_reason(
                    poi,
                    poi_category,
                    focus,
                    prefs,
                    center_point,
                    budget_target
                )
            }
            if callable(item_callback):
                item_callback(
                    poi,
                    item,
                    {
                        'destination': destination,
                        'category': cat,
                        'query': primary_query,
                        'budget_target': budget_target
                    }
                )
            items.append(item)

        return {
            'destination': destination,
            'category': cat,
            'recommend_focus': focus,
            'query': primary_query,
            'query_candidates': query_plan,
            'visit_weekday': normalized_weekday,
            'visit_time': normalized_visit_time,
            'budget_target': round(budget_target, 2),
            'items': items
        }
