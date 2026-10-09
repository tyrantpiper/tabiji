import { chromium } from 'playwright'
import path from 'path'

async function run() {
    const browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({
        viewport: { width: 412, height: 915 },
        deviceScaleFactor: 2
    })
    const page = await context.newPage()

    await page.addInitScript(() => {
        localStorage.setItem('user_uuid', '2a8b7442-9b9c-491d-aadc-b13311af418d')
        localStorage.setItem('user_nickname', 'Ryan Su')
        localStorage.setItem('tabiji_active_tab', 'profile')
        localStorage.setItem('has_seen_splash', 'true')
        localStorage.setItem('tabidachi-onboarding-storage', JSON.stringify({
            state: {
                isCompleted: true,
                isTourCompleted: true,
                isTourActive: false
            },
            version: 0
        }))
    })

    await page.goto("http://localhost:3000", { waitUntil: "networkidle" })
    await page.waitForTimeout(1500)

    const closeBtn = page.locator('button').filter({ has: page.locator('svg.lucide-x') }).first()
    if (await closeBtn.isVisible()) {
        await closeBtn.click()
        await page.waitForTimeout(500)
    }

    await page.click('#tour-nav-profile')
    await page.waitForTimeout(1000)

    const outDir = path.resolve('..', 'docs', 'screenshots', 'verification')

    // Scroll to Bento Cards
    await page.evaluate(() => {
        const els = Array.from(document.querySelectorAll('*'))
        const scroller = els.find(el => el.scrollHeight > el.clientHeight && el.clientHeight > 400)
        if (scroller) {
            scroller.scrollTop = 620
        }
    })
    await page.waitForTimeout(800)

    // Capture Light Mode Bento Cards
    const proofLightScrolled = path.join(outDir, 'proof_profile_view_bentos_light.png')
    await page.screenshot({ path: proofLightScrolled })
    console.log(`Saved: ${proofLightScrolled}`)

    // Switch to Dark Mode & Capture Bento Cards
    await page.evaluate(() => document.documentElement.classList.add('dark'))
    await page.waitForTimeout(600)
    const proofDarkScrolled = path.join(outDir, 'proof_profile_view_bentos_dark.png')
    await page.screenshot({ path: proofDarkScrolled })
    console.log(`Saved: ${proofDarkScrolled}`)

    await browser.close()
}

run().catch(err => {
    console.error("Error:", err)
    process.exit(1)
})
