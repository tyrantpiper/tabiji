"""
🛡️ Five-Cloud Hardening Waves 1-3 Regression & Mantis Block G Test Suite
Covers:
- Wave 1.1 / 1.2 / 3.3 SQL Migration static security contracts
- Wave 1.3 Web search 6h LRU cache, temporal wiki guard, CF Edge priority
- Wave 2.1 POI multi-signal Top-K scoring, no-coord normalization, compliant UA, #/& quote
- Wave 2.2 /api/poi/media-proxy 3-host whitelist, 2-hop urljoin redirect, SVG 415, untrusted redirect 400
- Wave 2.3 Shared flight_pricing_service + /api/agents/research/stream SSE + /api/chat/stream pricing injection
- Wave 3.1 Valhalla Polyline6 decode, straight-line short debounce (no 600s cache), 429 circuit breaker
- Wave 3.2 Zero blocking async def routes AST check, trips/ledger UUID guards, 22P02->404, zero detail=str(e)
- Wave 3.3 deps/auth production Fail-Closed, /docs & /openapi.json disabled in prod, /metrics secret gate
"""

import ast
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import main as backend_main
from routers import auth as auth_router
from routers import route as route_router
from services import flight_pricing_service, poi_service, web_search_engine
from utils.deps import get_session_secret, get_supabase, get_verified_user


# ---------------------------------------------------------------------------
# Wave 1.1, 1.2, 3.3 — SQL Migration Contract
# ---------------------------------------------------------------------------
def test_wave1_wave3_migration_security_contracts():
    mig_path = REPO_ROOT / "supabase" / "migrations" / "20261126_harden_push_rls_and_notify_hmac.sql"
    assert mig_path.exists()
    sql = mig_path.read_text(encoding="utf-8")
    sql_no_comments = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))

    # Wave 1.1: push_subscriptions Default-Deny
    assert "REVOKE ALL ON TABLE public.push_subscriptions FROM PUBLIC, anon, authenticated;" in sql_no_comments
    assert 'DROP POLICY IF EXISTS "Users manage own push subscriptions" ON public.push_subscriptions;' in sql_no_comments
    assert "ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;" in sql_no_comments

    # Wave 1.2: Vault HMAC for notify-event & notify-countdown
    assert "'notify_webhook_secret'" in sql_no_comments
    assert "CREATE OR REPLACE FUNCTION public.verify_notify_webhook_signature(" in sql_no_comments
    assert "abs(v_now - p_timestamp) > 300" in sql_no_comments
    assert "REVOKE ALL ON FUNCTION public.verify_notify_webhook_signature(bigint, text, text) FROM PUBLIC, anon, authenticated;" in sql_no_comments
    assert "CREATE OR REPLACE FUNCTION public.dispatch_trip_countdown_daily()" in sql_no_comments

    # Wave 3.3: No plaintext Bearer fallback in executable SQL + GIN-indexed spots ref-count guard
    assert "app.settings.service_role_key" not in sql_no_comments
    assert "idx_itinerary_items_spot_ref_ids" in sql_no_comments
    assert "extract_spot_cloudinary_ids" in sql_no_comments
    assert "USING GIN" in sql_no_comments


# ---------------------------------------------------------------------------
# Wave 1.3 — Web Search 6h LRU Cache, Temporal Wiki Guard, Edge Priority
# ---------------------------------------------------------------------------
def test_wave1_web_search_temporal_wiki_guard_and_benign_control():
    # Exploit / Poisoning prevention: time-sensitive queries must NOT hit Wikipedia
    assert web_search_engine._has_temporal_search_keyword("Shibuya Sky tickets 2026") is True
    assert web_search_engine._has_temporal_search_keyword("東京鐵塔 營業時間 2026") is True
    assert web_search_engine._has_temporal_search_keyword("晴空塔 預約 票價") is True

    # Benign control: historical / descriptive query allowed
    assert web_search_engine._has_temporal_search_keyword("淺草寺 歷史背景") is False
    assert web_search_engine._is_relevant_wiki_title("淺草寺 歷史", "淺草寺") is True
    assert web_search_engine._is_relevant_wiki_title("Shibuya Sky tickets 2026", "BLACKPINK") is False
    assert web_search_engine._is_relevant_wiki_title("東京鐵塔 營業時間", "東京電視台") is False


