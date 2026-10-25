import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Security Sentinel: Root Hygiene and Artifact Governance Audit', () => {
    const repoRoot = path.resolve(__dirname, '..', '..')
    const skillPath = path.resolve(repoRoot, '.agents', 'skills', 'security-sentinel', 'SKILL.md')
    const pushWorkflowPath = path.resolve(repoRoot, '.agents', 'workflows', 'push.md')
    const runnerPath = path.resolve(repoRoot, '.agents', 'skills', 'security-sentinel', 'scripts', 'runner.py')

    it('TC-1: candidates.json in repo root MUST be relocated to docs/security/', () => {
        const rootCandidates = path.resolve(repoRoot, 'candidates.json')
        const targetCandidates = path.resolve(repoRoot, 'docs', 'security', 'history', 'candidates', 'candidates_expense_toggle_icon_harmony.json')

        // 1. Root candidates file must be relocated (must not linger in repo root)
        expect(fs.existsSync(rootCandidates)).toBe(false)

        // 2. Relocated canonical target file must exist and contain valid audit hypotheses
        expect(fs.existsSync(targetCandidates)).toBe(true)
        const targetContent = fs.readFileSync(targetCandidates, 'utf-8')
        expect(targetContent).toContain('frontend/lib/i18n/remaining.ts:tv_list_clipboard_emoji')
    })

    it('TC-2: SKILL.md must mandate docs/security/ prefix for candidates and findings', () => {
        const content = fs.readFileSync(skillPath, 'utf-8')
        expect(content).toContain('docs/security/history/candidates/candidates_')
        expect(content).toContain('docs/security/history/findings/findings_')
        expect(content).not.toMatch(/--candidates\s+candidates\.json/)
    })

    it('TC-3: runner.py must contain root directory fail-fast guardrail function', () => {
        const content = fs.readFileSync(runnerPath, 'utf-8')
        expect(content).toContain('def assert_security_path_hygiene')
        expect(content).toContain('[Root Hygiene Violation]')
        expect(content).toContain('assert_security_path_hygiene(args.candidates, "--candidates"')
        expect(content).toContain('assert_security_path_hygiene(args.output, "--output"')
    })

    it('TC-4: push.md workflow must enforce Step 0 Root Hygiene Gate', () => {
        const content = fs.readFileSync(pushWorkflowPath, 'utf-8')
        expect(content).toContain('# 0. 專案根目錄衛生檢查 (Root Hygiene Gate)')
        expect(content).toContain('$whitelist = @("package.json"')
        expect(content).toContain('[Root Hygiene Gate]')
    })
})
