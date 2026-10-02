"""
Temporal Service
----------------
提供極致容錯的時區解析、全週期行程生命週期判定、當前活動進度標記與世界時間查詢。
徹底消除雲端容器 UTC 時區漂移，確保 AI 即時時間與行程進度感知 100% 精準。
"""

import re
import zoneinfo
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

# 模組時序語意常數 (防禦魔術數字)
MINUTES_IN_A_DAY: int = 1440
DEFAULT_EVENT_DURATION_MIN: int = 60
EARLY_MORNING_HOUR_CUTOFF: int = 6
LATE_NIGHT_HOUR_THRESHOLD: int = 20
EVENING_HOUR_THRESHOLD: int = 18
DESTINATION_SAMPLE_LIMIT: int = 15

# 確定性國家/城市/景點至 IANA 時區映射表
DESTINATION_TIMEZONE_MAP = {
    # 日本 (UTC+9)
    "日本": "Asia/Tokyo", "japan": "Asia/Tokyo", "jp": "Asia/Tokyo",
    "東京": "Asia/Tokyo", "tokyo": "Asia/Tokyo",
    "大阪": "Asia/Tokyo", "osaka": "Asia/Tokyo",
    "京都": "Asia/Tokyo", "kyoto": "Asia/Tokyo",
    "沖繩": "Asia/Tokyo", "okinawa": "Asia/Tokyo",
    "北海道": "Asia/Tokyo", "hokkaido": "Asia/Tokyo",
    "福岡": "Asia/Tokyo", "fukuoka": "Asia/Tokyo",
    "名古屋": "Asia/Tokyo", "nagoya": "Asia/Tokyo",
    "札幌": "Asia/Tokyo", "sapporo": "Asia/Tokyo",

    # 韓國 (UTC+9)
    "韓國": "Asia/Seoul", "korea": "Asia/Seoul", "kr": "Asia/Seoul",
    "首爾": "Asia/Seoul", "seoul": "Asia/Seoul",
    "釜山": "Asia/Seoul", "busan": "Asia/Seoul",
    "濟州": "Asia/Seoul", "jeju": "Asia/Seoul",

    # 台灣 (UTC+8)
    "台灣": "Asia/Taipei", "taiwan": "Asia/Taipei", "tw": "Asia/Taipei",
    "台北": "Asia/Taipei", "taipei": "Asia/Taipei",
    "高雄": "Asia/Taipei", "kaohsiung": "Asia/Taipei",
    "台中": "Asia/Taipei", "taichung": "Asia/Taipei",
    "台南": "Asia/Taipei", "tainan": "Asia/Taipei",

    # 港澳 (UTC+8)
    "香港": "Asia/Hong_Kong", "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong",
    "澳門": "Asia/Macau", "macau": "Asia/Macau",

    # 東南亞
    "泰國": "Asia/Bangkok", "thailand": "Asia/Bangkok", "th": "Asia/Bangkok",
    "曼谷": "Asia/Bangkok", "bangkok": "Asia/Bangkok",
    "清邁": "Asia/Bangkok", "chiang mai": "Asia/Bangkok",
    "新加坡": "Asia/Singapore", "singapore": "Asia/Singapore", "sg": "Asia/Singapore",
    "越南": "Asia/Ho_Chi_Minh", "vietnam": "Asia/Ho_Chi_Minh", "vn": "Asia/Ho_Chi_Minh",
    "河內": "Asia/Ho_Chi_Minh", "hanoi": "Asia/Ho_Chi_Minh",
    "胡志明": "Asia/Ho_Chi_Minh", "ho chi minh": "Asia/Ho_Chi_Minh",
    "馬來西亞": "Asia/Kuala_Lumpur", "malaysia": "Asia/Kuala_Lumpur", "吉隆坡": "Asia/Kuala_Lumpur",
    "印尼": "Asia/Jakarta", "巴里島": "Asia/Makassar", "峇里島": "Asia/Makassar", "bali": "Asia/Makassar",

    # 歐洲
    "英國": "Europe/London", "uk": "Europe/London", "倫敦": "Europe/London", "london": "Europe/London",
    "法國": "Europe/Paris", "france": "Europe/Paris", "巴黎": "Europe/Paris", "paris": "Europe/Paris",
    "德國": "Europe/Berlin", "germany": "Europe/Berlin", "柏林": "Europe/Berlin", "慕尼黑": "Europe/Berlin",
    "義大利": "Europe/Rome", "italy": "Europe/Rome", "羅馬": "Europe/Rome", "米蘭": "Europe/Rome",
    "西班牙": "Europe/Madrid", "spain": "Europe/Madrid", "馬德里": "Europe/Madrid", "巴塞隆納": "Europe/Madrid",
    "荷蘭": "Europe/Amsterdam", "阿姆斯特丹": "Europe/Amsterdam",
    "瑞士": "Europe/Zurich", "蘇黎世": "Europe/Zurich",

    # 美洲
    "美國": "America/New_York", "usa": "America/New_York",
    "紐約": "America/New_York", "new york": "America/New_York",
    "洛杉磯": "America/Los_Angeles", "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "舊金山": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "西雅圖": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "夏威夷": "Pacific/Honolulu", "hawaii": "Pacific/Honolulu",

    # 日本著名地標
    "富士山": "Asia/Tokyo", "晴空塔": "Asia/Tokyo", "淺草寺": "Asia/Tokyo",
    "清水寺": "Asia/Tokyo", "金閣寺": "Asia/Tokyo", "環球影城": "Asia/Tokyo", "迪士尼": "Asia/Tokyo",

    # 歐洲著名地標
    "大英博物館": "Europe/London", "倫敦眼": "Europe/London",
    "羅浮宮": "Europe/Paris", "艾菲爾鐵塔": "Europe/Paris", "凡爾賽宮": "Europe/Paris", "巴黎聖母院": "Europe/Paris",
    "聖家堂": "Europe/Madrid", "奎爾公園": "Europe/Madrid",
    "羅馬競技場": "Europe/Rome", "鬥獸場": "Europe/Rome", "比薩斜塔": "Europe/Rome",

    # 澳洲 / 大洋洲
    "澳洲": "Australia/Sydney", "australia": "Australia/Sydney",
    "雪梨": "Australia/Sydney", "sydney": "Australia/Sydney",
    "墨爾本": "Australia/Melbourne", "melbourne": "Australia/Melbourne",
    "布里斯本": "Australia/Brisbane", "brisbane": "Australia/Brisbane",
    "伯斯": "Australia/Perth", "perth": "Australia/Perth",
    "紐西蘭": "Pacific/Auckland", "new zealand": "Pacific/Auckland", "奧克蘭": "Pacific/Auckland", "auckland": "Pacific/Auckland",

    # 美洲著名地標
    "自由女神": "America/New_York", "時代廣場": "America/New_York", "中央公園": "America/New_York",
    "金門大橋": "America/Los_Angeles", "好萊塢": "America/Los_Angeles",
}

