import pytest
from services.destination_taxonomy import (
    detect_destination,
    generate_dual_queries,
    classify_and_filter_results,
    prune_and_align_citations
)

def test_detect_destination():
    # 台灣測試
    res_tw = detect_destination("台北週末有什麼隱藏美食？")
    assert res_tw["code"] == "TW"
    assert res_tw["matched_name"] == "台北"

    # 日本測試
    res_jp = detect_destination("京都清水寺附近拉麵推薦")
    assert res_jp["code"] == "JP"
    assert res_jp["matched_name"] == "京都"

    # 韓國測試
    res_kr = detect_destination("首爾弘大逛街地圖")
    assert res_kr["code"] == "KR"
    assert res_kr["matched_name"] == "首爾"

    # 新加坡測試
    res_sg = detect_destination("新加坡濱海灣花園美食")
    assert res_sg["code"] == "SG"
    assert res_sg["matched_name"] == "新加坡"

    # 越南測試
    res_vn = detect_destination("峴港會安五天四夜景點")
    assert res_vn["code"] == "VN"
    assert res_vn["matched_name"] == "峴港"

    # 歐洲測試
    res_eu = detect_destination("巴黎羅浮宮附近法式餐廳")
    assert res_eu["code"] == "EU"
    assert res_eu["matched_name"] == "巴黎"

    # 美國測試
    res_us = detect_destination("紐約百老匯推薦必看音樂劇")
    assert res_us["code"] == "US"
    assert res_us["matched_name"] == "紐約"

    # 香港測試
    res_hk = detect_destination("香港尖沙咀在地茶餐廳")
    assert res_hk["code"] == "HK"
    assert res_hk["matched_name"] == "香港"

    # 全球預設
    res_global = detect_destination("哪裡有漂亮的極光？")
    assert res_global["code"] == "GLOBAL"


def test_generate_dual_queries():
    local_q, global_q, meta = generate_dual_queries("台北隱藏美食")
    assert meta["destination_code"] == "TW"
    assert "ptt" in local_q or "dcard" in local_q
    assert "reddit" in global_q

    local_jp, global_jp, meta_jp = generate_dual_queries("京都拉麵")
    assert meta_jp["destination_code"] == "JP"
    assert "食べログ" in local_jp
    assert "reddit" in global_jp


def test_ac2_noise_filter():
    raw_results = [
        {"title": "2025 國際警察合作論壇閉幕式", "url": "https://police.gov.tw/1", "snippet": "研討會圓滿成功"},
        {"title": "台北101觀景台門票與私房美食指南", "url": "https://travel.taipei/spot", "snippet": "推薦景點"},
        {"title": "台灣地方政黨基金會研討會", "url": "https://party.org.tw/news", "snippet": "政治議題"},
        {"title": "[食記] 台北超強隱藏拉麵 PTT", "url": "https://ptt.cc/bbs/Food/1", "snippet": "老饕推爆"}
    ]

    filtered = classify_and_filter_results(raw_results, "台北美食推薦", dest_code="TW")
    # 警察與基金會應被物理過濾
    titles = [item["title"] for item in filtered]
    assert not any("警察" in t for t in titles)
    assert not any("基金會" in t for t in titles)
    assert len(filtered) == 2
    assert any("travel.taipei" in item["url"] for item in filtered)
    assert any("ptt.cc" in item["url"] for item in filtered)

    # 驗證徽章分類
    official_item = next(item for item in filtered if "travel.taipei" in item["url"])
    assert official_item["category"] == "official"
    assert "官方觀光局" in official_item["badge"]["text"]

    forum_item = next(item for item in filtered if "ptt.cc" in item["url"])
    assert forum_item["category"] == "local_forum"
    assert "PTT" in forum_item["badge"]["text"]

    # 驗證新加坡、歐洲與美國網域徽章
    global_test_results = [
        {"title": "Burpple Hawker Guide", "url": "https://www.burpple.com/feed", "snippet": "Best food"},
        {"title": "HardwareZone Travel Eat", "url": "https://forums.hardwarezone.com.sg/1", "snippet": "Local tips"},
        {"title": "TheFork Paris Top 10", "url": "https://www.thefork.fr/restaurant/1", "snippet": "Bistro"},
        {"title": "Yelp NYC Best Pastrami", "url": "https://www.yelp.com/biz/katz", "snippet": "Deli"},
        {"title": "OpenRice HK Dim Sum", "url": "https://www.openrice.com/zh/hongkong/r-1", "snippet": "Dim sum"},
    ]
    classified_global = classify_and_filter_results(global_test_results, "美食推薦", dest_code="GLOBAL")
    badge_texts = [item["badge"]["text"] for item in classified_global]
    assert any("HardwareZone" in t for t in badge_texts)
    assert any("獅城在地食評" in t for t in badge_texts)
    assert any("TheFork" in t for t in badge_texts)
    assert any("Yelp" in t for t in badge_texts)
    assert any("OpenRice" in t for t in badge_texts)