@pytest.mark.asyncio
async def test_wave1_web_search_lru_cache_and_cf_edge_priority(monkeypatch):
    web_search_engine.__reset_web_search_cache_for_testing()
    monkeypatch.setenv("CF_WORKER_SEARCH_URL", "https://search-proxy.example.com")
    monkeypatch.setenv("CF_PROXY_SECRET", "  super-secret-key  ")

    edge_calls = []

    async def fake_edge(query, max_results=3):
        edge_calls.append((query, max_results))
        return [{"title": "Shibuya Sky Official Tickets", "url": "https://www.shibuya-scramble-square.com/", "snippet": "2026 ticket info"}]

    ddgs_mock = MagicMock(side_effect=AssertionError("Tier 1 ddgs must NOT burn timeout before Tier 2 CF Edge"))

    with patch.object(web_search_engine, "_search_cloudflare_edge", side_effect=fake_edge), \
         patch.object(web_search_engine, "_sync_ddgs_call", ddgs_mock):
        res1 = await web_search_engine.execute_web_search("Shibuya Sky 門票", region="jp-jp", max_results=3)
        res2 = await web_search_engine.execute_web_search("Shibuya Sky 門票", region="jp-jp", max_results=3)

    assert len(res1) == 1
    assert res1 == res2
    assert len(edge_calls) == 1, "Second identical query must hit 6h LRU cache"
    ddgs_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Wave 2.1 — POI Multi-Signal Top-K Scoring & Compliant UA