# 依關鍵字長度由長至短預先排序，確保具體地名 (如 "New York") 優先於短縮寫 (如 "LA", "TH")
SORTED_TIMEZONE_MAP = sorted(
    DESTINATION_TIMEZONE_MAP.items(),
    key=lambda x: len(x[0]),
    reverse=True
)


def _match_temporal_keyword(kw: str, text: str) -> bool:
    """
    智慧雙態關鍵字比對：
    - 拉丁字母 (英文地名/縮寫)：強制採用單詞邊界 \b 防止子字串劫持 (如 'south' 誤判為 'th', 'villa' 誤判為 'la')
    - CJK 字符 (中日韓文字)：維持靈活子字串比對
    """
    kw_clean = kw.strip().lower()
    if not kw_clean:
        return False
    is_latin = all(ord(c) < 128 for c in kw_clean)
    if is_latin:
        return bool(re.search(r'\b' + re.escape(kw_clean) + r'\b', text, re.IGNORECASE))
    return kw_clean in text.lower()


# 兜底時區偏移表 (當系統無 IANA tzdata 資料庫時之極致防禦)
FALLBACK_OFFSETS = {
    "UTC": 0, "GMT": 0,
    "Asia/Taipei": 8, "Asia/Tokyo": 9, "Asia/Seoul": 9,
    "Asia/Hong_Kong": 8, "Asia/Macau": 8, "Asia/Singapore": 8,
    "Asia/Bangkok": 7, "Asia/Ho_Chi_Minh": 7, "Asia/Jakarta": 7,
    "Asia/Kuala_Lumpur": 8, "Asia/Makassar": 8,
    "Europe/London": 0, "Europe/Paris": 1, "Europe/Berlin": 1,
    "Europe/Rome": 1, "Europe/Madrid": 1, "Europe/Amsterdam": 1,
    "America/New_York": -5, "America/Los_Angeles": -8,
    "Australia/Sydney": 10, "Australia/Melbourne": 10,
    "Pacific/Honolulu": -10, "Pacific/Auckland": 12,
}


