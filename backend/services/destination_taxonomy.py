"""
Destination Taxonomy & Dual-Track Grounding Engine
--------------------------------------------------
1. Destination Detection & Taxonomy Mapping (TW, JP, KR, TH, Global)
2. Dual-Track Query Rewriting (Local Deep-Dive + Global Reddit Traveler)
3. AC-2 Noise Blacklist Filtering & URL Domain Classification
4. AC-4 Strict 1-to-1 Citation Pruner (Anchored Index Protection)
"""

import re
import urllib.parse
from typing import List, Dict, Tuple, Any, Optional

# ==================== 1. Destination Taxonomy ====================

DESTINATION_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "TW": {
        "names": ["台灣", "臺灣", "台北", "臺北", "新北", "台中", "臺中", "台南", "臺南", "高雄", "花蓮", "台東", "臺東", "墾丁", "宜蘭", "Taiwan", "Taipei", "Taichung", "Kaohsiung"],
        "local_keywords": "ptt dcard 推薦",
        "official_domains": [r"taiwan\.net\.tw", r"travel\.taipei", r"taiwanbus\.tw", r"railway\.gov\.tw", r"\.gov\.tw"],
        "forum_domains": [r"ptt\.cc", r"dcard\.tw", r"mobile01\.com", r"backpackers\.com\.tw"],
        "food_review": [r"walkerland\.com\.tw", r"pixnet\.net", r"ipeen\.com\.tw"],
        "global_reddit_terms": "Taipei travel reddit recommendations",
    },
    "JP": {
        "names": ["日本", "東京", "京都", "大阪", "北海道", "沖繩", "福岡", "名古屋", "札幌", "奈良", "神戶", "箱根", "Japan", "Tokyo", "Kyoto", "Osaka", "Hokkaido", "Okinawa"],
        "local_keywords": "食べログ 推薦",
        "official_domains": [r"japan\.travel", r"japan-guide\.com", r"jnto\.go\.jp", r"\.go\.jp"],
        "forum_domains": [r"tabelog\.com", r"retrip\.jp", r"jalan\.net", r"chiebukuro\.yahoo\.co\.jp"],
        "food_review": [r"tabelog\.com", r"retty\.me"],
        "global_reddit_terms": "JapanTravel reddit recommendations",
    },
    "KR": {
        "names": ["韓國", "首爾", "釜山", "濟州", "弘大", "明洞", "仁川", "大邱", "Korea", "Seoul", "Busan", "Jeju"],
        "local_keywords": "맛집 推薦",
        "official_domains": [r"visitkorea\.or\.kr", r"english\.visitseoul\.net"],
        "forum_domains": [r"blog\.naver\.com", r"creatrip\.com", r"dcinside\.com"],
        "food_review": [r"mangoplate\.com", r"diningcode\.com"],
        "global_reddit_terms": "KoreaTravel reddit recommendations",
    },
    "TH": {
        "names": ["泰國", "曼谷", "清邁", "普吉島", "芭達雅", "蘇美島", "Thailand", "Bangkok", "Chiang Mai", "Phuket", "Pattaya"],
        "local_keywords": "pantip 推薦 必吃",
        "official_domains": [r"tourismthailand\.org"],
        "forum_domains": [r"pantip\.com"],
        "food_review": [r"wongnai\.com"],
        "global_reddit_terms": "ThailandTourism reddit bangkok recommendations",
    },
    "SG": {
        "names": ["新加坡", "獅城", "Singapore", "SG", "樟宜", "濱海灣", "聖淘沙"],
        "local_keywords": "必吃 美食 推薦",
        "official_domains": [r"visitsingapore\.com", r"stb\.gov\.sg"],
        "forum_domains": [r"hardwarezone\.com\.sg", r"burpple\.com", r"sethlui\.com", r"eatbook\.sg"],
        "food_review": [r"burpple\.com", r"sethlui\.com", r"hungrygowhere\.com"],
        "global_reddit_terms": "SingaporeTravel reddit recommendations food hawker",
    },
    "VN": {
        "names": ["越南", "河內", "胡志明", "胡志明市", "峴港", "會安", "富國島", "下龍灣", "Vietnam", "Hanoi", "Ho Chi Minh", "Da Nang", "Hoi An", "Phu Quoc"],
        "local_keywords": "必吃 美食 推薦 street food",
        "official_domains": [r"vietnam\.travel", r"vietnamtourism\.gov\.vn"],
        "forum_domains": [r"foody\.vn", r"tinhte\.vn", r"voz\.vn", r"diadiemanuong\.com"],
        "food_review": [r"foody\.vn", r"diadiemanuong\.com"],
        "global_reddit_terms": "VietnamTravel reddit street food recommendations hidden gems",
    },
    "EU": {
        "names": ["歐洲", "法國", "巴黎", "英國", "倫敦", "義大利", "羅馬", "佛羅倫斯", "米蘭", "威尼斯", "西班牙", "巴塞隆納", "馬德里", "德國", "柏林", "慕尼黑", "瑞士", "蘇黎世", "荷蘭", "阿姆斯特丹", "Europe", "Paris", "London", "Rome", "Barcelona", "Madrid", "Berlin", "Munich", "Amsterdam"],
        "local_keywords": "推薦 私房景點 美食",
        "official_domains": [r"france\.fr", r"visitbritain\.com", r"italia\.it", r"spain\.info", r"germany\.travel", r"myswitzerland\.com"],
        "forum_domains": [r"thefork\.", r"timeout\.com", r"lefigaro\.fr", r"visitlondon\.com"],
        "food_review": [r"thefork\.", r"timeout\.com", r"eater\.com"],
        "global_reddit_terms": "TravelEurope reddit recommendations hidden gems local tips",
    },
    "US": {
        "names": ["美國", "紐約", "洛杉磯", "舊金山", "西雅圖", "芝加哥", "拉斯維加斯", "夏威夷", "波士頓", "USA", "United States", "New York", "Los Angeles", "San Francisco", "Seattle", "Chicago", "Las Vegas", "Hawaii"],
        "local_keywords": "Eater 推薦 美食",
        "official_domains": [r"visittheusa\.com", r"nycgo\.com", r"gohawaii\.com"],
        "forum_domains": [r"yelp\.com", r"eater\.com", r"theinfatuation\.com", r"thrillist\.com"],
        "food_review": [r"yelp\.com", r"eater\.com", r"theinfatuation\.com"],
        "global_reddit_terms": "travel reddit usa recommendations local food hidden gems",
    },
    "HK": {
        "names": ["香港", "九龍", "尖沙咀", "中環", "旺角", "銅鑼灣", "澳門", "Hong Kong", "HK", "Macau"],
        "local_keywords": "OpenRice 必吃 推薦",
        "official_domains": [r"discoverhongkong\.com", r"macaotourism\.gov\.mo"],
        "forum_domains": [r"lihkg\.com", r"openrice\.com", r"discuss\.com\.hk"],
        "food_review": [r"openrice\.com", r"weekendhk\.com"],
        "global_reddit_terms": "HongKongTravel reddit recommendations food gems",
    },
}

