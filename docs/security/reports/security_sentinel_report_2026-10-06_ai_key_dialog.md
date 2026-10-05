# Security Sentinel Empirical Audit Report: AI API Key Dialog & Overflow Defense

- **Audit Date**: 2026-10-06T00:58:00+08:00
- **Mode**: `/security-sentinel` In-Memory Sandbox Adversarial Validation (`agy.exe -p --sandbox`)
- **Target Components**: 
  - `frontend/components/ai/ai-key-dialog.tsx`
  - `frontend/components/ui/dialog.tsx`
  - `frontend/lib/security.ts`

---

## 🔬 Executive Summary

| Target ID | Vector Checked | Validator Hypothesis | Empirical Sandbox Verdict | Result Summary |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/components/ai/ai-key-dialog.tsx` | `mobile_responsive_overflow_and_key_handling` | `DialogFooter` unconstrained flex-row forces overflow under enlarged font scale; Accordion lacks `min-w-0`; Input lacks Enter key. | **CONFIRMED DEFECT** | 3 項缺陷全部證實：強制單行導致窄螢幕溢出、長字串未縮退、鍵盤無 Enter 響應。 |
| `frontend/components/ui/dialog.tsx` | `ui_overflow_defense_and_a11y` | `DialogContent` 缺少 `overflow-x-hidden`；`DialogHeader` 缺少右側避讓內距。 | **DISMISSED (WITH ARCHITECTURAL NOTE)** | `overflow-y-auto` 計算強制 `overflow-x: auto`，溢出僅限於彈窗內部滾動，未破壞父級 Document Viewport。但為防止彈窗內部左右滑動，建議局部強化。 |
| `frontend/lib/security.ts` | `client_key_encryption_and_leakage` | `user_gemini_key` XOR/Base64 與標頭注入風險。 | **DISMISSED** | `getSecureApiKey()` 嚴格透過正則過濾 `[^\x20-\x7E]` 剔除所有不可見與 CRLF 字元，徹底杜絕 HTTP Header Injection。 |

---

## 🧪 In-Memory Sandbox PoC (Unit Test)

```typescript
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AIKeyDialog } from '@/components/ai/ai-key-dialog'