def safe_get_zoneinfo(tz_name: Optional[str], fallback: str = "Asia/Taipei"):
    """
    零崩潰時區安全獲取 (雙層保險)
    若傳入空值、非法字串或未知 IANA 時區，先降級至 fallback；
    若系統完全缺少 tzdata，自動以固定偏移量 timezone(timedelta(...)) 兜底，絕不拋出異常。
    """
    from datetime import timezone, timedelta
    cleaned = (tz_name or "").strip() if isinstance(tz_name, str) else ""
    target = cleaned or fallback

    # 1. 嘗試原生 ZoneInfo
    try:
        return zoneinfo.ZoneInfo(target)
    except Exception:
        pass

    # 2. 嘗試 fallback 的 ZoneInfo
    try:
        return zoneinfo.ZoneInfo(fallback)
    except Exception:
        pass

    # 3. 極致兜底：以固定時區偏移量生成 timezone 物件
    offset = FALLBACK_OFFSETS.get(target, FALLBACK_OFFSETS.get(fallback, 8))
    return timezone(timedelta(hours=offset), name=target or fallback)


def infer_destination_timezone(itinerary: Optional[Dict[str, Any]], client_tz_str: str = "Asia/Taipei") -> str:
    """
    推斷目的地時區。
    綜合檢查行程標題、destination、dest_country、dest_city 與地點關鍵字，
    查無對應時安全回退至使用者手機時區。
    """
    if not itinerary or not isinstance(itinerary, dict):
        return client_tz_str or "Asia/Taipei"

    search_parts = [
        str(itinerary.get("title") or ""),
        str(itinerary.get("destination") or ""),
        str(itinerary.get("dest_country") or ""),
        str(itinerary.get("dest_city") or ""),
    ]
    # 全行程地點聚合抽樣 (去重後採樣前 DESTINATION_SAMPLE_LIMIT 處，杜絕長行程初期空白時區漏判)
    days = itinerary.get("days") or []
    all_places = [
        str(it.get("place") or "").strip()
        for day in days
        for it in (day.get("items") or [])
        if it.get("place")
    ]
    unique_places = list(dict.fromkeys(all_places))[:DESTINATION_SAMPLE_LIMIT]
    search_parts.extend(unique_places)

    combined_text = " ".join(search_parts)
    for keyword, tz in SORTED_TIMEZONE_MAP:
        if _match_temporal_keyword(keyword, combined_text):
            return tz

    return client_tz_str or "Asia/Taipei"


def parse_time_slot(time_str: Optional[str]) -> Tuple[Optional[time], Optional[time]]:
    """
    解析活動時間。
    支援 'HH:MM'、'HH:MM~HH:MM'、'HH:MM-HH:MM'，容錯中文及額外文字描述。
    回傳 (start_time, end_time)。
    """
    if not time_str or not isinstance(time_str, str):
        return None, None

    matches = re.findall(r'(\d{1,2}):(\d{2})', time_str)
    if not matches:
        return None, None

    try:
        h1, m1 = int(matches[0][0]), int(matches[0][1])
        if not (0 <= h1 <= 23 and 0 <= m1 <= 59):
            return None, None
        t_start = time(h1, m1)

        t_end = None
        if len(matches) > 1:
            h2, m2 = int(matches[1][0]), int(matches[1][1])
            if 0 <= h2 <= 23 and 0 <= m2 <= 59:
                t_end = time(h2, m2)

        return t_start, t_end
    except (ValueError, IndexError):
        return None, None


