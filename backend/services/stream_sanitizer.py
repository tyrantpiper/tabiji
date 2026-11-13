"""
Stream Lookahead Sanitizer (2026 Sentinel Shield)
--------------------------------------------------
1. 滑動前瞻緩衝區 (Sliding Lookahead Buffer, 30 chars safety window)
2. 跨 Chunk 思考思維鏈標籤撕裂過濾 (<thought>, <thinking>, 'Thinking Process:')
3. 輸出層內部協定 JSON 攔截 (中段出現之 items, day, place_name 等結構化資料)，
   無縫轉化為 FunctionCall，確保前端聊天氣泡 100% 純淨自然語言。
"""

import re
import json
from typing import List, Tuple, Optional, Dict, Any

THOUGHT_START = ("<thought>", "<thinking>", "Thinking Process:")
THOUGHT_END = ("</thought>", "</thinking>")

# 攔截 JSON 協定開頭特徵 (涵蓋可選的 markdown 標記與 items/day/place_name/amount/title 鍵值)
JSON_TRIGGER_RE = re.compile(
    r'(?:```(?:json)?\s*)?\{\s*(?:"items"\s*:\s*\[|"day"\s*:|"place_name"\s*:|"amount"\s*:|"title"\s*:)',
    re.IGNORECASE
)


class StreamLookaheadSanitizer:
    """
    狀態化串流前瞻安全淨化器
    支援平衡大括號閉環偵測、跨 Chunk 思考標籤撕裂過濾、與中段 JSON 截獲後的自然語言接續。
    """
    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.buffer = ""
        self.in_thought = False
        self.in_json = False
        self.json_accumulator = ""
        self.intercepted_jsons: List[Dict[str, Any]] = []
        self._decoder = json.JSONDecoder()

    def feed(self, chunk_text: str) -> List[str]:
        """
        輸入新的字串 chunk，回傳可以安全推送至前端之純淨文字清單 (event: text)
        """
        if not chunk_text:
            return []

        emitted_texts: List[str] = []

        if self.in_json:
            self.json_accumulator += chunk_text
            self._try_complete_json(emitted_texts)
        else:
            self.buffer += chunk_text

        # 狀態機持續處理緩衝區內的思維鏈標籤與 JSON 特徵
        while True:
            # 1. 思考標籤動態濾除 (支援跨 Chunk 撕裂)
            if self.in_thought:
                matched_end = None
                for e in THOUGHT_END:
                    if e in self.buffer:
                        matched_end = e
                        break
                if matched_end:
                    _, _, self.buffer = self.buffer.partition(matched_end)
                    self.in_thought = False
                    continue
                else:
                    # 仍處於思考標籤中，檢查尾端是否可能為閉合標籤的前綴 (如 "</th")
                    matched_prefix_len = 0
                    for e in THOUGHT_END:
                        for plen in range(min(len(e) - 1, len(self.buffer)), 0, -1):
                            if self.buffer.endswith(e[:plen]):
                                if plen > matched_prefix_len:
                                    matched_prefix_len = plen
                    if matched_prefix_len > 0:
                        self.buffer = self.buffer[-matched_prefix_len:]
                    else:
                        self.buffer = ""
                    break

            matched_start = None
            for t in THOUGHT_START:
                if t in self.buffer:
                    matched_start = t
                    break
            if matched_start:
                pre, _, post = self.buffer.partition(matched_start)
                if pre:
                    emitted_texts.append(pre)
                self.buffer = post
                self.in_thought = True
                continue

            # 2. 內部 JSON 協定動態攔截 (支援中段出現與跨 Chunk 拆裂)
            if not self.in_json:
                match = JSON_TRIGGER_RE.search(self.buffer)
                if match:
                    pre = self.buffer[:match.start()]
                    if pre:
                        emitted_texts.append(pre)
                    raw_json_start = self.buffer[match.start():]
                    self.buffer = ""
                    self.in_json = True
                    self.json_accumulator = raw_json_start
                    self._try_complete_json(emitted_texts)
                    # 若 JSON 已在當前 chunk 閉合，繼續迴圈處理後續字串
                    if not self.in_json:
                        continue
                    else:
                        break
                else:
                    # 保留 window_size 字元防範跨 Chunk 標籤特徵拆裂
                    min_threshold = self.window_size + 5
                    if len(self.buffer) > min_threshold:
                        flushable = self.buffer[:-self.window_size]
                        self.buffer = self.buffer[-self.window_size:]
                        emitted_texts.append(flushable)
                    break
            else:
                break

        return emitted_texts

    def _try_complete_json(self, emitted_texts: List[str]):
        """嘗試從 json_accumulator 中解碼完整的 JSON 物件並還原後續文字"""
        s = self.json_accumulator
        brace_idx = s.find('{')
        if brace_idx == -1:
            return

        try:
            obj, end_idx = self._decoder.raw_decode(s, brace_idx)
            if isinstance(obj, dict):
                self.intercepted_jsons.append(obj)

            # 提取 JSON 物件之後的剩餘字串
            rest = s[end_idx:]
            # 剝除緊隨其後的 markdown closing code fence (如 ``` 或 ```\n)
            rest = re.sub(r'^\s*```(?:json)?\s*', '', rest, flags=re.IGNORECASE)

            self.in_json = False
            self.json_accumulator = ""
            # 將後續自然語言字串放回緩衝區供後續串流消費
            self.buffer = rest + self.buffer
        except (json.JSONDecodeError, ValueError):
            # JSON 仍在串流中，尚未接收到閉合大括號，等待下一 chunk
            pass

    def flush(self) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        """
        串流結束時調用，釋放尾端安全文字並解析截獲之 JSON 協定
        """
        emitted_texts: List[str] = []

        # 若串流結束時仍停留在 in_json 狀態，執行盡力而為容錯提取
        if self.in_json and self.json_accumulator:
            full_json_str = self.json_accumulator.strip()
            if full_json_str.startswith("```"):
                full_json_str = re.sub(r"^```(?:json)?\s*", "", full_json_str, flags=re.IGNORECASE)
                full_json_str = re.sub(r"\s*```$", "", full_json_str)
                full_json_str = full_json_str.strip()

            try:
                data = json.loads(full_json_str)
                if isinstance(data, dict):
                    self.intercepted_jsons.append(data)
            except Exception:
                m = re.search(r'(\{[\s\S]*\})', full_json_str)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        if isinstance(data, dict):
                            self.intercepted_jsons.append(data)
                        rest = full_json_str[m.end():]
                        if rest:
                            self.buffer = rest + self.buffer
                    except Exception:
                        pass
            self.in_json = False
            self.json_accumulator = ""

        if self.buffer and not self.in_thought:
            emitted_texts.append(self.buffer)
            self.buffer = ""

        # 正規化截獲的 JSON 物件
        parsed_json: Optional[Dict[str, Any]] = None
        if self.intercepted_jsons:
            if len(self.intercepted_jsons) == 1:
                parsed_json = self.intercepted_jsons[0]
            else:
                # 合併多個扁平項目為標準 batch items 格式
                flat_items = []
                for j in self.intercepted_jsons:
                    if "items" in j and isinstance(j["items"], list):
                        flat_items.extend(j["items"])
                    else:
                        flat_items.append(j)
                parsed_json = {"items": flat_items}

        return emitted_texts, parsed_json
