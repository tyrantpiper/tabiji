import React from "react"
import Link from "next/link"
import { OfficialHeader } from "@/components/official/OfficialHeader"
import { OfficialFooter } from "@/components/official/OfficialFooter"
import { OfficialBackLink } from "@/components/official/OfficialBackLink"
import { ShieldAlert, Scale, FileText } from "lucide-react"

export const metadata = {
  title: "服務條款 (Terms of Service) | Tabiji 官方網站",
  description: "Tabiji 旅路服務條款與使用者協議。明定 100 美元責任上限、台北約束性仲裁、放棄集體訴訟及依現狀提供規範。",
}

export default function TermsOfServicePage() {
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
            <Scale className="w-3.5 h-3.5" />
            <span>約束性法律協議</span>
          </div>
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50">
            服務條款 (Terms of Service)
          </h1>
          <p className="mt-3 text-sm text-stone-500 dark:text-stone-400">
            生效日期：2026 年 11 月 1 日 · 最新修訂版本 v2.4
          </p>
        </div>

        {/* Key Legal Notice Callout */}
        <div className="rounded-2xl p-6 mb-10 bg-amber-500/10 border border-amber-500/20 text-stone-800 dark:text-stone-200">
          <div className="flex items-start gap-3.5">
            <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <div className="space-y-2 text-sm leading-relaxed">
              <p className="font-semibold text-stone-900 dark:text-stone-100">
                重要法律聲明摘要
              </p>
              <p>
                請仔細閱讀本服務條款。本條款包含<strong>100 美元損害賠償責任上限</strong>、提交予<strong>中華民國仲裁協會（台北）之約束性仲裁條款</strong>、<strong>放棄集體訴訟權利</strong>以及<strong>依中華民國（臺灣）法律為準據法</strong>之規定。透過訪問或使用 Tabiji 旅路平台，即代表您同意受本條款之法律拘束。
              </p>
            </div>
          </div>
        </div>

        {/* Terms Sections */}
        <div className="space-y-10 text-stone-700 dark:text-stone-300 leading-relaxed text-sm sm:text-base">
          {/* Section 1 */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">1.</span> 服務範圍與依現狀提供 (As-Is / As-Available)
            </h2>
            <p>
              Tabiji（以下簡稱「本平台」或「我們」）為輔助全球旅客進行多目的地行程協調、空間航線規劃與離線帳務管理之獨立軟體工具。所有由人工智慧（AI）生成之推薦內容、地理路線插值、即時天氣預報、大眾運輸轉乘及外幣估算資訊，均僅供個人行程規劃之參考。
            </p>
            <p>
              本服務係按「<strong>現狀 (AS IS)</strong>」及「<strong>可提供性 (AS AVAILABLE)</strong>」基準提供。在適用法律允許的最大範圍內，本平台明確排除任何明示、默示或法定之保證，包含但不限於適銷性、特定用途適用性、無權利侵害、正確性或不中斷運行之保證。
            </p>
          </section>

          {/* Section 2: Liability Cap */}
          <section className="space-y-3 p-5 rounded-2xl bg-[#0B3026]/5 dark:bg-stone-900/60 border border-[#0B3026]/15 dark:border-white/10">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">2.</span> 責任上限條款 ($100 USD Liability Cap)
            </h2>
            <p className="font-medium text-stone-900 dark:text-stone-100">
              在適用法律允許的最大範圍內，Tabiji、其創辦人、核心開發人員、貢獻者或關聯方，就使用者因使用或無法使用本服務所引起或與之相關之任何合約、侵權（包含過失）、嚴格責任或其他法律主張，其全部累計損害賠償責任，均以以下兩者中較低者為最高上限：
            </p>
            <ul className="list-disc list-inside space-y-1.5 pl-2 text-stone-800 dark:text-stone-200">
              <li><strong>(a) 100 美元整 (USD $100.00)</strong>；或</li>
              <li><strong>(b) 使用者在引發索賠事件前十二 (12) 個月內向 Tabiji 實際支付之服務費用總額</strong>。</li>
            </ul>
            <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 pt-2 border-t border-[#0B3026]/10 dark:border-white/10">
              在任何情況下，Tabiji 均不對任何間接性、附隨性、衍生性、懲罰性、特殊性損害、預期利潤損失、航班延誤、住宿取消、商譽損害或行程中斷負擔賠償責任，縱使本平台已被告知該損害發生的可能性亦同。
            </p>
          </section>

          {/* Section 3: Taipei Binding Arbitration */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">3.</span> 台北約束性仲裁 (Taipei Binding Arbitration)
            </h2>
            <p>
              因本服務條款或因本服務之使用所產生、相關或與之有牽涉的任何爭議、爭辯、分歧或索賠，包括其成立、存在、有效性、解釋、履行、違反或終止，雙方應首先秉持誠信原則進行友好協商。若自協商請求提出後三十 (30) 日內未能達成和解，該爭議均應提交予<strong>中華民國仲裁協會 (The Chinese Arbitration Association, Taipei)</strong>。
            </p>
            <p>
              仲裁應依該會現行有效之仲裁規則，在<strong>台灣台北市</strong>以具法律拘束力之仲裁方式進行最終裁決。仲裁程序之準據語言為<strong>繁體中文</strong>。仲裁判斷為終局裁決，對雙方均具完全之執行力與拘束力，任何具備管轄權之法院均得據以登錄並強制執行。
            </p>
          </section>

          {/* Section 4: Class Action Waiver */}
          <section className="space-y-3 p-5 rounded-2xl bg-stone-100 dark:bg-stone-900/60 border border-stone-200 dark:border-white/10">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">4.</span> 放棄集體訴訟權利 (Class Action Waiver)
            </h2>
            <p className="font-medium text-stone-900 dark:text-stone-100">
              所有爭議之解決僅得以使用者之個人身分單獨進行。使用者明確、知情且不可撤回地放棄以原告或集團成員身分，在任何預期的集體訴訟、代表訴訟、合併訴訟或私人檢察總長訴訟（Private Attorney General Action）中提出索賠或加入訴訟的權利。
            </p>
            <p className="text-sm">
              除非雙方另有書面協議，仲裁員無權合併多名使用者之索賠，亦不得主持任何形式的代表或集體審理程序。
            </p>
          </section>

          {/* Section 5: Governing Law */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">5.</span> 準據法與管轄管轄權 (Governing Law)
            </h2>
            <p>
              本服務條款之解釋、有效性、履行及爭議解決，均應受<strong>中華民國（臺灣）法律</strong>管轄並依其解釋，明確排除其涉外民事法律適用法（衝突法規則）以及《聯合國國際貨物銷售合同公約》(CISG) 之適用。
            </p>
          </section>

          {/* Section 6: Non-Custodial Account */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">6.</span> 客戶端優先架構與引繼碼遺失自負責任
            </h2>
            <p>
              Tabiji 奉行本機儲存優先（Local-First）架構，使用者的行程資料、多幣別支出項目與個人金鑰均以非託管形式優先存儲於使用者個人裝置（IndexedDB）。本平台提供之引繼碼（<code className="text-xs bg-stone-200 dark:bg-stone-800 px-1.5 py-0.5 rounded font-mono">tbj_rec_*</code> 或安全 UUID）為復原或遷移行程之唯一離線憑證。
            </p>
            <p>
              使用者應妥善備份其引繼碼。若因使用者遺失引繼碼、清除瀏覽器快取、更換裝置或裝置損毀而導致行程資料遺失，Tabiji 不承擔任何資料復原義務或損害賠償責任。
            </p>
          </section>

          {/* Section 7: Severability */}
          <section className="space-y-3">
            <h2 className="text-xl sm:text-2xl font-bold text-stone-900 dark:text-stone-100 flex items-center gap-2">
              <span className="text-[#0B3026] dark:text-emerald-400">7.</span> 條款可分割性與修訂 (Severability)
            </h2>
            <p>
              若本條款之任何約定被管轄仲裁庭或法院認定為無效、違法或不可執行，該約定應在最小必要範圍內予以限制或排除，以維持最大之適法意圖，而其餘約定之有效性、合法性與可執行性均不受任何影響。
            </p>
            <p>
              我們保留隨時更新或修訂本服務條款之權利。最新修訂之版本將公布於官方總站，重大變更將於頁面顯著位置提供通知。
            </p>
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
            href="/official/privacy"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 min-h-11 px-6 py-2.5 rounded-full text-sm font-medium text-stone-700 dark:text-stone-300 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors"
          >
            <span>閱讀隱私權政策 (Privacy Policy)</span>
            <FileText className="w-4 h-4" />
          </Link>
        </div>
      </main>

      <OfficialFooter />
    </div>
  )
}
