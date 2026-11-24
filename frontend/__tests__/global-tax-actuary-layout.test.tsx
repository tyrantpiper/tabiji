import React from "react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import fs from "node:fs"
import path from "node:path"

let mockLang: "zh" | "en" = "zh"

vi.mock("@/lib/LanguageContext", () => ({
  useLanguage: () => ({ lang: mockLang, t: (k: string) => k }),
}))

vi.mock("@/lib/hooks", () => ({
  useHaptic: () => ({
    tap: vi.fn(),
    selection: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
  }),
}))

vi.mock("@/lib/currency", () => ({
  getExchangeRate: vi.fn(async (currency: string) => {
    if (currency === "JPY") return 0.22
    if (currency === "KRW") return 0.024
    if (currency === "TWD") return 1.0
    return 32.0
  }),
}))

import { GlobalTaxActuary } from "@/components/tools/GlobalTaxActuary"

describe("GlobalTaxActuary Bento Layout & Safety-Net Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLang = "zh"
  })

  it("renders full-width 2-column Price Type toggle, independent FX bar, 2-column Bento KPIs, and updates on toggle", async () => {
    render(<GlobalTaxActuary defaultCurrency="JPY" />)

    await waitFor(() => {
      expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.22")
    })

    const priceTypeGroup = screen.getByRole("group", { name: "標價型態" })
    expect(priceTypeGroup.className).toContain("grid-cols-2")
    expect(priceTypeGroup.className).toContain("w-full")

    const inclBtn = screen.getByRole("button", { name: /含稅/ })
    const exclBtn = screen.getByRole("button", { name: /未稅/ })
    expect(inclBtn.getAttribute("aria-pressed")).toBe("true")
    expect(exclBtn.getAttribute("aria-pressed")).toBe("false")

    // Default 10,000 JPY tax-inclusive @ 10% -> base 9,090.91, tax 909.09
    expect(screen.getByText("未稅本金")).toBeDefined()
    expect(screen.getByText("預估稅金 (10%)")).toBeDefined()
    expect(screen.getByText("9,090.91")).toBeDefined()
    expect(screen.getByText("909.09")).toBeDefined()

    // Toggle to tax-exclusive -> base 10,000, tax 1,000
    fireEvent.click(exclBtn)
    expect(exclBtn.getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByText("10,000")).toBeDefined()
    expect(screen.getByText("1,000")).toBeDefined()
  })

  it("safely edits inline FX rate without mid-keystroke 1.0 corruption and supports Escape cancel", async () => {
    render(<GlobalTaxActuary defaultCurrency="JPY" />)

    await waitFor(() => {
      expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.22")
    })

    // Open inline editor (must be text+decimal, not native number with spinners)
    fireEvent.click(screen.getByTitle("點擊自訂/覆寫匯率"))
    const rateInput = screen.getByLabelText("自訂匯率") as HTMLInputElement
    expect(rateInput.type).toBe("text")
    expect(rateInput.getAttribute("inputmode")).toBe("decimal")
    expect(rateInput.value).toBe("0.22")

    // Clearing input mid-keystroke must NOT immediately overwrite with 1.0
    fireEvent.change(rateInput, { target: { value: "" } })
    expect(rateInput.value).toBe("")

    // Typing a different valid rate ("0.99") and pressing Escape (even followed by blur) MUST cancel & preserve 0.22
    fireEvent.change(rateInput, { target: { value: "0.99" } })
    expect(rateInput.value).toBe("0.99")
    fireEvent.keyDown(rateInput, { key: "Escape" })
    fireEvent.blur(rateInput)
    expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.22")

    // Open again, enter comma-decimal custom rate "0,25e" -> sanitized to "0.25" and commit via Enter
    fireEvent.click(screen.getByTitle("點擊自訂/覆寫匯率"))
    const rateInput2 = screen.getByLabelText("自訂匯率") as HTMLInputElement
    fireEvent.change(rateInput2, { target: { value: "0,25e" } })
    expect(rateInput2.value).toBe("0.25")
    fireEvent.keyDown(rateInput2, { key: "Enter" })
    expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.25")

    // Invalid <= 0 value on blur keeps previous valid 0.25
    fireEvent.click(screen.getByTitle("點擊自訂/覆寫匯率"))
    const rateInput3 = screen.getByLabelText("自訂匯率") as HTMLInputElement
    fireEvent.change(rateInput3, { target: { value: "0" } })
    fireEvent.blur(rateInput3)
    expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.25")
  })

  it("renders anti-truncation double-line expense CTA for large KRW figures and preserves onAddExpense payload", async () => {
    const onAddExpense = vi.fn()
    render(<GlobalTaxActuary defaultCurrency="KRW" onAddExpense={onAddExpense} />)

    await waitFor(() => {
      expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.024")
    })

    const amountInput = screen.getByLabelText("輸入 KRW 標價金額")
    fireEvent.change(amountInput, { target: { value: "1500000" } })

    const ctaBtn = screen.getByRole("button", { name: /一鍵轉入這趟行程記帳/ })
    expect(ctaBtn.className).toContain("whitespace-normal")
    expect(ctaBtn.className).toContain("h-auto")
    expect(ctaBtn.className).toContain("min-h-13")
    expect(ctaBtn.className).toContain("flex-col")
    expect(ctaBtn.textContent).toContain("KRW ≈ NT$")

    fireEvent.click(ctaBtn)
    expect(onAddExpense).toHaveBeenCalledTimes(1)
    expect(onAddExpense).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "韓國 購物 (含稅)",
        currency: "KRW",
        payment_method: "Cash",
      })
    )
    expect(onAddExpense.mock.calls[0][0].amount).toBeGreaterThan(1000000)

    // Empty / 0 amount cleanly hides CTA without NaN
    fireEvent.change(amountInput, { target: { value: "" } })
    expect(screen.queryByRole("button", { name: /一鍵轉入這趟行程記帳/ })).toBeNull()
    expect(document.body.textContent).not.toContain("NaN")
  })

  it("enforces 44px (h-11) calculator keypad touch targets and supports tally tape workflow", async () => {
    render(<GlobalTaxActuary defaultCurrency="JPY" />)

    await waitFor(() => {
      expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.22")
    })

    fireEvent.click(screen.getByRole("button", { name: "計算機" }))

    const key7 = screen.getByRole("button", { name: "7" })
    const key0 = screen.getByRole("button", { name: "0" })
    const addTapeBtn = screen.getByRole("button", { name: /加入暫存紙帶/ })
    expect(key7.className).toContain("h-11")
    expect(key0.className).toContain("h-11")
    expect(addTapeBtn.className).toContain("min-h-11")

    // Tap 7, 0, 0 -> Add to Tape -> tapeTotal drives master amount
    fireEvent.click(key7)
    fireEvent.click(key0)
    fireEvent.click(key0)
    fireEvent.click(addTapeBtn)

    expect(screen.getByText(/購物暫存紙帶明細 \(1 筆\)/)).toBeDefined()
    expect(screen.getByText(/紙帶鎖定累計中 \(1 項\)/)).toBeDefined()

    // Clear tape cleanly restores direct input
    fireEvent.click(screen.getByRole("button", { name: /清空紙帶/ }))
    expect(screen.queryByText(/購物暫存紙帶明細/)).toBeNull()
  })

  it("renders complete EN bilingual parity with zero hardcoded Chinese across main view, cards, calculator, and rule dialog", async () => {
    mockLang = "en"
    const onAddExpense = vi.fn()
    const { container } = render(
      <GlobalTaxActuary
        defaultCurrency="TWD"
        cards={[
          { id: "c1", name: "JCB Rose", rewardRate: 5.0, rewardLimit: 1000 },
          { id: "c2", name: "FlyGo Card", rewardRate: 3.5 },
        ]}
        onAddExpense={onAddExpense}
      />
    )

    await waitFor(() => {
      expect(screen.getByTitle("Click to edit rate").textContent).toContain("1")
    })

    // Raise amount high enough to trigger 2-card split strategy
    const amountInput = screen.getByLabelText("Sticker price in TWD")
    fireEvent.change(amountInput, { target: { value: "40000" } })

    // Open calculator in EN mode
    fireEvent.click(screen.getByRole("button", { name: "Calc" }))

    // Zero CJK characters anywhere in the rendered Actuary tree (even for TW static taxLabels!)
    expect(container.textContent).not.toMatch(/[\u4e00-\u9fff]/)
    expect(screen.getByText("Tax-Excl. Base")).toBeDefined()
    expect(screen.getByText("Live FX")).toBeDefined()
    expect(screen.getByText("Overseas Card Net Cost")).toBeDefined()
    expect(screen.getByRole("button", { name: /Record in Trip Expenses/ })).toBeDefined()

    // Open Customs Rules Info dialog and verify EN parity + high-contrast dark close button + clean IEEE-754 custom VAT display
    fireEvent.click(screen.getByRole("button", { name: /Customs Rules Info/ }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog.textContent).not.toMatch(/[\u4e00-\u9fff]/)
    expect(dialog.textContent).toContain("Taiwan Customs Tax-Free Rules")

    const customVatInput = screen.getByLabelText("Custom VAT (%)") as HTMLInputElement
    fireEvent.change(customVatInput, { target: { value: "14" } })
    expect(customVatInput.value).toBe("14")

    const closeBtns = screen.getAllByRole("button", { name: "Close" })
    const footerCloseBtn = closeBtns.find((btn) => btn.textContent?.trim() === "Close")
    expect(footerCloseBtn?.className).toContain("dark:bg-slate-100")
    expect(footerCloseBtn?.className).toContain("dark:text-slate-900")
  })

  it("never displays contradictory '未達門檻 (100%)' near threshold, hides progress bar when custom VAT is 0%, and uses flex layout for calculator result", async () => {
    render(<GlobalTaxActuary defaultCurrency="JPY" />)

    await waitFor(() => {
      expect(screen.getByTitle("點擊自訂/覆寫匯率").textContent).toContain("0.22")
    })

    // 5499 JPY tax-inclusive @ 10% -> base 4999.09 < 5000 (shortfall 0.91 JPY)
    const amountInput = screen.getByLabelText("輸入 JPY 標價金額")
    fireEvent.change(amountInput, { target: { value: "5499" } })
    expect(screen.getByText("未達門檻 (99%)")).toBeDefined()
    expect(screen.queryByText("未達門檻 (100%)")).toBeNull()

    // Open calculator and verify long expression uses Flex container (not hardcoded pr-20)
    fireEvent.click(screen.getByRole("button", { name: "計算機" }))
    const exprInput = screen.getByPlaceholderText(/1980\*3/) as HTMLInputElement
    expect(exprInput.className).not.toContain("pr-20")
    fireEvent.change(exprInput, { target: { value: "1500000.25+500000.5" } })
    expect(screen.getByText("= 2,000,000.75")).toBeDefined()

    // Setting Custom VAT = 0% switches status to NO_TAX_FREE and hides progress bar
    fireEvent.click(screen.getByRole("button", { name: /海關規則依據/ }))
    const vatInput = await screen.findByLabelText("自訂稅率 (%)")
    fireEvent.change(vatInput, { target: { value: "0" } })
    expect(screen.getByText("無觀光退稅")).toBeDefined()
    expect(screen.queryByRole("progressbar")).toBeNull()
  })

  it("keeps custom country tax labels dynamically bilingual across EN -> ZH language switches", async () => {
    mockLang = "en"
    const { rerender } = render(<GlobalTaxActuary defaultCurrency="JPY" />)

    await waitFor(() => {
      expect(screen.getByTitle("Click to edit rate").textContent).toContain("0.22")
    })

    fireEvent.click(screen.getByRole("button", { name: /More\.\.\./ }))
    fireEvent.click(await screen.findByRole("button", { name: /Custom New Destination/ }))
    fireEvent.change(screen.getByPlaceholderText("e.g. Malaysia"), { target: { value: "Malaysia" } })
    fireEvent.change(screen.getByPlaceholderText("MYR"), { target: { value: "MYR" } })
    fireEvent.click(screen.getByRole("button", { name: "Create & Apply" }))

    await waitFor(() => {
      expect(screen.getByTitle("Click to edit rate").textContent).toContain("32")
    })
    expect(screen.getByRole("button", { name: /Tax-Inclusive/ })).toBeDefined()

    // Switch language to ZH and rerender — custom country MUST dynamically update to 含稅 / 未稅
    mockLang = "zh"
    rerender(<GlobalTaxActuary defaultCurrency="JPY" />)
    expect(screen.getByRole("button", { name: "含稅" })).toBeDefined()
    expect(screen.getByRole("button", { name: "未稅" })).toBeDefined()
  })

  it("guarantees SessionReauthModal z-index (z-165) stays above IOSBottomSheet (z-115)", () => {
    const reauthSrc = fs.readFileSync(
      path.resolve(__dirname, "../components/auth/session-reauth-modal.tsx"),
      "utf-8"
    )
    expect(reauthSrc).toContain('overlayClassName="z-165"')
    expect(reauthSrc).toContain("z-165")
  })
})
