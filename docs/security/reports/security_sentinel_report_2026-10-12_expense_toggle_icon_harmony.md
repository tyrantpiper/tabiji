# 🛡️ Security Sentinel 對抗性沙盒審計報告 (Expense Toggle & Share Button Icon Harmony)

> **審計日期**: 2026-10-12  
> **執行規範**: Security Sentinel v2.0 (Cloudflare 6-Phase Ledger ✕ Google Mantis Patch Synthesis)  
> **審計範圍**: [tools-view.tsx](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/tools-view.tsx), [remaining.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/i18n/remaining.ts), [expense.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/i18n/expense.ts), [translations.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/translations.ts)  
> **隔離機制**: In-Memory PoC 沙盒證偽 (`frontend/__tests__/expense-toggle-sentinel.test.ts`)  

---

## 1. 執行總結 (Executive Summary)

- **總檢驗標的數 (Total Hypotheses)**: 5
- **實證成立缺陷 (Confirmed Vulnerabilities / Regressions)**: 5
- **駁回假說 (Dismissed)**: 0
- **沙盒驗證狀態**: `5/5 CONFIRMED` (在未修補程式碼上執行測試已 100% 觸發斷言失敗，完成證偽)
- **候選補丁資產**: [patch_candidate_expense_toggle.diff](file:///d:/Project/Tabidachi/travel-pwa/docs/security/history/patches/patch_candidate_expense_toggle.diff)

---

## 2. 審計攻擊面與缺陷矩陣 (Attack Surface Matrix)

| 編號 | 標的檔案 | 向量類型 | 假說與風險分析 | 沙盒驗證結果 |
| :--- | :--- | :--- | :--- | :--- |
| **TC-1** | `remaining.ts` | `i18n_dictionary_pollution_and_duplicate_icon` | `tv_list` 殘留硬編碼剪貼簿表情符號 `📋`，與 JSX 內原生 `<List />` 向量圖標重複碰撞 | **CONFIRMED** |
| **TC-2** | `expense.ts` & `translations.ts` | `i18n_dictionary_pollution_and_duplicate_icon` | `exp_shared_ledger` 殘留硬編碼超連結表情符號 `🔗`，與原生 `<Share2 />` 向量圖標重複碰撞 | **CONFIRMED** |
| **TC-3** | `tools-view.tsx` | `ui_brand_palette_deviation` | 開支視圖切換鈕使用冷黑 `bg-slate-900`，偏離 Tabiji 經典墨綠 `#0B3026` 品牌色階 | **CONFIRMED** |
| **TC-4** | `tools-view.tsx` | `ui_color_clash_and_foreign_token` | 分享公帳按鈕使用突兀的 `text-indigo-600` 外來色彩，破壞全頁調性統一 | **CONFIRMED** |
| **TC-5** | `tools-view.tsx` | `layout_spacing_stacking_bug` | 圖標行內設定 `mr-2` 與 `mr-1.5`，與 Button 基底 `gap-1.5` 疊加形成 14px 異常過大間距 | **CONFIRMED** |

---

## 3. In-Memory PoC 證偽實錄 (Evidence & PoC)

執行指令：
```bash
npx vitest run __tests__/expense-toggle-sentinel.test.ts
```

輸出日誌：
```text
FAIL  __tests__/expense-toggle-sentinel.test.ts
  🛡️ Security Sentinel: Expense View Toggle & Share Ledger Icon Harmony Audit
    ✕ TC-1: remaining.ts tv_list MUST NOT contain hardcoded clipboard emoji 📋
    ✕ TC-2: expense.ts & translations.ts exp_shared_ledger MUST NOT contain link emoji 🔗
    ✕ TC-3: tools-view.tsx view toggle buttons MUST use Tabiji primary #0B3026 (No generic slate-900)
    ✕ TC-4: tools-view.tsx share button MUST eliminate text-indigo-600 and adopt Tabiji brand palette
    ✕ TC-5: tools-view.tsx toggle and share icons MUST eliminate redundant mr-2 / mr-1.5 margins

Test Files  1 failed (1)
     Tests  5 failed (5)
```

---

## 4. 候選補丁與精確區塊替換規範 (Mantis Patch & Replacement Block Mappings)

### 區塊替換 1: [tools-view.tsx:843–875](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/tools-view.tsx#L843-L875)
- **目標範圍**: Line 843–875 (View Mode Toggle & Share Button)
- **現有內容 (Target)**:
```tsx
                                        <Button
                                            variant={expenseView === 'summary' ? 'default' : 'outline'}
                                            size="sm"
                                            className={cn("flex-1 h-11", expenseView === 'summary' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'dark:text-white dark:border-slate-700')}
                                            onClick={() => setExpenseView('summary')}
                                        >
                                            <PieChart className="w-4 h-4 mr-2" /> {t('total')}
                                        </Button>
                                        <Button
                                            variant={expenseView === 'daily' ? 'default' : 'outline'}
                                            size="sm"
                                            className={cn("flex-1 h-11", expenseView === 'daily' ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900' : 'dark:text-white dark:border-slate-700')}
                                            onClick={() => setExpenseView('daily')}
                                        >
                                            <List className="w-4 h-4 mr-2" /> {t('tv_list')}
                                        </Button>
                                    </div>

                                    {/* Phase 8 Share Public Ledger */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleShareLedger}
                                        disabled={isSharing || !activeTripId}
                                        className="text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 border border-transparent hover:border-indigo-100"
                                    >
                                        {isSharing
                                            ? <Loader2 className="w-4 h-4 animate-spin" />
                                            : <Share2 className="w-4 h-4" />
                                        }
                                        <span className="ml-1 font-semibold">{t('share_ledger_btn') || "分享公帳"}</span>
                                    </Button>
```
- **替換內容 (Replacement)**:
```tsx
                                        <Button
                                            variant={expenseView === 'summary' ? 'default' : 'outline'}
                                            size="sm"
                                            className={cn(
                                                "flex-1 h-11 rounded-xl font-semibold transition-all active:scale-[0.98] cursor-pointer",
                                                expenseView === 'summary'
                                                    ? "bg-[#0B3026] hover:bg-[#0B3026]/90 text-white dark:bg-[#E5EBEA] dark:hover:bg-white dark:text-[#0B3026] shadow-xs"
                                                    : "bg-white/80 dark:bg-[#1E2927]/60 text-[#1E2927] dark:text-[#E5EBEA] border border-[#0B3026]/15 dark:border-white/15 hover:bg-black/5 dark:hover:bg-white/5"
                                            )}
                                            onClick={() => setExpenseView('summary')}
                                        >
                                            <PieChart className="w-4 h-4 shrink-0" />
                                            <span>{t('total')}</span>
                                        </Button>
                                        <Button
                                            variant={expenseView === 'daily' ? 'default' : 'outline'}
                                            size="sm"
                                            className={cn(
                                                "flex-1 h-11 rounded-xl font-semibold transition-all active:scale-[0.98] cursor-pointer",
                                                expenseView === 'daily'
                                                    ? "bg-[#0B3026] hover:bg-[#0B3026]/90 text-white dark:bg-[#E5EBEA] dark:hover:bg-white dark:text-[#0B3026] shadow-xs"
                                                    : "bg-white/80 dark:bg-[#1E2927]/60 text-[#1E2927] dark:text-[#E5EBEA] border border-[#0B3026]/15 dark:border-white/15 hover:bg-black/5 dark:hover:bg-white/5"
                                            )}
                                            onClick={() => setExpenseView('daily')}
                                        >
                                            <List className="w-4 h-4 shrink-0" />
                                            <span>{t('tv_list')}</span>
                                        </Button>
                                    </div>

                                    {/* Phase 8 Share Public Ledger */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleShareLedger}
                                        disabled={isSharing || !activeTripId}
                                        className="text-[#0B3026] dark:text-[#E5EBEA] hover:bg-[#0B3026]/10 dark:hover:bg-white/10 border border-transparent font-medium rounded-xl h-11 transition-colors cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
                                    >
                                        {isSharing
                                            ? <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                                            : <Share2 className="w-4 h-4 shrink-0" />
                                        }
                                        <span>{t('share_ledger_btn') || "分享公帳"}</span>
                                    </Button>
```

---

### 區塊替換 2: 語系檔字典純淨化
- **[remaining.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/i18n/remaining.ts)**:
  - Line 241: `tv_list: "List"`
  - Line 972: `tv_list: "列表"`
- **[expense.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/i18n/expense.ts)**:
  - Line 30: `exp_shared_ledger: "Share Ledger"`
  - Line 122: `exp_shared_ledger: "分享公帳"`
- **[translations.ts](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/translations.ts)**:
  - Line 177: `exp_shared_ledger: "Share Ledger"`
  - Line 507: `exp_shared_ledger: "分享公帳"`

---

## 5. Human Gate 查核守門 (Phase 6 Handover)

依循 Security Sentinel L0 憲法：
- `@security` 已完成對抗證偽、沙盒 PoC 建立、補丁產出與精確替換映射。
- **原始碼檔案尚未更動**。
- 待人類審核核准後，方可由開發端執行變更並進行全量無降級驗證。