# ==================== 2. AC-2 Noise Filter Patterns ====================

NOISE_TITLE_PATTERNS = [
    r'警察', r'犯罪', r'政黨', r'立法院', r'基金會', r'研討會', 
    r'論壇閉幕', r'宣導會', r'判決書', r'招標', r'公報', r'公會理事',
    r'兩岸論壇', r'高峰會閉幕', r'循環經濟論壇',
    # 封殺百科非旅遊條目 (動漫、虛構人物、角色列表等無關條目)
    r'角色列表', r'虛構角色', r'登場人物', r'動畫集數', r'配音員', r'漫畫列表',
    # 補齊詞根：徹底根除聲優與演藝條目穿透
    r'聲優', r'配音', r'單曲', r'專輯', r'電視動畫'
]

# ==================== 3. Query Extraction & Dual Rewriting ====================

def detect_destination(query: str, history: Optional[List[dict]] = None) -> Dict[str, Any]:
    """辨識目的地代碼 (TW, JP, KR, TH, GLOBAL) 與名稱"""
    combined_text = query
    if history:
        for msg in reversed(history[-4:]):
            content = msg.get("content") or msg.get("displayContent") or ""
            if not content:
                parts = msg.get("rawParts") or msg.get("parts") or []
                for p in parts:
                    if isinstance(p, dict) and p.get("text"):
                        content += p["text"]
            combined_text = f"{combined_text} {content}"

    for code, data in DESTINATION_TAXONOMY.items():
        for name in data["names"]:
            if re.search(r'\b' + re.escape(name) + r'\b', combined_text, re.IGNORECASE) or (len(name) <= 3 and name in combined_text):
                return {
                    "code": code,
                    "matched_name": name,
                    "taxonomy": data
                }

    return {
        "code": "GLOBAL",
        "matched_name": "全球",
        "taxonomy": None
    }


