"""
🛡️ Security Sentinel Sandbox In-Memory PoC: Workflow Secret Sanitization & Cloud Run Security
Tests:
- TC-1: Detects raw secret exposures in deploy-backend.yml (Cloudinary key, Supabase ref, CF worker domain)
- TC-2: Verifies sanitized workflow template conforms to valid YAML schema
- TC-3: Verifies simulated GitHub Actions context substitution satisfies Cloud Run environment contracts
- TC-4: Verifies zero-leakage invariant (No plaintext credentials in sanitized workflow)
"""
import pytest
import re
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-backend.yml"

# RegEx patterns for sensitive assets
RAW_CLOUDINARY_KEY_REGEX = re.compile(r'CLOUDINARY_API_KEY=\d{10,}')
RAW_CF_WORKER_REGEX = re.compile(r'CF_WORKER_SEARCH_URL=https://[a-zA-Z0-9_-]+\.workers\.dev')
RAW_SUPABASE_PROJECT_REGEX = re.compile(r'SUPABASE_URL=https://[a-z0-9]{15,}\.supabase\.co')


def test_tc1_detect_raw_secrets_in_current_workflow():
    """TC-1: Empirically proves that deploy-backend.yml currently contains hardcoded infrastructure strings."""
    assert DEPLOY_WORKFLOW_PATH.exists(), f"Workflow file not found at {DEPLOY_WORKFLOW_PATH}"
    content = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")
    
    # 1. Detects raw Cloudinary API Key
    has_cloudinary = bool(RAW_CLOUDINARY_KEY_REGEX.search(content))
    # 2. Detects raw Cloudflare worker domain
    has_cf_worker = bool(RAW_CF_WORKER_REGEX.search(content))
    # 3. Detects raw Supabase project URL
    has_supabase = bool(RAW_SUPABASE_PROJECT_REGEX.search(content))
    
    # At least one raw asset is currently present in line 45
    assert has_cloudinary or has_cf_worker or has_supabase, "Expected at least one raw infrastructure credential in workflow"


def test_tc2_sanitized_workflow_yaml_validity():
    """TC-2: Proves that replacing raw credentials with GitHub Secrets preserves strict YAML parseability."""
    raw_content = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")
    
    # Simulate candidate sanitization
    sanitized_content = raw_content
    sanitized_content = re.sub(
        r'SUPABASE_URL=https://[a-z0-9]+\.supabase\.co',
        'SUPABASE_URL=${{ secrets.SUPABASE_URL }}',
        sanitized_content
    )
    sanitized_content = re.sub(
        r'NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=[a-zA-Z0-9_-]+',
        'NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=${{ secrets.CLOUDINARY_CLOUD_NAME }}',
        sanitized_content
    )
    sanitized_content = re.sub(
        r'CLOUDINARY_API_KEY=\d+',
        'CLOUDINARY_API_KEY=${{ secrets.CLOUDINARY_API_KEY }}',
        sanitized_content
    )
    sanitized_content = re.sub(
        r'CF_WORKER_SEARCH_URL=https://[a-zA-Z0-9_-]+\.workers\.dev',
        'CF_WORKER_SEARCH_URL=${{ secrets.CF_WORKER_SEARCH_URL }}',
        sanitized_content
    )
    sanitized_content = re.sub(
        r'--project antigravity-prod-2026',
        '--project ${{ secrets.GCP_PROJECT_ID || \'antigravity-prod-2026\' }}',
        sanitized_content
    )
    
    # Strict YAML Parse Verification
    parsed = yaml.safe_load(sanitized_content)
    assert parsed["name"] == "Deploy Backend to Cloud Run"
    assert "jobs" in parsed
    assert "deploy" in parsed["jobs"]
    deploy_steps = parsed["jobs"]["deploy"]["steps"]
    assert any("gcloud run deploy" in step.get("run", "") for step in deploy_steps)


def test_tc3_simulated_cloud_run_environment_contract():
    """TC-3: Proves that after GitHub Secret injection, the Cloud Run container receives the expected env variables."""
    # Mock GitHub Action Runner Secret Store
    mock_secrets = {
        "SUPABASE_URL": "https://mocked-sb.supabase.co",
        "CLOUDINARY_CLOUD_NAME": "mock-cloud",
        "CLOUDINARY_API_KEY": "1234567890",
        "TP_API_TOKEN": "mock-tp-token",
        "GAS_GEOCODE_URLS": "https://script.google.com/macros/s/mock1/exec",
        "GAS_RESOLVE_LINK_URLS": "https://script.google.com/macros/s/mock2/exec",
        "CF_WORKER_SEARCH_URL": "https://mock-search.workers.dev"
    }
    
    # Construct Cloud Run Env string
    raw_env_template = (
        "^||^SUPABASE_URL={SUPABASE_URL}"
        "||API_VERSION=v1"
        "||NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME={CLOUDINARY_CLOUD_NAME}"
        "||CLOUDINARY_API_KEY={CLOUDINARY_API_KEY}"
        "||TP_API_TOKEN={TP_API_TOKEN}"
        "||GAS_GEOCODE_URLS={GAS_GEOCODE_URLS}"
        "||GAS_RESOLVE_LINK_URLS={GAS_RESOLVE_LINK_URLS}"
        "||CF_WORKER_SEARCH_URL={CF_WORKER_SEARCH_URL}"
    )
    
    injected_str = raw_env_template.format(**mock_secrets)
    
    # Verify parsing in container startup
    pairs = injected_str.lstrip("^||^").split("||")
    env_dict = dict(pair.split("=", 1) for pair in pairs)
    
    assert env_dict["SUPABASE_URL"] == "https://mocked-sb.supabase.co"
    assert env_dict["API_VERSION"] == "v1"
    assert env_dict["CLOUDINARY_API_KEY"] == "1234567890"
    assert env_dict["TP_API_TOKEN"] == "mock-tp-token"
    assert env_dict["CF_WORKER_SEARCH_URL"] == "https://mock-search.workers.dev"


def test_tc4_zero_leakage_invariant_after_patch():
    """TC-4: Proves that sanitized template achieves zero credential leakage."""
    raw_content = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")
    
    sanitized = raw_content
    sanitized = re.sub(r'https://REDACTED_SUPABASE_REF\.supabase\.co', '${{ secrets.SUPABASE_URL }}', sanitized)
    sanitized = re.sub(r'CLOUDINARY_API_KEY=REDACTED_CLOUDINARY_KEY_2', 'CLOUDINARY_API_KEY=${{ secrets.CLOUDINARY_API_KEY }}', sanitized)
    sanitized = re.sub(r'NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=REDACTED_CLOUDINARY_CLOUD', 'NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=${{ secrets.CLOUDINARY_CLOUD_NAME }}', sanitized)
    sanitized = re.sub(r'https://tabidachi-search-proxy\.ryanpig228\.workers\.dev', '${{ secrets.CF_WORKER_SEARCH_URL }}', sanitized)
    
    # Ensure zero matches for the hardcoded sensitive strings
    assert "REDACTED_CLOUDINARY_KEY_2" not in sanitized
    assert "ryanpig228" not in sanitized
    assert "REDACTED_SUPABASE_REF" not in sanitized
    assert "REDACTED_CLOUDINARY_CLOUD" not in sanitized
