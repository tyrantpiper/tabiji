"""
Emergency Medical & Accessibility Geospatial Topology Simulator
================================================================
模擬海外醫療急難 (AED, 24/7 藥局, 急診, 無障礙廁所) 之 Overpass 拓撲解析與多語系症狀對照
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 🛡️ Windows Console CP950 編碼防護
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# 醫療急難與無障礙 OSM Overpass QL 標籤拓撲映射
EMERGENCY_OVERPASS_MAP = {
    # 1. 自動體外心臟除顫器 (AED)
    "aed": 'nwr["emergency"="defibrillator"]',
    # 2. 醫院與急救醫療設施 (Hospital / Emergency Clinic)
    "hospital": 'nwr["amenity"="hospital"]',
    "emergency_clinic": 'nwr["amenity"~"hospital|clinic"]["emergency"="yes"]',
    # 3. 24 小時 / 夜間調劑藥局 (Dispensing Pharmacy)
    "night_pharmacy": 'nwr["amenity"="pharmacy"]["opening_hours"="24/7"]',
    # 4. 無障礙洗手間 (Accessible Toilet)
    "accessible_restroom": 'nwr["amenity"="toilets"]["wheelchair"="yes"]',
}

# 醫療急難多語系關鍵字偵測詞庫 (中、日、英)
EMERGENCY_KEYWORDS = {
    "aed": ["aed", "除顫器", "急救心臟", "defibrillator", "心臟起搏", "自動體外心臟電擊去顫器"],
    "hospital": ["急診", "醫院", "診所", "掛急診", "救護車", "hospital", "emergency room", "er", "clinic", "病院", "救急"],
    "night_pharmacy": ["24小時藥局", "夜間藥局", "處方藥局", "調劑藥局", "藥局", "24h pharmacy", "night pharmacy", "薬局", "処方箋"],
    "accessible_restroom": ["無障礙廁所", "輪椅廁所", "多功能廁所", "親子廁所", "wheelchair toilet", "accessible restroom", "多目的トイレ", "車椅子トイレ"]
}

# 臨床緊急症狀與常備用藥中日英對照庫 (Clinical Cross-Border Medical Vocabulary)
CLINICAL_SYMPTOM_LEXICON = [
    {
        "category": "cardiovascular",
        "symptom_zh": "胸痛 / 心絞痛 / 呼吸困難",
        "symptom_ja": "胸の痛み・心臓の圧迫感・呼吸困難 (むねのいたみ)",
        "symptom_en": "Chest pain / Angina / Dyspnea",
        "urgency": "CRITICAL_ER",
        "action_prompt": "請立即撥打 119 (日本) 或 911 (美加)，就近尋找 AED 設施！"
    },
    {
        "category": "neurological",
        "symptom_zh": "抽搐 / 痙攣 / 意識不清 / 熱性痙攣",
        "symptom_ja": "けいれん・ひきつけ・意識障害 (けいれん)",
        "symptom_en": "Seizure / Convulsion / Altered consciousness / Febrile seizure",
        "urgency": "CRITICAL_ER",
        "action_prompt": "保持呼吸道暢通，側臥防嗆咳，切勿強塞異物，立即撥打 119 送急診！"
    },

    {
        "category": "gastrointestinal",
        "symptom_zh": "急性腸胃炎 / 嚴重腹瀉 / 嘔吐",
        "symptom_ja": "急性胃腸炎・激しい下痢・嘔吐 (げり・おうと)",
        "symptom_en": "Acute gastroenteritis / Severe diarrhea / Vomiting",
        "urgency": "URGENT_CLINIC",
        "action_prompt": "補充口服電解質液 (ORS)，至最近調劑藥局或內科診所就醫。"
    },
    {
        "category": "allergy",
        "symptom_zh": "過敏性休克 / 蕁麻疹 / 喉頭水腫",
        "symptom_ja": "アナフィラキシー・じんましん・喉の腫れ",
        "symptom_en": "Anaphylaxis / Urticaria / Laryngeal edema",
        "urgency": "CRITICAL_ER",
        "action_prompt": "若自備 EpiPen 請立即注射大腿外側，並前往最近急診醫院。"
    },
    {
        "category": "fever_pain",
        "symptom_zh": "高燒 / 頭痛 / 喉嚨痛",
        "symptom_ja": "高熱・頭痛・喉の痛み (こうねつ・のどのいたみ)",
        "symptom_en": "High fever / Headache / Sore throat",
        "urgency": "PHARMACY_FIRST",
        "action_prompt": "就近前往藥局購買 Acetaminophen (普拿疼/乙醯胺酚) 或 Ibuprofen (布洛芬)。"
    }
]

# 臨床檢傷分類優先級 (Clinical Triage Severity Ranking)
TRIAGE_PRIORITY = {
    "CRITICAL_ER": 100,
    "URGENT_CLINIC": 50,
    "PHARMACY_FIRST": 10
}

def _match_emergency_keyword(kw: str, text: str) -> bool:
    """拉丁字母強制採用 ASCII 字母邊界 (?<![A-Za-z0-9])...(?![A-Za-z0-9])，相容中英混排『最近的AED』且防止 'er' 誤判 'Uber'/'Burger'"""
    kw_clean = kw.strip().lower()
    if not kw_clean:
        return False
    if all(ord(c) < 128 for c in kw_clean):
        return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(kw_clean) + r"(?![A-Za-z0-9])", text, re.IGNORECASE))
    return kw_clean in text


def detect_emergency_intent(user_input: str) -> Dict[str, Any]:
    """
    偵測使用者輸入是否觸發醫療急難關鍵字 (嚴格遵循臨床檢傷分類優先權 CRITICAL_ER > URGENT_CLINIC > PHARMACY_FIRST)
    """
    if not user_input or not isinstance(user_input, str):
        return {
            "is_emergency": False,
            "matched_poi_category": None,
            "overpass_filter": None,
            "clinical_guidance": None,
        }
    clean_input = user_input.strip().lower()
    matched_category = None
    
    for category, kw_list in EMERGENCY_KEYWORDS.items():
        if any(_match_emergency_keyword(kw, clean_input) for kw in kw_list):
            matched_category = category
            break
            
    matched_candidates = []
    for item in CLINICAL_SYMPTOM_LEXICON:
        ja_raw = re.sub(r"\(.*?\)|（.*?）", "", item.get("symptom_ja", ""))
        ja_terms = [t.strip() for t in ja_raw.split("・") if t.strip()]
        terms = [t.strip() for t in item["symptom_zh"].split(" / ") + item["symptom_en"].lower().split(" / ")] + ja_terms
        if any(_match_emergency_keyword(w, clean_input) for w in terms):
            matched_candidates.append(item)
            
    # 若匹配到多個臨床症狀，依檢傷危急程度排序取最高優先級
    matched_clinical = None
    if matched_candidates:
        matched_candidates.sort(key=lambda x: TRIAGE_PRIORITY.get(x["urgency"], 0), reverse=True)
        matched_clinical = matched_candidates[0]
        if matched_category is None:
            matched_category = "night_pharmacy" if matched_clinical.get("urgency") == "PHARMACY_FIRST" else "hospital"
            
    is_emergency = matched_category is not None or matched_clinical is not None
    return {
        "is_emergency": is_emergency,
        "matched_poi_category": matched_category,
        "overpass_filter": EMERGENCY_OVERPASS_MAP.get(matched_category) if matched_category else None,
        "clinical_guidance": matched_clinical
    }


def format_emergency_response_card(intent: Dict[str, Any], anchor_place: str) -> Dict[str, Any]:
    """
    組裝緊急就醫導引卡片 (具備實體座標感知與多語系對照)
    """
    if not intent.get("is_emergency"):
        return {"active": False}
        
    guidance = intent.get("clinical_guidance")
    category = intent.get("matched_poi_category")
    
    return {
        "active": True,
        "anchor_place": anchor_place,
        "target_facility": category or "hospital",
        "urgency_level": guidance["urgency"] if guidance else "HIGH",
        "action_banner": guidance["action_prompt"] if guidance else "請就近前往合格醫療機構尋求協助。",
        "multilingual_card": {
            "zh": guidance["symptom_zh"] if guidance else "醫療協助請求",
            "ja": guidance["symptom_ja"] if guidance else "医療機関への受診希望",
            "en": guidance["symptom_en"] if guidance else "Request for medical assistance"
        }
    }

if __name__ == "__main__":
    print("=== Testing Emergency Medical Intent Detection ===")
    test_cases = [
        "小孩在淺草突然發高燒嘔吐，附近有沒有急診醫院？",
        "長輩胸口劇烈疼痛呼吸困難！快點找最近的AED！",
        "我的降血壓藥吃完了，附近哪裡有處方藥局？",
        "想去吃淺草附近的文字燒"
    ]
    
    for tc in test_cases:
        res = detect_emergency_intent(tc)
        print(f"\nUser: '{tc}'")
        print(f"  -> Is Emergency: {res['is_emergency']}")
        print(f"  -> Category: {res['matched_poi_category']}")
        print(f"  -> Overpass Tag: {res['overpass_filter']}")
        if res.get("clinical_guidance"):
            card = format_emergency_response_card(res, "淺草寺")
            print(f"  -> Urgency: {card['urgency_level']}")
            print(f"  -> Action: {card['action_banner']}")
            print(f"  -> Japanese Medical Card: {card['multilingual_card']['ja']}")