def detect_global_country_entity(query: str, history: Optional[List[dict]] = None) -> Optional[Tuple[str, str]]:
    """
    從全球 190+ 國資料庫中反查中文或英文國名，回傳 (中文國名, 英文正規名)
    支援長尾國家（如冰島、埃及、秘魯、紐西蘭、摩洛哥等）在 0ms 內映射為地道英文
    """
    try:
        from services.geocode_service import COUNTRY_TO_ISO
    except ImportError:
        return None

    combined = query
    if history:
        for msg in reversed(history[-2:]):
            c = msg.get("content") or msg.get("displayContent") or ""
            if c:
                combined += f" {c}"

    # 按長度降序匹配，避免短詞搶先誤判
    sorted_countries = sorted(COUNTRY_TO_ISO.keys(), key=len, reverse=True)
    for country_name in sorted_countries:
        if len(country_name) >= 2 and country_name in combined:
            iso = COUNTRY_TO_ISO[country_name]
            # 找到英文正規名（取 COUNTRY_TO_ISO 中同 ISO 的英文名稱）
            eng_name = next(
                (k for k, v in COUNTRY_TO_ISO.items() if v == iso and re.match(r'^[A-Za-z\s]+$', k)),
                country_name
            )
            return country_name, eng_name

    return None


def clean_conversational_query(user_msg: str) -> str:
    """去除客套語與搜尋動詞提煉純關鍵字"""
    clean_msg = re.sub(
        r'^(?:你好|您好|哈囉|嗨|嗨嗨|早安|午安|晚安|請|麻煩|幫我|我想|想要|我想要|請你|你可以|能不能|可以|要你|\s)*(?:幫我|替我|\s)*(?:網路搜索|網路搜尋|搜尋|搜索|google|谷歌|上網查|查一下|查看|找一下|查詢|看一下|\s)*',
        '',
        user_msg.strip(),
        flags=re.IGNORECASE
    ).strip()
    clean_msg = re.sub(r'(?:現在的|當前的|推薦的|熱門的|有沒有|我想知道|我想了解|有哪些|哪裡有|告訴我)', ' ', clean_msg)
    clean_msg = re.sub(r'[嗎？\?~～!！\.]+$', '', clean_msg).strip()
    clean_msg = re.sub(r'\s+', ' ', clean_msg).strip()
    return clean_msg or user_msg


def resolve_destination_regions(dest_code: str, query: str) -> Tuple[str, str]:
    """
    動態解析搜尋區域代碼 (Dynamic Search Region Resolution)
    回傳: (local_region, global_region)
    在地軌優先對齊繁中或指標國，全球軌一律鎖定 us-en 穿透 Reddit
    """
    is_cjk = any("\u4e00" <= c <= "\u9fff" for c in query)

    if dest_code == "JP":
        local_reg = "jp-jp"
    elif dest_code == "KR":
        local_reg = "kr-kr"
    elif dest_code == "US":
        local_reg = "us-en"
    elif dest_code in ("TW", "HK"):
        local_reg = "tw-tzh"
    else:
        local_reg = "tw-tzh" if is_cjk else "us-en"

    return local_reg, "us-en"


def generate_dual_queries(query: str, history: Optional[List[dict]] = None) -> Tuple[str, str, Dict[str, Any]]:
    """
    雙軌關鍵字合成 (Local Deep-Dive + Global Reddit Traveler)
    回傳: (local_query, global_query, metadata)
    """
    clean_text = clean_conversational_query(query)
    dest_info = detect_destination(query, history=history)
    code = dest_info["code"]
    tax = dest_info.get("taxonomy")

    local_reg, global_reg = resolve_destination_regions(code, query)

    metadata = {
        "destination_code": code,
        "matched_destination": dest_info["matched_name"],
        "clean_query": clean_text,
        "local_region": local_reg,
        "global_region": global_reg,
    }

    if code != "GLOBAL" and tax:
        matched_dest = dest_info["matched_name"]
        local_terms = tax["local_keywords"]
        global_terms = tax["global_reddit_terms"]

        # 在地軌：若問題內未包含目的地名稱，補上目的地
        if matched_dest not in clean_text:
            local_query = f"{matched_dest} {clean_text} {local_terms}".strip()
        else:
            local_query = f"{clean_text} {local_terms}".strip()

        # 全球軌：注入 Reddit 英文詞彙
        global_query = f"{matched_dest} {clean_text} {global_terms}".strip()
    else:
        # 🌐 智能全域實體補強：若命中 190+ 國中任一長尾國家（如冰島、埃及、秘魯、紐西蘭、土耳其）
        dynamic_country = detect_global_country_entity(query, history=history)
        if dynamic_country:
            c_zh, c_en = dynamic_country
            local_query = f"{clean_text} 旅遊 推薦".strip() if c_zh in clean_text else f"{c_zh} {clean_text} 旅遊 推薦".strip()
            # 全球軌動態注入地道英文國名，直接擊中 Reddit 國際旅人版！
            global_query = f"{c_en} travel reddit recommendations tips hidden gems".strip()
            metadata["matched_destination"] = c_zh
        else:
            # 通用全球目的地
            local_query = f"{clean_text} 旅遊 推薦".strip()
            global_query = f"{clean_text} travel reddit recommendations tips".strip()

    return local_query, global_query, metadata


