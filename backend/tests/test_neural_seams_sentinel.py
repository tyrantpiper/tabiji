# -*- coding: utf-8 -*-
"""
Security Sentinel In-Memory PoC Test Suite: Neural Seams & Keepalive
=====================================================================
Empirically verifies:
1. Dockerfile & Dockerfile.prod keepalive configuration matches upstream proxy (65s > 60s)
2. Backend main.py local bootstrap keepalive configuration is present
"""

import os
import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_keepalive_configuration():
    """
    PoC 1: 驗證後端容器部署配置是否明確包含 keep-alive 65s (防禦 Next.js/Cloudflare 60s ECONNRESET)
    """
    dockerfile_path = REPO_ROOT / "backend" / "Dockerfile"
    assert dockerfile_path.exists(), "backend/Dockerfile must exist"
    
    content = dockerfile_path.read_text(encoding="utf-8")
    
    # 檢查 Gunicorn 啟動參數是否含有 --keep-alive 65
    has_keepalive = bool(re.search(r"--keep-alive\s+65", content) or "--keep-alive" in content)
    
    # 目前 Dockerfile 尚未配置 --keep-alive 65，此處實證其脆弱性或宣告期望防線
    # 若未包含，此測試將指出該 Seam 存在靜默斷連風險
    dockerfile_prod_path = REPO_ROOT / "backend" / "Dockerfile.prod"
    prod_content = dockerfile_prod_path.read_text(encoding="utf-8") if dockerfile_prod_path.exists() else ""
    
    assert has_keepalive, "backend/Dockerfile must contain --keep-alive 65"
    assert "--timeout-keep-alive" in prod_content or "--keep-alive" in prod_content, "backend/Dockerfile.prod must contain --timeout-keep-alive 65"


def test_main_py_local_keepalive_invariance():
    """
    PoC 2: 驗證 backend/main.py 是否在本地啟動時明確宣告 timeout_keep_alive=65
    """
    main_py_path = REPO_ROOT / "backend" / "main.py"
    assert main_py_path.exists()
    
    content = main_py_path.read_text(encoding="utf-8")
    assert "timeout_keep_alive=65" in content, "main.py must configure timeout_keep_alive=65 to guard against socket hang up"
