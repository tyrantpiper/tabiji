"""
Security Sentinel In-Memory PoC Suite: Spec DAG Engine (2026-11-06)
Validating Path Traversal, Gate Bypass, and Grounding Circuit Breaker Invariants
Enforcing Mantis Block G Benign Control.
"""

import asyncio
import os
from pathlib import Path
import pytest
from typing import Dict, Any, Optional

# --- Reference Implementation & Invariant Guards ---

class PrototypeSandboxSecurityError(Exception):
    """Raised when prototype path escapes allowed sandbox boundary."""
    pass

class HumanGateBypassSecurityError(Exception):
    """Raised when handover to @dev is attempted without explicit human approval."""
    pass

class GroundingTimeoutFallback:
    """Simulates external radar with 5-second circuit breaker fallback."""
    def __init__(self, timeout_sec: float = 5.0):
        self.timeout_sec = timeout_sec

    async def fetch_grounding_info(self, external_fetcher, local_fallback_fetcher):
        try:
            return await asyncio.wait_for(external_fetcher(), timeout=self.timeout_sec)
        except (asyncio.TimeoutError, Exception):
            # Graceful degradation to local codebase facts
            return await local_fallback_fetcher()


def resolve_sandbox_proto_path(base_sandbox_dir: Path, requested_relative_path: str) -> Path:
    """
    Hardened path resolver enforcing strict sandbox containment.
    Prevents directory traversal (e.g., ../../package.json).
    """
    base_resolved = base_sandbox_dir.resolve()
    target_resolved = (base_sandbox_dir / requested_relative_path).resolve()

    try:
        # Must be strictly within base_sandbox_dir
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise PrototypeSandboxSecurityError(
            f"Path traversal detected! Requested path '{requested_relative_path}' resolves outside sandbox '{base_resolved}'."
        )

    # Prevent root directory pollution
    if target_resolved == base_resolved:
        raise PrototypeSandboxSecurityError("Cannot target sandbox root itself.")

    return target_resolved


def route_spec_execution(
    mode: str,
    action: str,
    human_approval_confirmed: bool
) -> Dict[str, Any]:
    """
    Dual-Track Router enforcing the Invariant:
    Under NO circumstance can an action leading to @dev or code modification proceed
    without human_approval_confirmed == True.
    """
    if action in ("handoff_to_dev", "apply_code", "write_production"):
        if not human_approval_confirmed:
            raise HumanGateBypassSecurityError(
                f"L0 Human Sovereignty Violation: Action '{action}' blocked in mode '{mode}'. Human approval is required."
            )
        return {"status": "HANDOFF_ALLOWED", "mode": mode, "action": action}

    # Pure drafting / spec generation is allowed
    return {"status": "SPEC_DRAFTED", "mode": mode, "action": action}


# --- Test Suite ---

# Target 1: Path Traversal in Prototype Sandbox
def test_red_path_traversal_in_prototype_sandbox(tmp_path: Path):
    """RED CHECK: Demonstrates that uncontained path concatenation allows escaping the sandbox."""
    sandbox_dir = tmp_path / "scratch" / "proto"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    malicious_path = "../../package.json"
    
    # Vulnerable behavior: raw concatenation escapes
    vulnerable_target = (sandbox_dir / malicious_path).resolve()
    assert vulnerable_target == tmp_path / "package.json"
    assert str(vulnerable_target).endswith("package.json")

    # Hardened behavior: must raise PrototypeSandboxSecurityError
    with pytest.raises(PrototypeSandboxSecurityError) as exc_info:
        resolve_sandbox_proto_path(sandbox_dir, malicious_path)
    assert "Path traversal detected" in str(exc_info.value)


def test_benign_prototype_generation(tmp_path: Path):
    """MANTIS BLOCK G: Benign valid relative prototype paths must resolve successfully."""
    sandbox_dir = tmp_path / "scratch" / "proto"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    valid_paths = [
        "demo_card.tsx",
        "nested/preview_button.vue",
        "styles/theme.css"
    ]

    for p in valid_paths:
        resolved = resolve_sandbox_proto_path(sandbox_dir, p)
        assert resolved.resolve().is_relative_to(sandbox_dir.resolve())
        assert resolved.name == Path(p).name


# Target 2: Approval Gate Bypass in Fast-Track Mode
def test_red_fast_track_approval_gate_bypass():
    """RED CHECK: Handover to @dev must fail if human approval is False, even in fast_track mode."""
    with pytest.raises(HumanGateBypassSecurityError) as exc_info:
        route_spec_execution(
            mode="fast_track",
            action="handoff_to_dev",
            human_approval_confirmed=False
        )
    assert "L0 Human Sovereignty Violation" in str(exc_info.value)


def test_benign_fast_track_spec_generation():
    """MANTIS BLOCK G: Benign drafting is allowed, and approved handoff succeeds."""
    # Drafting only (no human gate needed yet)
    draft_res = route_spec_execution(
        mode="fast_track",
        action="generate_spec_markdown",
        human_approval_confirmed=False
    )
    assert draft_res["status"] == "SPEC_DRAFTED"

    # Approved handoff succeeds
    approved_res = route_spec_execution(
        mode="fast_track",
        action="handoff_to_dev",
        human_approval_confirmed=True
    )
    assert approved_res["status"] == "HANDOFF_ALLOWED"


# Target 3: Unbounded Grounding Timeout Denial of Service
@pytest.mark.asyncio
async def test_red_and_benign_grounding_circuit_breaker():
    """RED & BENIGN: External hang must trigger 5.0s fallback to local codebase facts without stalling."""
    breaker = GroundingTimeoutFallback(timeout_sec=0.1)  # small timeout for test

    async def hanging_external_mcp():
        await asyncio.sleep(1.0)
        return {"source": "external", "data": "late_data"}

    async def local_fallback_fetcher():
        return {"source": "local_codebase", "data": "invariants_verified"}

    # Must NOT hang for 1.0s, must fallback immediately
    result = await breaker.fetch_grounding_info(hanging_external_mcp, local_fallback_fetcher)
    assert result["source"] == "local_codebase"
    assert result["data"] == "invariants_verified"