# ==================== 4. AC-2 Blacklist & Category Mapping ====================

def classify_and_filter_results(
    raw_results: List[Dict[str, Any]], 
    user_query: str,
    dest_code: str = "GLOBAL"
) -> List[Dict[str, Any]]:
    """
    實作 AC-2 雜訊黑名單過濾與 URL 網域分類
    """
    cleaned_sources = []
    seen_urls = set()
    allow_sensitive = any(k in user_query for k in ["警察", "犯罪", "治安", "政治", "安全", "研討會"])
    tax = DESTINATION_TAXONOMY.get(dest_code)

    for item in raw_results:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        snippet = item.get("snippet", "").strip()
        
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        
        # 1. AC-2 黑名單物理過濾
        if not allow_sensitive:
            if any(re.search(pat, title, re.IGNORECASE) for pat in NOISE_TITLE_PATTERNS):
                continue
            if any(re.search(pat, snippet[:120], re.IGNORECASE) for pat in NOISE_TITLE_PATTERNS):
                continue

        # 2. Domain Category Mapping
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()

        category = "general"
        badge = {"text": "🌐 旅遊指南", "color": "text-slate-500 bg-slate-500/10 border-slate-500/20"}

        # 官方站點
        official_rules = [
            r"\.gov\.tw", r"\.go\.jp", r"japan\.travel", r"visitkorea", r"tourismthailand",
            r"visitsingapore", r"stb\.gov\.sg", r"vietnam\.travel", r"france\.fr",
            r"visitbritain", r"italia\.it", r"spain\.info", r"germany\.travel",
            r"discoverhongkong", r"visittheusa"
        ]
        if tax and "official_domains" in tax:
            official_rules.extend(tax["official_domains"])

        if any(re.search(r, netloc) for r in official_rules):
            category = "official"
            badge = {"text": "🏛️ 官方觀光局", "color": "text-emerald-500 bg-emerald-500/10 border-emerald-500/20"}
        # 在地論壇與食評
        elif any(f in netloc for f in [
            "ptt.cc", "dcard.tw", "mobile01.com", "tabelog.com", "retrip.jp", "jalan.net",
            "blog.naver.com", "pantip.com", "hardwarezone.com.sg", "burpple.com", "sethlui.com",
            "foody.vn", "tinhte.vn", "voz.vn", "thefork.", "timeout.com", "lihkg.com", "openrice.com"
        ]):
            category = "local_forum"
            if "ptt.cc" in netloc:
                badge = {"text": "🇹🇼 PTT 在地情報", "color": "text-blue-500 bg-blue-500/10 border-blue-500/20"}
            elif "dcard.tw" in netloc:
                badge = {"text": "🇹🇼 Dcard 旅人熱議", "color": "text-cyan-500 bg-cyan-500/10 border-cyan-500/20"}
            elif "tabelog.com" in netloc:
                badge = {"text": "🇯🇵 Tabelog 老饕評分", "color": "text-orange-500 bg-orange-500/10 border-orange-500/20"}
            elif "hardwarezone.com.sg" in netloc:
                badge = {"text": "🇸🇬 HardwareZone 獅城熱議", "color": "text-red-500 bg-red-500/10 border-red-500/20"}
            elif "burpple.com" in netloc or "sethlui.com" in netloc:
                badge = {"text": "🇸🇬 獅城在地食評", "color": "text-amber-500 bg-amber-500/10 border-amber-500/20"}
            elif "foody.vn" in netloc or "tinhte.vn" in netloc or "voz.vn" in netloc:
                badge = {"text": "🇻🇳 越南社群在地推薦", "color": "text-emerald-500 bg-emerald-500/10 border-emerald-500/20"}
            elif "thefork." in netloc:
                badge = {"text": "🇪🇺 TheFork 歐洲老饕首選", "color": "text-violet-500 bg-violet-500/10 border-violet-500/20"}
            elif "timeout.com" in netloc:
                badge = {"text": "🗺️ TimeOut 都市導覽", "color": "text-sky-500 bg-sky-500/10 border-sky-500/20"}
            elif "lihkg.com" in netloc:
                badge = {"text": "🇭🇰 LIHKG 香港在地討論", "color": "text-indigo-500 bg-indigo-500/10 border-indigo-500/20"}
            elif "openrice.com" in netloc:
                badge = {"text": "🇭🇰 OpenRice 開飯喇", "color": "text-amber-500 bg-amber-500/10 border-amber-500/20"}
            else:
                badge = {"text": "📍 在地社群/評測", "color": "text-indigo-500 bg-indigo-500/10 border-indigo-500/20"}
        # 全球論壇
        elif "reddit.com" in netloc:
            category = "global_forum"
            badge = {"text": "💬 Reddit 全球旅人", "color": "text-amber-500 bg-amber-500/10 border-amber-500/20"}
        elif "tripadvisor.com" in netloc or "wikivoyage.org" in netloc or "lonelyplanet.com" in netloc:
            category = "global_forum"
            badge = {"text": "🌍 國際旅遊社群", "color": "text-yellow-500 bg-yellow-500/10 border-yellow-500/20"}
        # 美食評測
        elif any(r in netloc for r in ["google.com/maps", "yelp.com", "eater.com", "theinfatuation.com", "walkerland.com.tw", "retty.me"]):
            category = "review"
            if "yelp.com" in netloc:
                badge = {"text": "🇺🇸 Yelp 權威食評", "color": "text-red-500 bg-red-500/10 border-red-500/20"}
            elif "eater.com" in netloc or "theinfatuation.com" in netloc:
                badge = {"text": "🇺🇸 Eater 深度探店", "color": "text-rose-500 bg-rose-500/10 border-rose-500/20"}
            else:
                badge = {"text": "⭐ 景點美食評分", "color": "text-rose-500 bg-rose-500/10 border-rose-500/20"}

        cleaned_sources.append({
            "title": title,
            "url": url,
            "uri": url,
            "snippet": snippet,
            "category": category,
            "badge": badge
        })

    return cleaned_sources