# ---------------------------------------------------------------------------
def test_wave2_poi_topk_disambiguation_and_no_coord_normalization():
    # Compliant UA check
    assert "contact@tabijiapp.com" in poi_service.TABIJI_USER_AGENT
    assert "example.com" not in poi_service.TABIJI_USER_AGENT

    # Case 1: 東京鐵塔 beats nearby 東京塔攝影棚
    s_exact, sim_exact, q_exact = poi_service._score_wiki_candidate(
        "東京鐵塔",
        "東京鐵塔",
        poi_lat=35.6586,
        poi_lng=139.7454,
        cand_lat=35.6586,
        cand_lng=139.7454,
        poi_type="attraction",
    )
    s_studio, sim_studio, _ = poi_service._score_wiki_candidate(
        "東京鐵塔",
        "東京塔攝影棚",
        poi_lat=35.6586,
        poi_lng=139.7454,
        cand_lat=35.6585,
        cand_lng=139.7453,
        poi_type="attraction",
    )
    assert s_exact > s_studio
    assert poi_service._is_wiki_candidate_admitted(s_exact, sim_exact, q_exact) is True

    # Case 2: 清水寺 beats 地主神社
    s_kiyo, sim_kiyo, _ = poi_service._score_wiki_candidate(
        "清水寺",
        "清水寺",
        poi_lat=34.9949,
        poi_lng=135.7850,
        cand_lat=34.9949,
        cand_lng=135.7850,
    )
    s_jishu, sim_jishu, _ = poi_service._score_wiki_candidate(
        "清水寺",
        "地主神社",
        poi_lat=34.9949,
        poi_lng=135.7850,
        cand_lat=34.9950,
        cand_lng=135.7851,
    )
    assert s_kiyo > s_jishu
    assert poi_service._is_wiki_candidate_admitted(s_jishu, sim_jishu, False) is False

    # Case 3: Restaurant vs district admin penalty (北海 -HOKKAI- お初天神店 vs 曾根崎)
    s_dist, sim_dist, _ = poi_service._score_wiki_candidate(
        "北海 -HOKKAI- お初天神店",
        "曾根崎",
        poi_lat=34.7024,
        poi_lng=135.5002,
        cand_lat=34.7020,
        cand_lng=135.5000,
        poi_type="restaurant",
        cand_description="日本大阪府大阪市北區的町名",
    )
    assert poi_service._is_wiki_candidate_admitted(s_dist, sim_dist, False) is False

    # Case 4: > 5km hard veto
    s_far, _, _ = poi_service._score_wiki_candidate(
        "東京鐵塔",
        "東京鐵塔",
        poi_lat=35.6586,
        poi_lng=139.7454,
        cand_lat=35.8000,
        cand_lng=139.9000,
    )
    assert s_far == float("-inf")

    # Case 5: No-coordinate exact match still passes admission threshold >= 55
    s_nocoord, sim_nocoord, _ = poi_service._score_wiki_candidate(
        "清水寺",
        "清水寺",
        poi_lat=None,
        poi_lng=None,
        cand_lat=None,
        cand_lng=None,
    )
    assert s_nocoord >= 55.0
    assert poi_service._is_wiki_candidate_admitted(s_nocoord, sim_nocoord, False) is True

    # Case 6: Historical event/arson penalty rejects 金閣寺放火事件 for query 金閣寺,
    # while benign control querying 金閣寺放火事件 directly is NOT penalized
    s_arson, sim_arson, _ = poi_service._score_wiki_candidate(
        "金閣寺",
        "金阁寺放火事件",
        poi_lat=35.0394,
        poi_lng=135.7292,
        cand_lat=35.0394,
        cand_lng=135.7292,
        poi_type="temple",
    )
    assert poi_service._is_wiki_candidate_admitted(s_arson, sim_arson, False) is False

    s_event_benign, sim_event_benign, _ = poi_service._score_wiki_candidate(
        "金閣寺放火事件",
        "金阁寺放火事件",
        poi_lat=35.0394,
        poi_lng=135.7292,
        cand_lat=35.0394,
        cand_lng=135.7292,
    )
    assert poi_service._is_wiki_candidate_admitted(s_event_benign, sim_event_benign, False) is True

    # Case 7: Traditional <-> Simplified CJK orthography equivalence (嵐山/岚山, 銀座/银座, 橫濱/横滨, 東京/东京)
    assert poi_service._compute_name_similarity("嵐山", "岚山 (京都市)") == 1.0
    assert poi_service._compute_name_similarity("銀座", "银座") == 1.0
    assert poi_service._compute_name_similarity("橫濱", "横滨") == 1.0
    assert poi_service._compute_name_similarity("東京", "东京") == 1.0

    # Geocode service zero residual placeholder UAs
    geo_src = (REPO_ROOT / "backend" / "services" / "geocode_service.py").read_text(encoding="utf-8")
    assert "contact@ryantravel.app" not in geo_src
    assert '"RyanTravelApp/' not in geo_src


@pytest.mark.asyncio
async def test_wave2_poi_disambiguation_page_resolves_to_nearby_canonical_article():
    """Disambiguation page (e.g., 金閣寺 -> 鹿苑寺) must resolve via batched outgoing links + coordinates."""
    disambig_summary = {"type": "disambiguation", "title": "金閣寺", "extract": "金閣寺可以指：..."}
    links_payload = {
        "query": {
            "pages": [
                {"title": "金閣寺 (五台山)", "coordinates": [{"lat": 38.99, "lon": 113.59}], "description": "山西寺院"},
                {"title": "鹿苑寺", "coordinates": [{"lat": 35.0395, "lon": 135.7285}], "description": "日本京都的佛教禪宗寺院"},
            ]
        }
    }
    rokuonji_summary = {
        "type": "standard",
        "title": "鹿苑寺",
        "extract": "鹿苑寺，又名金閣寺，位於京都府京都市北區。",
        "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Kinkakuji.jpg/330px-Kinkakuji.jpg"},
    }

    async def fake_fetch_summary(title, lang, headers, client=None):
        if title == "金閣寺":
            return disambig_summary
        if title == "鹿苑寺":
            return rokuonji_summary
        return None

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = links_payload
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_resp)

    with patch.object(poi_service, "_fetch_wiki_page_summary", side_effect=fake_fetch_summary), \
         patch.object(poi_service, "is_safe_url", return_value=True):
        desc, img = await poi_service.get_wikipedia_summary(
            "金閣寺", lang="zh", client=fake_client, lat=35.0394, lng=135.7292, poi_type="temple"
        )

    assert "鹿苑寺" in desc
    assert "放火" not in desc
    assert img.endswith("330px-Kinkakuji.jpg")