describe('AIKeyDialog Responsive & Interaction PoC', () => {
  it('PoC-1: verifies DialogFooter forces flex-row without wrapping in legacy code', () => {
    const { container } = render(<AIKeyDialog open={true} onOpenChange={vi.fn()} />)
    const footer = container.querySelector('[class*="justify-between"]')
    expect(footer?.className).toContain('flex-row')
    expect(footer?.className).not.toContain('flex-col')
  })

  it('PoC-2: verifies Input currently lacks Enter key submission handler', () => {
    const onOpenChange = vi.fn()
    render(<AIKeyDialog open={true} onOpenChange={onOpenChange} />)
    const input = screen.getByPlaceholderText(/AIzaSy/i)
    fireEvent.change(input, { target: { value: 'AIzaSyValidMockKey123' } })
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })
    // In legacy code, onOpenChange is not triggered
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})
```

---

## 🛡️ Mantis Patch & Block Replacement Candidate (Human Gate)

### Candidate RFC Unified Diff (`ai-key-dialog.tsx`)

```diff
--- a/frontend/components/ai/ai-key-dialog.tsx
+++ b/frontend/components/ai/ai-key-dialog.tsx
@@ -107,7 +107,13 @@ export function AIKeyDialog({ open, onOpenChange, trigger }: AIKeyDialogProps) {
                             value={apiKey}
                             onChange={(e) => setApiKey(e.target.value)}
+                            onKeyDown={(e) => {
+                                if (e.key === 'Enter') {
+                                    e.preventDefault()
+                                    handleSaveApiKey()
+                                }
+                            }}
                             placeholder="AIzaSy**************************"
-                            className="font-mono text-sm"
+                            className="font-mono text-sm w-full"
                         />
                     </div>
@@ -118,7 +124,7 @@ export function AIKeyDialog({ open, onOpenChange, trigger }: AIKeyDialogProps) {
                             <AccordionContent className="text-xs text-slate-500 dark:text-slate-400 space-y-3 pb-4">
                                 <div className="flex gap-3">
-                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0">1</div>
-                                    <div>
-                                        {zh ? '前往' : 'Go to'} <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 underline font-bold inline-flex items-center">Google AI Studio <ExternalLink className="w-3 h-3 ml-0.5" /></a> {zh ? '並登入 Google 帳號。' : 'and sign in with Google.'}
+                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0 mt-0.5">1</div>
+                                    <div className="min-w-0 flex-1 wrap-break-word">
+                                        {zh ? '前往' : 'Go to'} <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noreferrer" className="text-blue-600 dark:text-blue-400 underline font-bold inline-flex items-center break-all">Google AI Studio <ExternalLink className="w-3 h-3 ml-0.5 shrink-0" /></a> {zh ? '並登入 Google 帳號。' : 'and sign in with Google.'}
                                     </div>
                                 </div>
                                 <div className="flex gap-3">
-                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0">2</div>
-                                    <div>{zh ? '點擊左側選單的' : 'Click'} <b>Get API key</b>{zh ? '。' : ' in the left menu.'}</div>
+                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0 mt-0.5">2</div>
+                                    <div className="min-w-0 flex-1 wrap-break-word">{zh ? '點擊左側選單的' : 'Click'} <b>Get API key</b>{zh ? '。' : ' in the left menu.'}</div>
                                 </div>
                                 <div className="flex gap-3">
-                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0">3</div>
-                                    <div>{zh ? '點擊' : 'Click'} <b>Create API key</b>{zh ? ' 建立新版授權金鑰 (Auth key)，複製' : ' to create an Auth key, copy the code starting with'} <code>AIza...</code> {zh ? '開頭的代碼。' : '.'}</div>
+                                    <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-200 font-bold shrink-0 mt-0.5">3</div>
+                                    <div className="min-w-0 flex-1 wrap-break-word">{zh ? '點擊' : 'Click'} <b>Create API key</b>{zh ? ' 建立新版授權金鑰 (Auth key)，複製' : ' to create an Auth key, copy the code starting with'} <code>AIza...</code> {zh ? '開頭的代碼。' : '.'}</div>
                                 </div>
@@ -141,23 +147,26 @@ export function AIKeyDialog({ open, onOpenChange, trigger }: AIKeyDialogProps) {
-                <DialogFooter className="flex flex-row justify-between sm:justify-between gap-2">
-                    <Button variant="outline" onClick={handleClearApiKey} className="text-slate-400 hover:text-red-500">
-                        {zh ? '清除' : 'Clear'}
-                    </Button>
-                    <div className="flex items-center gap-2">
+                <DialogFooter className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 pt-2">
+                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto order-1 sm:order-2">
                         <Button 
                             type="button" 
                             variant="secondary" 
                             onClick={handleTestApiKey} 
                             disabled={isTestingKey || !apiKey.trim()}
-                            className="border border-slate-200 hover:bg-slate-100 dark:border-slate-700"
+                            className="w-full sm:w-auto border border-slate-200 hover:bg-slate-100 dark:border-slate-700 h-10 px-4"
                         >
                             {isTestingKey ? (
-                                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> {t('profile_testing_api_key')}</>
+                                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin shrink-0" /> <span className="truncate">{t('profile_testing_api_key')}</span></>
                             ) : (
-                                <><Sparkles className="w-4 h-4 mr-1.5 text-amber-500" /> {t('profile_test_api_key')}</>
+                                <><Sparkles className="w-4 h-4 mr-1.5 text-amber-500 shrink-0" /> <span className="truncate">{t('profile_test_api_key')}</span></>
                             )}
                         </Button>
-                        <Button onClick={handleSaveApiKey} className="bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200">
-                            <Key className="w-4 h-4 mr-2" /> {zh ? '儲存設定' : 'Save'}
+                        <Button 
+                            type="button"
+                            onClick={handleSaveApiKey} 
+                            className="w-full sm:w-auto bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200 h-10 px-4"
+                        >
+                            <Key className="w-4 h-4 mr-2 shrink-0" /> <span className="truncate">{zh ? '儲存設定' : 'Save'}</span>
                         </Button>
                     </div>
+                    <Button 
+                        type="button"
+                        variant="ghost" 
+                        onClick={handleClearApiKey} 
+                        className="w-full sm:w-auto text-slate-400 hover:text-red-500 hover:bg-red-50/50 dark:hover:bg-red-950/20 h-9 order-2 sm:order-1"
+                    >
+                        {zh ? '清除金鑰' : 'Clear Key'}
+                    </Button>
                 </DialogFooter>
```

### Exact Block Replacements

#### Block 1: `frontend/components/ui/dialog.tsx`
- **Target File**: `frontend/components/ui/dialog.tsx`
- **Target Content**:
```tsx
          "bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-[110] grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-6 shadow-lg duration-200 outline-none sm:max-w-lg max-h-[90vh] overflow-y-auto",
```
- **Replacement Content**:
```tsx
          "bg-background data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-[110] grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-4 sm:p-6 shadow-lg duration-200 outline-none sm:max-w-lg max-h-[90vh] overflow-y-auto overflow-x-hidden",
```

#### Block 2: `frontend/components/ai/ai-key-dialog.tsx` (Footer)
- **Target File**: `frontend/components/ai/ai-key-dialog.tsx`
- **Target Content**:
```tsx
                <DialogFooter className="flex flex-row justify-between sm:justify-between gap-2">
                    <Button variant="outline" onClick={handleClearApiKey} className="text-slate-400 hover:text-red-500">
                        {zh ? '清除' : 'Clear'}
                    </Button>
                    <div className="flex items-center gap-2">
                        <Button 
                            type="button" 
                            variant="secondary" 
                            onClick={handleTestApiKey} 
                            disabled={isTestingKey || !apiKey.trim()}
                            className="border border-slate-200 hover:bg-slate-100 dark:border-slate-700"
                        >
                            {isTestingKey ? (
                                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> {t('profile_testing_api_key')}</>
                            ) : (
                                <><Sparkles className="w-4 h-4 mr-1.5 text-amber-500" /> {t('profile_test_api_key')}</>
                            )}
                        </Button>
                        <Button onClick={handleSaveApiKey} className="bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200">
                            <Key className="w-4 h-4 mr-2" /> {zh ? '儲存設定' : 'Save'}
                        </Button>
                    </div>
                </DialogFooter>
```
- **Replacement Content**:
```tsx
                <DialogFooter className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 pt-2">
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto order-1 sm:order-2">
                        <Button 
                            type="button" 
                            variant="secondary" 
                            onClick={handleTestApiKey} 
                            disabled={isTestingKey || !apiKey.trim()}
                            className="w-full sm:w-auto border border-slate-200 hover:bg-slate-100 dark:border-slate-700 h-10 px-4"
                        >
                            {isTestingKey ? (
                                <><Loader2 className="w-4 h-4 mr-1.5 animate-spin shrink-0" /> <span className="truncate">{t('profile_testing_api_key')}</span></>
                            ) : (
                                <><Sparkles className="w-4 h-4 mr-1.5 text-amber-500 shrink-0" /> <span className="truncate">{t('profile_test_api_key')}</span></>
                            )}
                        </Button>
                        <Button 
                            type="button"
                            onClick={handleSaveApiKey} 
                            className="w-full sm:w-auto bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200 h-10 px-4"
                        >
                            <Key className="w-4 h-4 mr-2 shrink-0" /> <span className="truncate">{zh ? '儲存設定' : 'Save'}</span>
                        </Button>
                    </div>
                    <Button 
                        type="button"
                        variant="ghost" 
                        onClick={handleClearApiKey} 
                        className="w-full sm:w-auto text-slate-400 hover:text-red-500 hover:bg-red-50/50 dark:hover:bg-red-950/20 h-9 order-2 sm:order-1"
                    >
                        {zh ? '清除金鑰' : 'Clear Key'}
                    </Button>
                </DialogFooter>
```