# ==================== 5. AC-4 Citation Pruner ====================

def prune_and_align_citations(
    full_text: str, 
    candidate_sources: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    AC-4 嚴格 1對1 對齊演算法：
    1. 正則萃取 full_text 實際引用的 [1], [2], [3] 等標籤。
    2. 比對 candidate_sources 的 1-based index。
    3. 僅保留被內文引用的 Sources，賦予原錨點 citation_index，物理剔除未引用的多餘來源。
    """
    if not full_text or not candidate_sources:
        return []

    # 🛡️ 容錯正規化：統一全形與多標籤格式（如 [1, 2]、[1][2]、以及全形 【1】）
    normalized_text = full_text.replace('【', '[').replace('】', ']')
    raw_blocks = re.findall(r'\[([\d\s,，]+)\]', normalized_text)
    cited_indices = set()
    for block in raw_blocks:
        for num_str in re.findall(r'\d+', block):
            try:
                val = int(num_str)
                if 1 <= val <= len(candidate_sources):
                    cited_indices.add(val)
            except ValueError:
                continue

    final_sources = []
    if cited_indices:
        for idx in sorted(list(cited_indices)):
            src = candidate_sources[idx - 1]
            final_sources.append({
                "citation_index": idx,
                "title": src.get("title", "參考來源"),
                "uri": src.get("url") or src.get("uri", ""),
                "snippet": src.get("snippet", ""),
                "category": src.get("category", "general"),
                "badge": src.get("badge", {"text": "參考資料", "color": "text-slate-500"})
            })
    else:
        # 兜底：若 LLM 漏寫 [i]，進行標題實體詞重疊匹配
        for idx, src in enumerate(candidate_sources[:3], 1):
            title = src.get("title", "")
            words = [w for w in re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]{3,}', title) if w not in ["推薦", "攻略", "旅行", "景點", "美食"]]
            if any(w in full_text for w in words):
                final_sources.append({
                    "citation_index": idx,
                    "title": title,
                    "uri": src.get("url") or src.get("uri", ""),
                    "snippet": src.get("snippet", ""),
                    "category": src.get("category", "general"),
                    "badge": src.get("badge", {"text": "相關來源", "color": "text-slate-500"})
                })

    return final_sources
