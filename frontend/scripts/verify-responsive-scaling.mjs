import { chromium } from 'playwright'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUTPUT_DIR = path.resolve(__dirname, '../../docs/screenshots/verification')

async function run() {
    const browser = await chromium.launch({ headless: true })

    const viewports = [
        { name: 'mobile_412', width: 412, height: 915 },
        { name: 'tablet_768', width: 768, height: 1024 },
        { name: 'desktop_1440', width: 1440, height: 900 }
    ]

    for (const vp of viewports) {
        const context = await browser.newContext({
            viewport: { width: vp.width, height: vp.height },
            deviceScaleFactor: 1
        })
        const page = await context.newPage()

        await page.addInitScript(() => {
            localStorage.setItem('user_uuid', '2a8b7442-9b9c-491d-aadc-b13311af418d')
            localStorage.setItem('user_nickname', 'Ryan Su')
            localStorage.setItem('tabidachi_tour_completed', 'true')
        })

        await page.goto('http://localhost:3000', { waitUntil: 'networkidle' })
        await page.waitForTimeout(1000)

        // Capture Home Dashboard
        await page.screenshot({
            path: path.join(OUTPUT_DIR, `proof_responsive_${vp.name}_home.png`),
            fullPage: false
        })

        // Dismiss any modal/overlay if visible
        const closeBtn = page.locator('button').filter({ has: page.locator('svg.lucide-x') }).first()
        if (await closeBtn.isVisible().catch(() => false)) {
            await closeBtn.click()
            await page.waitForTimeout(400)
        }

        // Navigate to Profile using explicit tour ID
        await page.click('#tour-nav-profile')
        await page.waitForTimeout(600)

        // Capture Profile View
        await page.screenshot({
            path: path.join(OUTPUT_DIR, `proof_responsive_${vp.name}_profile.png`),
            fullPage: false
        })

        await context.close()
    }

    await browser.close()
    console.log('✅ Captured all responsive viewport screenshots successfully!')
}

run().catch(err => {
    console.error('Execution failed:', err)
    process.exit(1)
})