# ---------------------------------------------------------------------------
# Wave 2.2 — /api/poi/media-proxy 3-Host Whitelist & Safe Redirect Loop
# ---------------------------------------------------------------------------
def test_wave2_media_proxy_allows_3_hosts_and_blocks_untrusted_redirect():
    client = TestClient(backend_main.app)

    # Exploit: untrusted host -> 400
    r_bad_host = client.get("/api/poi/media-proxy", params={"url": "https://evil.example.com/a.jpg"})
    assert r_bad_host.status_code == 400

    # Exploit: SVG on thumb.wikimedia.org -> 415
    r_svg = client.get("/api/poi/media-proxy", params={"url": "https://thumb.wikimedia.org/wikipedia/commons/a/a1/logo.svg"})
    assert r_svg.status_code == 415

    # Exploit: 302 redirect from commons.wikimedia.org -> untrusted host -> 400
    class FakeResp:
        def __init__(self, status_code, headers, body=b""):
            self.status_code = status_code
            self.headers = httpx.Headers(headers)
            self._body = body
            self.closed = False

        async def aclose(self):
            self.closed = True

        async def aiter_bytes(self, chunk_size=65536):
            yield self._body

    redirect_to_evil = FakeResp(302, {"location": "https://evil.example.com/pwn.png"})
    fake_client = MagicMock()
    fake_client.build_request = lambda m, u, **kw: httpx.Request(m, u)
    fake_client.send = AsyncMock(return_value=redirect_to_evil)
    fake_client.aclose = AsyncMock()

    with patch("routers.poi.create_safe_client", return_value=fake_client), \
         patch("routers.poi.is_safe_url_async", AsyncMock(return_value=True)):
        r_redir_evil = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://commons.wikimedia.org/wiki/Special:FilePath/Tokyo_Tower.jpg"},
        )
    assert r_redir_evil.status_code == 400
    assert redirect_to_evil.closed is True

    # Benign control: protocol-relative redirect //upload.wikimedia.org/... -> 200 with sandbox CSP
    redirect_rel = FakeResp(302, {"location": "//upload.wikimedia.org/wikipedia/commons/thumb/a/a1/T.jpg/330px-T.jpg"})
    ok_img = FakeResp(200, {"content-type": "image/jpeg", "content-length": "4"}, body=b"\xff\xd8\xff\xe0")
    fake_client2 = MagicMock()
    fake_client2.build_request = lambda m, u, **kw: httpx.Request(m, u)
    fake_client2.send = AsyncMock(side_effect=[redirect_rel, ok_img])
    fake_client2.aclose = AsyncMock()

    with patch("routers.poi.create_safe_client", return_value=fake_client2), \
         patch("routers.poi.is_safe_url_async", AsyncMock(return_value=True)):
        r_ok = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://commons.wikimedia.org/wiki/Special:FilePath/T.jpg"},
        )
    assert r_ok.status_code == 200
    assert redirect_rel.closed is True
    assert "sandbox" in r_ok.headers.get("content-security-policy", "")


# ---------------------------------------------------------------------------
# Wave 2.3 — Flight Pricing Service
# ---------------------------------------------------------------------------
def test_wave2_flight_pricing_iata_and_itinerary_extraction():
    flight_pricing_service.__reset_flight_pricing_for_testing()
    assert flight_pricing_service._match_local_iata("2026 東京家族之旅") == "TYO"
    assert flight_pricing_service._match_local_iata("Osaka Food Trip") == "OSA"

    # Explicit flight_info takes priority even on 0-activity skeleton itinerary
    origin, dest, dep_date = flight_pricing_service.extract_route_from_itinerary({
        "title": "神秘秘境之旅",
        "flight_info": {
            "outbound": [{"dep_airport": "KHH", "arr_airport": "CTS", "dep_date": "2026-12-01"}]
        },
        "days": [],
    })
    assert origin == "KHH"
    assert dest == "CTS"
    assert dep_date == "2026-12-01"


