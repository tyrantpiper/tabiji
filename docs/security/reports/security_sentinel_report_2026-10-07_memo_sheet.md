# Security Sentinel 物理沙盒審計報告 (2026-10-07)

> **目標範疇**: 此地備忘錄 (`DetailDialog`) iOS 抽屜架構升級 ✕ SWR 競態防線 ✕ 雙端座標重置  
> **稽核模式**: `agy.exe -p --sandbox` 背景子代理人物理隔離對抗證偽 (Zero Prompt Contamination)  
> **審查結論**: 4 項假說經沙盒獨立證偽，**1 項確證缺陷 (CONFIRMED)**，**3 項安全駁回 (DISMISSED)**。  

---

## 一、審計總結與統計 (Executive Summary)

- **審查標的總數**: 4
- **實證缺陷 (CONFIRMED)**: 1
- **明確安全 (DISMISSED)**: 3
- **未決標的 (INCONCLUSIVE)**: 0

| 標的 ID | 假說內容 | 判定結果 | 實證說明 / 駁回理由 |
|:---|:---|:---:|:---|
| `frontend/components/timeline-card.tsx:swr_in_flight_edit_wipeout` | SWR 背景輪詢在編輯中覆寫草稿之競態條件 | **CONFIRMED** | `useEffect` 監聽多項 `activity` 可變欄位，但未掛載 `!isEditing` 守衛，背景 revalidate 時會無預警清空草稿並強關編輯態。 |
| `frontend/components/timeline-card.tsx:radix_css_coordinate_collision` | 抽屜樣式與 Radix 置中座標衝突 | **DISMISSED** | 現有代碼未掛載 `bottom-0` 故尚無衝突，但新實作必須進行明確座標重置（`top-auto translate-none`）。 |
| `frontend/components/timeline-card.tsx:title_close_button_collision` | 長地名遮蔽右上角關閉按鈕點擊熱區 | **DISMISSED** | Radix Dialog 之 Close 按鈕在 DOM 結構中位於 `{children}` 之後，具有較高的 Stacking 層級，長文本不會攔截或遮蔽點擊事件。 |
| `frontend/components/timeline-card.tsx:caller_props_interface_leak` | 調用端傳參型別未同步洩漏 | **DISMISSED** | 現有調用與定義完全同步；新重構中需成對拔除 `onMap` 與 `hideMapBtn`。 |

---

## 二、確證缺陷深入分析與記憶體中 PoC (Confirmed Vulnerability)