def calculate_temporal_itinerary_context(
    itinerary: Optional[Dict[str, Any]],
    client_time_iso: Optional[str] = None,
    client_tz_str: Optional[str] = "Asia/Taipei",
    focused_day: Optional[int] = 1
) -> Dict[str, Any]:
    """
    確定性時間與行程進度運算引擎。
    核心原則：
    1. 以使用者手機時間與時區為起始事實。
    2. 以目的地當地時間為判定「旅行第幾天」與「活動是否結束」的絕對錨點。
    3. 計算時差與生命週期狀態（BEFORE_TRIP, IN_TRIP, AFTER_TRIP, GENERAL）。
    """
    # 1. 取得時區與基準時間
    client_tz = safe_get_zoneinfo(client_tz_str, fallback="Asia/Taipei")
    dest_tz_name = infer_destination_timezone(itinerary, str(client_tz))
    dest_tz = safe_get_zoneinfo(dest_tz_name, fallback=str(client_tz))

    if client_time_iso:
        try:
            client_dt = datetime.fromisoformat(client_time_iso).astimezone(client_tz)
        except Exception:
            client_dt = datetime.now(client_tz)
    else:
        client_dt = datetime.now(client_tz)

    # 目的地當地時間 (物理絕對對齊)
    dest_dt = client_dt.astimezone(dest_tz)

    # 時差計算 (小數或整數小時)
    client_offset = client_dt.utcoffset().total_seconds() if client_dt.utcoffset() else 0.0
    dest_offset = dest_dt.utcoffset().total_seconds() if dest_dt.utcoffset() else 0.0
    diff_hours = (dest_offset - client_offset) / 3600.0

    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

    context_data: Dict[str, Any] = {
        "client_time_str": client_dt.strftime("%Y-%m-%d %H:%M"),
        "client_weekday": weekday_names[client_dt.weekday()],
        "client_tz": str(client_tz),
        "dest_time_str": dest_dt.strftime("%Y-%m-%d %H:%M"),
        "dest_weekday": weekday_names[dest_dt.weekday()],
        "dest_tz": str(dest_tz),
        "time_diff_hours": diff_hours,
        "is_different_tz": str(client_tz) != str(dest_tz),
        "lifecycle_stage": "GENERAL",
        "lifecycle_desc": "無特定行程綁定",
        "current_day_number": None,
        "is_today_completed": False,
        "items_progress": [],
        "active_day": focused_day or 1
    }

    if not itinerary or not isinstance(itinerary, dict):
        return context_data

    # 2. 判定行程生命週期 (以目的地當地日期為絕對錨點)
    start_date_str = str(itinerary.get("start_date") or "").strip()
    end_date_str = str(itinerary.get("end_date") or "").strip()
    days_list = itinerary.get("days") or []
    total_days = itinerary.get("total_days") or len(days_list) or 1

    dest_d = dest_dt.date()

    if start_date_str and re.match(r'^\d{4}-\d{2}-\d{2}$', start_date_str):
        try:
            start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if end_date_str and re.match(r'^\d{4}-\d{2}-\d{2}$', end_date_str):
                end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            else:
                end_d = start_d + timedelta(days=total_days - 1)

            if dest_d < start_d:
                days_left = (start_d - dest_d).days
                context_data["lifecycle_stage"] = "BEFORE_TRIP"
                context_data["lifecycle_desc"] = f"🛫 行程尚未啟程 (距離出發還有 {days_left} 天，當前為行前規劃狀態)"
            elif dest_d > end_d:
                days_ago = (dest_d - end_d).days
                context_data["lifecycle_stage"] = "AFTER_TRIP"
                context_data["lifecycle_desc"] = f"🏁 行程已圓滿結束 (已結束 {days_ago} 天，當前為行程回顧狀態)"
            else:
                curr_day = (dest_d - start_d).days + 1
                context_data["lifecycle_stage"] = "IN_TRIP"
                context_data["lifecycle_desc"] = f"🚀 旅行進行中 (今天是旅程第 {curr_day} 天 / 共 {total_days} 天)"
                context_data["current_day_number"] = curr_day
                context_data["active_day"] = curr_day
        except Exception:
            context_data["lifecycle_desc"] = "行程日期特殊，保持彈性檢視"

    # 3. 焦點天活動進度標記
    eval_day_num = context_data["current_day_number"] or focused_day or 1
    target_day_data = next((d for d in days_list if d.get("day_number") == eval_day_num), None)

    if target_day_data and isinstance(target_day_data, dict):
        curr_t = dest_dt.time()
        items = target_day_data.get("items") or []
        has_timed_items = False
        all_timed_passed = True

        curr_m = curr_t.hour * 60 + curr_t.minute
        has_late_night_items = any(
            parse_time_slot(it.get("time"))[0] and parse_time_slot(it.get("time"))[0].hour >= LATE_NIGHT_HOUR_THRESHOLD
            for it in items
        )
        if curr_t.hour < EARLY_MORNING_HOUR_CUTOFF and has_late_night_items:
            curr_m += MINUTES_IN_A_DAY

        seen_night = False

        for item in items:
            place = item.get("place", "?")
            raw_time = item.get("time") or ""
            t_start, t_end = parse_time_slot(raw_time)

            if not t_start:
                tag = "[時間彈性]"
            else:
                has_timed_items = True
                start_m = t_start.hour * 60 + t_start.minute

                if (seen_night or (t_end and t_end < t_start)) and t_start.hour < EARLY_MORNING_HOUR_CUTOFF:
                    start_m += MINUTES_IN_A_DAY
                elif t_start.hour >= EVENING_HOUR_THRESHOLD:
                    seen_night = True

                if t_end:
                    end_m = t_end.hour * 60 + t_end.minute
                    if end_m < (t_start.hour * 60 + t_start.minute):
                        end_m += MINUTES_IN_A_DAY
                else:
                    end_m = start_m + DEFAULT_EVENT_DURATION_MIN

                if curr_m > end_m:
                    tag = "[已過]"
                elif curr_m >= start_m:
                    tag = "[📍 進行中]"
                    all_timed_passed = False
                else:
                    tag = "[待進行]"
                    all_timed_passed = False

            context_data["items_progress"].append({
                "place": place,
                "time": raw_time,
                "tag": tag,
                "category": item.get("category", "")
            })

        if has_timed_items and all_timed_passed:
            context_data["is_today_completed"] = True

    return context_data


