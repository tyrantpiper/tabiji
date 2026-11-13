import React from "react"
import Link from "next/link"
import { OfficialHeader } from "@/components/official/OfficialHeader"
import { OfficialFooter } from "@/components/official/OfficialFooter"
import { OfficialBackLink } from "@/components/official/OfficialBackLink"
import { ShieldCheck, Lock, UserCheck, Database } from "lucide-react"

export const metadata = {
  title: "隱私權政策 (Privacy Policy) | Tabiji 官方網站",
  description: "Tabiji 旅路隱私權政策。嚴格遵循 GDPR 6 大當事人權利、台灣個人資料保護法、SCC 跨國傳輸防護與零第三方廣告追蹤承諾。",
}

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen flex flex-col justify-between">
      <OfficialHeader />

      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 sm:pt-36 pb-16">
        {/* Back Link */}
        <div className="mb-8">
          <OfficialBackLink
            href="/official"
            aria-label="返回官方網站首頁"
            className="inline-flex items-center gap-2 min-h-11 px-3 py-2 rounded-full text-sm font-medium text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 hover:bg-stone-100 dark:hover:bg-stone-800/50 transition-all duration-160 ease-out active:scale-[0.97]"
          />
        </div>

        {/* Title Header */}
        <div className="border-b border-[#0B3026]/10 dark:border-white/10 pb-8 mb-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-[#0B3026]/10 dark:bg-emerald-500/10 text-[#0B3026] dark:text-emerald-400 mb-4">
            <Lock className="w-3.5 h-3.5" />
            <span>個人資料保護與隱私權承諾</span>
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50">
            隱私權政策 (Privacy Policy)
          </h1>
          <p className="mt-3 text-sm text-stone-500 dark:text-stone-400">
            生效日期：2026 年 11 月 1 日 · 最新修訂版本 v2.4
          </p>
        </div>

        {/* Local-First Architecture Callout */}
        <div className="rounded-2xl p-6 mb-10 bg-emerald-500/10 border border-emerald-500/20 text-stone-800 dark:text-stone-200">
          <div className="flex items-start gap-3.5">
            <ShieldCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
            <div className="space-y-2 text-sm leading-relaxed">
              <p className="font-semibold text-stone-900 dark:text-stone-100">
                Local-First 在地優先與零廣告追蹤聲明 (Zero-Tracking Policy)
              </p>
              <p>
                Tabiji 平台全面採用<strong>客戶端在地優先架構（Local-First Architecture）</strong>。您的行程與記帳資料預設儲存於您自身的設備瀏覽器內部（IndexedDB），未經您的主動操作，絕不會上傳或同步。<strong>我們絕不加載 Facebook Pixel、TikTok Tracker 等商業廣告追蹤代碼，亦絕不出售、出租或交換您的個人資料予任何第三方廣告經紀商。</strong>
              </p>
            </div>
          </div>
        </div>

        {/* Policy Sections */}
        <div className="space-y-10 text-stone-700 dark:text-stone-300 leading-relaxed text-sm sm:text-base">
          {/* Section 1: GDPR 6 Data Subject Rights */}
          <section className="space-y-4">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">1.</span> 歐盟 GDPR 六大資料當事人權利 (GDPR Data Subject Rights)
            </h2>
            <p>
              若您為歐洲經濟區（EEA）或英國之居民，依照《通用資料保護條例》（GDPR Regulation (EU) 2016/679），您對個人資料享有以下法定權利：
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <UserCheck className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  訪問權 (Right of Access - Art. 15)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  您有權向我們請求確認您的個人資料是否正在被處理，並取得該個人資料之副本。
                </p>
              </div>

              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <UserCheck className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  更正權 (Right to Rectification - Art. 16)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  您有權隨時在應用程式介面中更正不正確之個人暱稱、景點標籤或行程明細。
                </p>
              </div>

              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <UserCheck className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  刪除權 / 被遺忘權 (Right to Erasure - Art. 17)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  您有權透過「清除本機儲存」或向我們申請徹底抹除伺服器協同房間內之所有暫存資料。
                </p>
              </div>

              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <UserCheck className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  限制處理權 (Right to Restriction - Art. 18)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  在符合法律要件之情況下，您有權要求我們暫停對您個人資料之進一步處理。
                </p>
              </div>

              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <Database className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  資料可攜權 (Right to Data Portability - Art. 20)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  您有權以結構化、通用且機器可讀格式（如 JSON / 檔案匯出）接收您所提供之行程資料。
                </p>
              </div>

              <div className="p-4 rounded-xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10 space-y-1">
                <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm flex items-center gap-1.5">
                  <Lock className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                  反對權 (Right to Object - Art. 21)
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400">
                  您有權基於自身特定情況隨時反對我們處理您的個人資料。
                </p>
              </div>
            </div>
          </section>

          {/* Section 2: Taiwan Personal Data Protection Act */}
          <section className="space-y-4 p-5 rounded-2xl bg-[#0B3026]/5 dark:bg-stone-900/60 border border-[#0B3026]/15 dark:border-white/10">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">2.</span> 台灣個人資料保護法合規事項 (Taiwan PDPA Compliance)
            </h2>
            <p>
              本平台嚴格遵守中華民國《個人資料保護法》（簡稱個資法）相關法令規範。依個資法第八條規定，明確告知下列事項：
            </p>
            <div className="space-y-3 text-sm">
              <div>
                <h4 className="font-semibold text-stone-900 dark:text-stone-100">
                  (1) 蒐集之法定特定目的：
                </h4>
                <ul className="list-disc list-inside pl-2 space-y-1 text-stone-700 dark:text-stone-300">
                  <li><strong>090 資訊(通訊)服務</strong>：提供即時協同旅行規劃、離線地圖導引與自癒同步。</li>
                  <li><strong>148 網路購物及其他電子商務服務</strong>：處理增值訂閱或第三方票券比價導購轉址。</li>
                  <li><strong>157 調查、統計與研究分析</strong>：進行系統除錯日誌分析及無識別特徵之聚合效能優化。</li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold text-stone-900 dark:text-stone-100">
                  (2) 蒐集之個人資料類別：
                </h4>
                <ul className="list-disc list-inside pl-2 space-y-1 text-stone-700 dark:text-stone-300">
                  <li><strong>C001 辨識個人者</strong>：旅行者自訂暱稱、引繼復原碼。</li>
                  <li><strong>C035 休閒活動及興趣</strong>：使用者自訂之旅行景點清單、行程日期與多幣別記帳明細。</li>
                </ul>
              </div>

              <div>
                <h4 className="font-semibold text-stone-900 dark:text-stone-100">
                  (3) 當事人依個資法第三條得行使之權利：
                </h4>
                <p className="text-stone-700 dark:text-stone-300">
                  您得就您留存於本平台之個人資料行使查詢、閱覽、製給複製本、補充或更正、停止電腦處理利用及請求刪除之權利。行使方式可透過平台官方設定功能或聯繫個人資料保護專用信箱。
                </p>
              </div>
            </div>
          </section>

          {/* Section 3: Cross-Border Data Transfer & SCC */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">3.</span> 跨國資料傳輸保護規範 (Cross-Border Data Transfer & SCC)
            </h2>
            <p>
              為提供全球高可用之低延遲邊緣服務，本平台採用全球分散式邊緣架構（例如 Cloudflare Edge 網路與 Supabase 安全雲端節點）。
            </p>
            <p>
              當涉及歐盟或台灣境外之跨境資料傳輸時，我們依據歐盟執委會認可之<strong>標準合約條款（Standard Contractual Clauses - SCCs）</strong>建立傳輸安全防護基準，並確保全端通訊全程強制使用 <strong>TLS 1.3 現代傳輸加密協定</strong>，保障跨國傳輸時資料之完整性與機密性。
            </p>
          </section>

          {/* Section 4: Local-First & Zero-Tracking */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">4.</span> 在地儲存優先與零第三方廣告追蹤 (Zero-Tracking Architecture)
            </h2>
            <p>
              與傳統雲端旅遊工具不同，Tabiji 實施「本地優先」架構理念。所有行程標籤、景點標註與多幣別平攤計算，均直接由使用者瀏覽器本機的 IndexedDB 與 SWR 記憶體快取處理。
            </p>
            <p>
              我們向使用者鄭重承諾：<strong>本平台絕不置入侵入式跨站廣告追蹤標籤、第三方廣告 SDK 或個人輪廓畫像引擎</strong>。您的旅遊足跡是您的私密生活資產，絕非廣告商之商品。
            </p>
          </section>

          {/* Section 5: Cookies & Local Storage Transparency */}
          <section className="space-y-3 p-5 rounded-2xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">5.</span> 本地儲存與 Cookie 透明清單 (Storage Transparency)
            </h2>
            <p className="text-sm">
              本平台不使用任何廣告行銷 Cookie，僅在本地儲存技術運作所絕對必需之項目：
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs sm:text-sm border-collapse">
                <thead>
                  <tr className="border-b border-stone-300 dark:border-stone-700">
                    <th className="py-2.5 pr-4 font-semibold text-stone-900 dark:text-stone-100">鍵名 (Key)</th>
                    <th className="py-2.5 pr-4 font-semibold text-stone-900 dark:text-stone-100">技術類型</th>
                    <th className="py-2.5 font-semibold text-stone-900 dark:text-stone-100">功能與用途說明</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-200 dark:divide-stone-800">
                  <tr>
                    <td className="py-2.5 pr-4 font-mono text-xs">app_language</td>
                    <td className="py-2.5 pr-4">LocalStorage / Cookie</td>
                    <td className="py-2.5">記錄介面語系偏好 (zh-TW / en)</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pr-4 font-mono text-xs">dark_mode</td>
                    <td className="py-2.5 pr-4">LocalStorage</td>
                    <td className="py-2.5">記憶使用者的深色 / 淺色外觀偏好</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pr-4 font-mono text-xs">app_font_scale</td>
                    <td className="py-2.5 pr-4">LocalStorage</td>
                    <td className="py-2.5">無障礙字級倍率偏好 (100% ~ 130%)</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pr-4 font-mono text-xs">user_gemini_key</td>
                    <td className="py-2.5 pr-4">LocalStorage</td>
                    <td className="py-2.5">使用者自備 AI 金鑰之本機混淆封裝 (___SECURE_V1___)</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pr-4 font-mono text-xs">idb-keyval</td>
                    <td className="py-2.5 pr-4">IndexedDB</td>
                    <td className="py-2.5">極限離線秒開之行程快照二進位庫</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {/* Bottom Back Button */}
        <div className="mt-16 pt-8 border-t border-[#0B3026]/10 dark:border-white/10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <OfficialBackLink
            href="/official"
            aria-label="返回官方首頁"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 min-h-11 px-6 py-2.5 rounded-full text-sm font-semibold text-white bg-[#0B3026] hover:bg-[#164E40] dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:text-stone-950 transition-all duration-160 ease-out active:scale-[0.97]"
          />
          <Link
            href="/official/terms"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 min-h-11 px-6 py-2.5 rounded-full text-sm font-medium text-stone-700 dark:text-stone-300 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors"
          >
            <span>閱讀服務條款 (Terms of Service)</span>
          </Link>
        </div>
      </main>

      <OfficialFooter />
    </div>
  )
}