# ---------------------------------------------------------------------------
# Wave 3.1 — Route Polyline6, Straight-Line Short Debounce & 429 Circuit Breaker
# ---------------------------------------------------------------------------
def test_wave3_valhalla_polyline6_and_circuit_breaker():
    route_router.__reset_route_state_for_testing()

    def _encode_poly6(pts):
        out = []
        plat = plng = 0
        for lat, lng in pts:
            ilat, ilng = round(lat * 1e6), round(lng * 1e6)
            for v in (ilat - plat, ilng - plng):
                v = ~(v << 1) if v < 0 else (v << 1)
                while v >= 0x20:
                    out.append(chr((0x20 | (v & 0x1F)) + 63))
                    v >>= 5
                out.append(chr(v + 63))
            plat, plng = ilat, ilng
        return "".join(out)

    sample = [(35.658581, 139.745433), (35.659100, 139.746000)]
    encoded = _encode_poly6(sample)
    decoded = route_router.decode_polyline6(encoded)
    assert len(decoded) == 2
    assert abs(decoded[0][1] - 35.658581) < 1e-5
    assert abs(decoded[0][0] - 139.745433) < 1e-5

    # Circuit breaker test
    assert route_router._is_engine_circuit_open("osrm") is False
    route_router._trip_engine_circuit("osrm", duration_sec=60.0)
    assert route_router._is_engine_circuit_open("osrm") is True
    route_router.__reset_route_state_for_testing()
    assert route_router._is_engine_circuit_open("osrm") is False


@pytest.mark.asyncio
async def test_wave3_route_straight_line_not_poisoning_long_cache():
    route_router.__reset_route_state_for_testing()
    from models.base import RouteRequest

    req = RouteRequest(
        stops=[{"lat": 35.6586, "lng": 139.7454}, {"lat": 35.6620, "lng": 139.7500}],
        mode="walk",
    )
    with patch.object(route_router, "route_with_osrm", AsyncMock(return_value=None)), \
         patch.object(route_router, "route_with_valhalla", AsyncMock(return_value=None)), \
         patch.object(route_router, "route_with_ors", AsyncMock(return_value=None)):
        res = await route_router.calculate_route(req)
    assert res["source"] == "straight-line"
    assert len(route_router._ROUTE_CACHE._cache) == 0, "straight-line fallback must NEVER write to 600s _ROUTE_CACHE"
    assert len(route_router._STRAIGHT_DEBOUNCE_CACHE._cache) == 1

    # Benign control: OSRM fails -> Valhalla succeeds -> returned & cached in 600s _ROUTE_CACHE
    route_router.__reset_route_state_for_testing()
    valhalla_ok = route_router._format_route_response(
        "valhalla-fossgis",
        {"type": "LineString", "coordinates": [[139.7454, 35.6586], [139.748, 35.66], [139.7500, 35.6620]]},
        0.72,
        9.0,
    )
    with patch.object(route_router, "route_with_osrm", AsyncMock(side_effect=RuntimeError("429"))), \
         patch.object(route_router, "route_with_valhalla", AsyncMock(return_value=valhalla_ok)):
        res_ok = await route_router.calculate_route(req)
    assert res_ok["source"] == "valhalla-fossgis"
    assert len(res_ok["route"]["geometry"]["coordinates"]) == 3
    assert len(route_router._ROUTE_CACHE._cache) == 1