def format_temporal_header(temporal_info: Dict[str, Any]) -> str:
    """
    格式化注入 Prompt 頂部之即時時間與進度說明區塊
    """
    client_str = f"{temporal_info['client_time_str']} ({temporal_info['client_weekday']}, {temporal_info['client_tz']})"
    dest_str = f"{temporal_info['dest_time_str']} ({temporal_info['dest_weekday']}, {temporal_info['dest_tz']})"

    lines = [
        "--- SYSTEM CONTEXT: TEMPORAL & ITINERARY NEURAL AWARENESS ---",
        "【即時時間基準】",
        f"- 使用者手機時間: {client_str}",
    ]

    if temporal_info.get("is_different_tz"):
        diff = temporal_info.get("time_diff_hours", 0)
        diff_str = f"+{diff:g}" if diff > 0 else f"{diff:g}"
        lines.append(f"- 行程目的地時間: {dest_str} (目的地時差 {diff_str} 小時)")
    else:
        lines.append(f"- 行程目的地時間: 同使用者時區 ({dest_str})")

    lines.append(f"- 行程生命週期: {temporal_info['lifecycle_desc']}")

    if temporal_info.get("is_today_completed"):
        lines.append("- 當前活動狀態: 🌙 【今日排定活動已全部結束】(使用者詢問時請主動確認，並可建議休息或夜間自由活動)")
    elif temporal_info.get("current_day_number"):
        curr_d = temporal_info["current_day_number"]
        lines.append(f"- 當前活動狀態: 🏃 進行中 (焦點為 Day {curr_d} 當前時段安排)")

    lines.append("-------------------------------------------------------------")
    return "\n".join(lines)


def query_world_time(query: str) -> Dict[str, Any]:
    """
    世界時間查詢工具實作 (Server-side ReAct)
    支援城市名、國家名或 IANA 時區代碼。
    """
    if not query or not isinstance(query, str):
        query = "London"

    cleaned = query.strip().lower()
    matched_tz_name = None

    # 1. 查找已知城市映射 (依長度排序與邊界保護，防止子字串劫持)
    for keyword, tz in SORTED_TIMEZONE_MAP:
        if _match_temporal_keyword(keyword, query):
            matched_tz_name = tz
            break

    # 2. 嘗試直接作為 IANA 時區解析
    if not matched_tz_name:
        try:
            zoneinfo.ZoneInfo(query.strip())
            matched_tz_name = query.strip()
        except Exception:
            # 3. 常見世界大城市後備
            fallback_map = {
                "utc": "UTC", "gmt": "GMT", "london": "Europe/London",
                "paris": "Europe/Paris", "new york": "America/New_York",
                "tokyo": "Asia/Tokyo", "taipei": "Asia/Taipei", "sydney": "Australia/Sydney"
            }
            matched_tz_name = fallback_map.get(cleaned, "UTC")

    target_tz = safe_get_zoneinfo(matched_tz_name, fallback="UTC")
    now_target = datetime.now(target_tz)
    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

    utc_offset = now_target.utcoffset().total_seconds() / 3600.0 if now_target.utcoffset() else 0.0
    offset_str = f"UTC{'+' if utc_offset >= 0 else ''}{utc_offset:g}"

    return {
        "query": query,
        "timezone": str(target_tz),
        "local_time": now_target.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now_target.strftime("%Y-%m-%d"),
        "time": now_target.strftime("%H:%M"),
        "weekday": weekday_names[now_target.weekday()],
        "utc_offset": offset_str,
        "formatted": f"{query} 當前時間為 {now_target.strftime('%Y-%m-%d %H:%M')} ({weekday_names[now_target.weekday()]}, {offset_str})"
    }