def test_ac4_citation_pruning():
    candidate_sources = [
        {"title": "台北101觀景台", "url": "https://source1.com", "snippet": "高樓美景", "category": "official"},
        {"title": "鼎泰豐小籠包", "url": "https://source2.com", "snippet": "知名排隊美食", "category": "review"},
        {"title": "師大夜市巷弄咖啡", "url": "https://source3.com", "snippet": "隱密文青景點", "category": "local_forum"},
        {"title": "九份老街茶館", "url": "https://source4.com", "snippet": "懷舊山城", "category": "local_forum"}
    ]

    # LLM 內文僅提及 [1] 與 [3]
    full_text = "台北市區推薦前往台北101觀景台欣賞夜景[1]，午後則可以到師大夜市探訪隱藏咖啡館[3]，氣氛絕佳！"

    aligned = prune_and_align_citations(full_text, candidate_sources)
    assert len(aligned) == 2
    cited_indices = [item["citation_index"] for item in aligned]
    assert cited_indices == [1, 3]
    assert aligned[0]["uri"] == "https://source1.com"
    assert aligned[1]["uri"] == "https://source3.com"

    # 越界引用測試 (模型幻覺出 [9])
    hallucinated_text = "推薦私房好去處[1] 以及不存在的神祕秘境[9]！"
    aligned_h = prune_and_align_citations(hallucinated_text, candidate_sources)
    assert len(aligned_h) == 1
    assert aligned_h[0]["citation_index"] == 1

    # 複合標籤與全形標籤容錯測試 ([1, 2] 與 【3】)
    compound_text = "台北101與鼎泰豐皆為熱門名勝[1, 2]，亦可前往師大夜市【3】散步。"
    aligned_compound = prune_and_align_citations(compound_text, candidate_sources)
    assert len(aligned_compound) == 3
    compound_indices = [item["citation_index"] for item in aligned_compound]
    assert compound_indices == [1, 2, 3]


def test_detect_global_country_entity():
    from services.destination_taxonomy import detect_global_country_entity
    # 冰島
    res_is = detect_global_country_entity("冰島雷克雅維克自駕極光")
    assert res_is is not None
    assert res_is[0] == "冰島"
    assert res_is[1].lower() == "iceland"

    # 秘魯
    res_pe = detect_global_country_entity("秘魯馬丘比丘門票與攻略")
    assert res_pe is not None
    assert res_pe[0] == "秘魯"
    assert res_pe[1].lower() == "peru"

    # 埃及
    res_eg = detect_global_country_entity("埃及開羅金字塔推薦導遊")
    assert res_eg is not None
    assert res_eg[0] == "埃及"
    assert res_eg[1].lower() == "egypt"


def test_generate_dual_queries_long_tail():
    # 測試未在預設 9 大國之長尾國 (冰島)
    local_q, global_q, meta = generate_dual_queries("第一次去冰島自駕，推薦隱藏版極光秘境")
    assert "冰島" in local_q
    assert "Iceland" in global_q
    assert "reddit" in global_q
    assert meta["matched_destination"] == "冰島"
    assert meta["local_region"] == "tw-tzh"
    assert meta["global_region"] == "us-en"


def test_resolve_destination_regions():
    from services.destination_taxonomy import resolve_destination_regions
    assert resolve_destination_regions("JP", "京都拉麵")[0] == "jp-jp"
    assert resolve_destination_regions("KR", "首爾烤肉")[0] == "kr-kr"
    assert resolve_destination_regions("US", "紐約貝果")[0] == "us-en"
    assert resolve_destination_regions("TW", "台北牛肉麵")[0] == "tw-tzh"
    assert resolve_destination_regions("HK", "香港點心")[0] == "tw-tzh"
    # 中文長尾或歐洲預設繁中
    assert resolve_destination_regions("EU", "巴黎咖啡廳")[0] == "tw-tzh"
    assert resolve_destination_regions("GLOBAL", "埃及金字塔")[0] == "tw-tzh"
    # 純英文查詢
    assert resolve_destination_regions("GLOBAL", "Egypt pyramids tips")[0] == "us-en"
    # 全球軌固定 us-en
    assert resolve_destination_regions("JP", "京都拉麵")[1] == "us-en"


def test_no_or_operator_in_taxonomies():
    from services.destination_taxonomy import DESTINATION_TAXONOMY
    for code, data in DESTINATION_TAXONOMY.items():
        local_kw = data.get("local_keywords", "")
        assert " OR " not in local_kw, f"{code} local_keywords still contains bloated ' OR ': {local_kw}"


def test_voice_actor_and_anime_noise_filter():
    from services.destination_taxonomy import classify_and_filter_results
    raw = [
        {"title": "林原惠 (維基百科)", "url": "https://zh.wikipedia.org/wiki/hayashibara", "snippet": "日本女性聲優、歌手。出道以來長年作為人氣聲優活躍於各領域。"},
        {"title": "名偵探柯南配音名單", "url": "https://zh.wikipedia.org/wiki/conan", "snippet": "電視動畫配音員陣容詳細清單。"},
        {"title": "2026 京都賞楓25選攻略", "url": "https://osaka.letsgojp.com/1", "snippet": "京都最新賞楓景點推薦與紅葉預報。"}
    ]
    filtered = classify_and_filter_results(raw, "京都賞楓推薦", dest_code="JP")
    titles = [item["title"] for item in filtered]
    assert "林原惠 (維基百科)" not in titles
    assert "名偵探柯南配音名單" not in titles
    assert len(filtered) == 1
    assert "2026 京都賞楓25選攻略" in titles[0]