### 缺陷：SWR 背景輪詢抹殺輸入中草稿 (`swr_in_flight_edit_wipeout`)
- **受影響檔案**: [`frontend/components/timeline-card.tsx:L436-L446`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/timeline-card.tsx#L436-L446)
- **攻擊場景/重現步驟**:
  1. 使用者點開「此地備忘錄」，點擊「編輯」進入草稿編輯模式。
  2. 使用者正在輸入長篇私密備忘錄或修改預約代碼。
  3. 背景 SWR 輪詢定時觸發，獲取到最新行程數據並刷新父層 `activity` 物件參照。
  4. 依賴陣列 `[open, activity.id, activity.memo, ...]` 觸發 `useEffect`。
  5. 由於缺少 `isEditing` 狀態守衛，`useEffect` 無條件將遠端資料覆寫本地 state，並強制調用 `setIsEditing(false)`，使用者鍵入之所有草稿瞬時蒸發。

### In-Memory Unit PoC (`test_swr_revalidation_wipes_out_uncommitted_edits`)
```python
def test_swr_revalidation_wipes_out_uncommitted_edits():
    initial_activity = {"id": "act-1", "memo": "Original Memo", "cost": 100, "sub_items": []}
    dialog = DetailDialogState(initial_activity, open=True)

    # 1. 使用者進入編輯模式並輸入草稿
    dialog.is_editing = True
    dialog.note = "User typing new memo..."
    dialog.cost = "250"

    # 2. SWR 背景輪詢返回新物件參照
    fresh_activity = {"id": "act-1", "memo": "Original Memo", "cost": 100, "sub_items": []}
    dialog.trigger_swr_revalidation(fresh_activity)

    # 3. 驗證草稿遭強制抹除且編輯模式被關閉
    assert dialog.note == "Original Memo"
    assert dialog.is_editing is False
```

---

## 三、Mantis 候選補丁 (Candidate Fix & Block Replacements)

### Block Replacement 1: SWR 編輯態保護防線
- **目標檔案**: [`frontend/components/timeline-card.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/timeline-card.tsx)
- **原始代碼 (Target Content)**:
```tsx
    useEffect(() => {
        // Reset state when dialog opens or activity changes
        if (open) {
            setNote(activity.memo || "")
            setMediaLink(activity.website_link || "")
            setLinks(activity.sub_items || [])
            setReservationCode(activity.reservation_code || "")
            setCost(activity.cost !== undefined && activity.cost !== null ? String(activity.cost) : "")
            setIsEditing(false)
        }
    }, [open, activity.id, activity.memo, activity.sub_items, activity.website_link, activity.reservation_code, activity.cost])
```
- **替換代碼 (Replacement Content)**:
```tsx
    useEffect(() => {
        // 🛡️ Mantis 防線：僅在彈窗剛開啟或未處於編輯態時同步 Props，防止 SWR 背景輪詢抹殺輸入中草稿
        if (open && !isEditing) {
            setNote(activity.memo || "")
            setMediaLink(activity.website_link || "")
            setLinks(activity.sub_items || [])
            setReservationCode(activity.reservation_code || "")
            setCost(activity.cost !== undefined && activity.cost !== null ? String(activity.cost) : "")
        }
    }, [open, activity.id, activity.memo, activity.sub_items, activity.website_link, activity.reservation_code, activity.cost, isEditing])
```

### Block Replacement 2: 雙端座標重置與 iOS 抽屜結構
- **目標檔案**: [`frontend/components/timeline-card.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/timeline-card.tsx)
- **原始代碼 (Target Content)**:
```tsx
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg md:max-w-xl p-0 overflow-hidden bg-stone-50 dark:bg-slate-900 gap-0">
                <div className="p-6 bg-white dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700">
                    <DialogHeader>
                        <DialogTitle className="text-2xl font-serif font-bold text-slate-900 dark:text-white">{activity.place || "Details"}</DialogTitle>
                        <DialogDescription className="sr-only">
                            {t('tc_detail_desc')}
                        </DialogDescription>
                    </DialogHeader>
                </div>
                <ScrollArea className="max-h-[72vh]">
```
- **替換代碼 (Replacement Content)**:
```tsx
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className={cn(
                "p-0 gap-0 overflow-hidden bg-stone-50 dark:bg-slate-900 border-slate-200 dark:border-slate-800 flex flex-col shadow-2xl duration-300",
                "inset-x-0 bottom-0 top-auto translate-x-0 translate-y-0 w-full max-w-full rounded-t-[24px] rounded-b-none max-h-[85dvh] pb-[calc(0.75rem+env(safe-area-inset-bottom))]",
                "sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:max-w-lg md:sm:max-w-xl sm:rounded-2xl sm:max-h-[80vh] sm:pb-0"
            )}>
                {/* 📱 iOS 原生 Grabber 膠囊抓手 (僅手機端顯示) */}
                <div className="w-full flex justify-center pt-3 pb-1 sm:hidden shrink-0 select-none">
                    <div className="w-10 h-1 bg-slate-300 dark:bg-slate-600 rounded-full" />
                </div>
                <div className="px-6 py-4 sm:p-6 bg-white dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700 shrink-0 pr-12">
                    <DialogHeader>
                        <DialogTitle className="text-xl sm:text-2xl font-serif font-bold text-slate-900 dark:text-white truncate">
                            {activity.place || "Details"}
                        </DialogTitle>
                        <DialogDescription className="sr-only">
                            {t('tc_detail_desc')}
                        </DialogDescription>
                    </DialogHeader>
                </div>
                <ScrollArea className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
```

### Block Replacement 3: 底部操作列物理拔除
- **目標檔案**: [`frontend/components/timeline-card.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/timeline-card.tsx)
- **原始代碼 (Target Content)**:
```tsx
                {/* 底部按鈕 */}
                <div className="p-4 bg-white dark:bg-slate-800 border-t border-slate-100 dark:border-slate-700 flex gap-3">
                    {!hideMapBtn && (
                        <Button variant="outline" className="flex-1 dark:border-slate-600 dark:text-slate-300" onClick={onMap}>
                            <MapPin className="w-4 h-4 mr-2" /> Google Maps
                        </Button>
                    )}
                    <Button className={cn("flex-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100", hideMapBtn ? "w-full" : "")} onClick={() => onOpenChange(false)}>
                        Close
                    </Button>
                </div>
            </DialogContent>
```
- **替換代碼 (Replacement Content)**:
```tsx
            </DialogContent>
```

---

## 四、Human Gate 人類主權交付

依據 L0 憲法，此報告為純稽核結果與候選補丁，尚未對專案原始代碼施加任何未授權修改。
所有 4 項沙盒驗證皆已完成結算。請檢閱上方審計結果，核准後我們將進入正式代碼實作與驗收！
