# 🛡️ Security Sentinel Audit Report: Phase 4 Multi-Device Auth Sync Deadlock

- **Date**: 2026-10-23
- **Auditor**: Security Sentinel (`@security` with Cloudflare 6-Phase Ledger & Google Mantis Patch Engine)
- **Targets Evaluated**: 3
- **In-Memory PoC Verification**: 4/4 Passed (0.32s)
- **Ledger Verification**: 218 Targets Checked (`scripts/validate_security_ledger.py` Green)

---

## 1. Executive Summary

During multi-device key rotation and cross-device synchronization auditing, an acute authentication deadlock was identified when legacy devices (holding native `user_uuid`) or dormant devices (whose 30-day JWT expired while offline) attempt to synchronize with accounts upgraded or rotated on another device.

| Target ID | Trust Boundary | Vector | Status | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| `backend/routers/auth.py:legacy_and_rotated_key_deadlock` | `public_to_authenticated` | `device_lockout_deadlock` | **CONFIRMED_PENDING_DEV** | Proof-of-Possession session verification |
| `backend/routers/auth.py:credential_vault_expired_token_block` | `authenticated_to_internal` | `grace_period_missing_for_dormant_device` | **CONFIRMED_PENDING_DEV** | 90-day grace period for vault self-healing |
| `frontend/lib/auth-session.ts:dormant_token_vault_sync_barrier` | `browser_to_edge` | `client_side_token_prerequisite_lockout` | **CONFIRMED_PENDING_DEV** | Fallback to stored token for dormant exchange |

---

## 2. In-Memory PoC Verification

The deadlock and its hardened solution were formally reproduced and proven in `backend/tests/test_phase4_sync_deadlock_poc.py`:
- **TC-1 (Legacy Device Deadlock & Resolution)**: Proved that a blind 400 rejection traps authentic legacy devices, whereas requiring Proof-of-Possession allows legitimate devices to upgrade to modern credentials while strictly blocking unauthenticated ATO attackers.
- **TC-2 (Dormant Device Grace Period)**: Proved that allowing a 90-day grace period on server-signed tokens enables dormant devices to self-heal their recovery key without exposing the endpoint to forged signatures.

---

## 3. Candidate Mantis Patch Diff & Block Replacements

Patch Candidate: `docs/security/patch_candidate_phase4_sync_deadlock_2026-10-23.diff`

### Block Replacement 1: `backend/routers/auth.py`
```python
# Target lines 227-231 in backend/routers/auth.py:
<<<<
        # 若用戶已完成雙軌升級，強制阻斷原生 UUID，消除 ATO 漏洞
        if user_rec and user_rec.get("recovery_key_id"):
            raise HTTPException(
                status_code=400, 
                detail="Account already upgraded. Please use your modern recovery key (tbj_rec_*)."
            )
====
        # 🛡️ 雙軌平滑升級：若帳號已升級，校驗合法持有證明 (Proof-of-Possession)
        if user_rec and user_rec.get("recovery_key_id"):
            is_authenticated = False
            if auth_header and auth_header.startswith("Bearer "):
                cand_token = auth_header.split(" ")[1].strip()
                try:
                    payload = jwt.decode(
                        cand_token, secret, algorithms=["HS256"], issuer="tabiji-core", options={"verify_exp": False}
                    )
                    now = int(time.time())
                    if payload.get("sub") == clean_uid and payload.get("type") == "device_session" and (now - payload.get("iat", 0) <= 90 * 86400):
                        is_authenticated = True
                except Exception:
                    pass

            if not is_authenticated:
                raise HTTPException(
                    status_code=401, 
                    detail="Account already upgraded. Please use your modern recovery key (tbj_rec_*)."
                )

            vault_key = derive_vault_key(secret)
            decrypted_key = decrypt_recovery_key(user_rec.get("recovery_key_encrypted"), vault_key)
            token = create_session_jwt(clean_uid, secret, user_rec.get("credential_version", 1))
            return SessionResponse(
                access_token=token,
                user_id=clean_uid,
                recovery_key=decrypted_key,
                upgraded=True,
                is_new=False,
            )
>>>>
```

### Block Replacement 2: `frontend/lib/auth-session.ts`
Attach `Authorization: Bearer <token>` in `ensureValidSession()` to supply Proof-of-Possession, and dispatch reactive `tabiji:recovery_key_updated` event when `fetchLatestRecoveryKey()` detects rotated credentials.

---

## 4. L0 Human Gate Handover
In accordance with L0 Constitution, `@security` presents these verified findings and candidate fixes for human review and confirmation before applying changes to production.