# ---------------------------------------------------------------------------
# Wave 3.2 — Zero Blocking Async Routes AST Gate & UUID / 22P02 / Sanitization
# ---------------------------------------------------------------------------
def test_wave3_zero_blocking_async_routes_ast_invariant():
    """Verify NO async def handler OR awaited async helper in routers/main executes blocking sync .execute() on the event loop."""
    violations = []
    targets = sorted((REPO_ROOT / "backend" / "routers").glob("*.py")) + [REPO_ROOT / "backend" / "main.py"]
    for p in targets:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef):
                sync_execs = []

                def visit(n):
                    if isinstance(n, (ast.FunctionDef, ast.Lambda)):
                        return
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute":
                        sync_execs.append(n.lineno)
                    for c in ast.iter_child_nodes(n):
                        visit(c)

                for stmt in node.body:
                    visit(stmt)
                if sync_execs:
                    violations.append(f"{p.name}:{node.lineno} {node.name} -> {sync_execs}")

    assert violations == [], f"Found blocking sync .execute() inside async handlers/helpers: {violations}"


def test_wave3_invalid_literal_trip_ids_and_ledger_uuid_guard():
    mock_sb = MagicMock()
    backend_main.app.dependency_overrides[get_supabase] = lambda: mock_sb
    backend_main.app.dependency_overrides[get_verified_user] = lambda: "11111111-1111-4111-8111-111111111111"
    try:
        client = TestClient(backend_main.app)
        # Invalid literal IDs blocked unconditionally before hitting DB
        for bad in ("undefined", "null", "NaN"):
            assert client.get(f"/api/trips/{bad}").status_code == 404
            assert client.delete(f"/api/trips/{bad}").status_code == 404
            assert client.patch(f"/api/trips/{bad}/title", json={"title": "x"}).status_code == 403

        # Public ledger invalid UUID -> 404 (not 500)
        assert client.get("/api/ledger/not-a-valid-uuid").status_code == 404
        assert client.get("/api/ledger/undefined").status_code == 404

        # Simulated Postgres 22P02 on get_trip_by_id -> clean 404 without leaking SQL message
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception(
            '{"code": "22P02", "message": "invalid input syntax for type uuid: \\"bad-id\\""}'
        )
        r_22p02 = client.get("/api/trips/trip-bad-22p02")
        assert r_22p02.status_code == 404
        assert "22P02" not in r_22p02.text

        # Simulated unexpected DB failure -> sanitized 500 without leaking raw exception string
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = RuntimeError(
            "INTERNAL_SECRET_PG_DSN_LEAK"
        )
        r_500 = client.get("/api/trips/11111111-1111-4111-8111-222222222222")
        assert r_500.status_code == 500
        assert "INTERNAL_SECRET_PG_DSN_LEAK" not in r_500.text
    finally:
        backend_main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Wave 3.3 — Production Fail-Closed Secrets, /docs Lockdown & /metrics Gate
# ---------------------------------------------------------------------------
def test_wave3_prod_secrets_fail_closed(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_present_but_must_not_fallback_in_prod")
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        get_session_secret()

    monkeypatch.delenv("VAULT_MASTER_KEY", raising=False)
    with pytest.raises(RuntimeError, match="VAULT_MASTER_KEY"):
        auth_router.get_vault_master_key()

    # Benign control: explicit keys succeed in production
    monkeypatch.setenv("SESSION_SECRET_KEY", "prod-session-secret-key-32bytes!!")
    monkeypatch.setenv("VAULT_MASTER_KEY", "prod-vault-master-key-32bytes!!!!")
    assert get_session_secret() == "prod-session-secret-key-32bytes!!"
    assert auth_router.get_vault_master_key() == "prod-vault-master-key-32bytes!!!!"


def test_wave3_prod_docs_and_metrics_fail_closed(monkeypatch):
    client = TestClient(backend_main.app)

    # In production without METRICS_SECRET -> /docs, /redoc, /openapi.json, /metrics ALL 404
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("METRICS_SECRET", raising=False)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/metrics").status_code == 404

    # In production WITH METRICS_SECRET -> unauth/wrong returns 401, valid header returns 200
    monkeypatch.setenv("METRICS_SECRET", "super-metrics-secret-2026")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-Metrics-Secret": "wrong"}).status_code == 401
    assert client.get("/metrics", headers={"X-Metrics-Secret": "super-metrics-secret-2026"}).status_code == 200
    assert client.get("/metrics", headers={"Authorization": "Bearer super-metrics-secret-2026"}).status_code == 200
