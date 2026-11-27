import pytest


@pytest.fixture(autouse=True)
def _prevent_accidental_prod_supabase_in_agents(monkeypatch):
    """
    Prevent unit tests that do not explicitly override `get_supabase`
    from reading/writing production Supabase `agent_fallback_tasks` via `.env`.
    """
    from main import app
    from utils.deps import get_supabase
    import routers.agents as agents_router

    orig_resolve = agents_router._resolve_supabase

    def _safe_resolve(request=None):
        if get_supabase in app.dependency_overrides:
            return orig_resolve(request)
        if request is not None:
            req_app = getattr(request, "app", None)
            overrides = getattr(req_app, "dependency_overrides", None)
            if isinstance(overrides, dict) and get_supabase in overrides:
                return orig_resolve(request)
        return None

    monkeypatch.setattr(agents_router, "_resolve_supabase", _safe_resolve)


@pytest.fixture(autouse=True)
def _isolate_agents_live_research_network(monkeypatch):
    """
    Per-leaf network isolation for Deep Research v2 live news & web search:
    - Isolates `agents_router.fetch_google_news_rss` and `agents_router.execute_web_search` independently.
    - Passes through a leaf ONLY when that leaf (or its underlying `web_search_engine` target) is explicitly
      overridden by a test.
    - When neither leaf is overridden, short-circuits `_fetch_live_research_intelligence` before calling
      `_build_research_news_query` so existing offline tests never leak network requests or consume
      `mock_client.aio.models.generate_content.side_effect`.
    """
    import routers.agents as agents_router
    from services import web_search_engine

    orig_fetch_intel = agents_router._fetch_live_research_intelligence
    orig_wse_rss = web_search_engine.fetch_google_news_rss
    orig_wse_web = web_search_engine.execute_web_search
    orig_wse_client = web_search_engine.get_search_client

    async def _guarded_rss(*args, **kwargs):
        if (
            web_search_engine.fetch_google_news_rss is not orig_wse_rss
            or web_search_engine.get_search_client is not orig_wse_client
        ):
            return await web_search_engine.fetch_google_news_rss(*args, **kwargs)
        return []

    async def _guarded_web(*args, **kwargs):
        if web_search_engine.execute_web_search is not orig_wse_web:
            return await web_search_engine.execute_web_search(*args, **kwargs)
        return []

    def _is_rss_overridden() -> bool:
        return (
            agents_router.fetch_google_news_rss is not _guarded_rss
            or web_search_engine.fetch_google_news_rss is not orig_wse_rss
            or web_search_engine.get_search_client is not orig_wse_client
        )

    def _is_web_overridden() -> bool:
        return (
            agents_router.execute_web_search is not _guarded_web
            or web_search_engine.execute_web_search is not orig_wse_web
        )

    async def _guarded_fetch_intel(*args, **kwargs):
        if not _is_rss_overridden() and not _is_web_overridden():
            return "", []
        return await orig_fetch_intel(*args, **kwargs)

    monkeypatch.setattr(agents_router, "fetch_google_news_rss", _guarded_rss)
    monkeypatch.setattr(agents_router, "execute_web_search", _guarded_web)
    monkeypatch.setattr(agents_router, "_fetch_live_research_intelligence", _guarded_fetch_intel)


@pytest.fixture(autouse=True)
def _isolate_web_search_and_gas_caches():
    """Reset module-level caches, route state, flight pricing, and GAS dead caches between tests."""
    from services.web_search_engine import __reset_web_search_cache_for_testing
    from services.link_resolver import __reset_link_resolver_caches_for_testing
    from services.flight_pricing_service import __reset_flight_pricing_for_testing
    from routers.route import __reset_route_state_for_testing
    from services import geocode_service

    __reset_web_search_cache_for_testing()
    __reset_link_resolver_caches_for_testing()
    __reset_flight_pricing_for_testing()
    __reset_route_state_for_testing()
    geocode_service._DEAD_URL_CACHE.clear()
    yield
    __reset_web_search_cache_for_testing()
    __reset_link_resolver_caches_for_testing()
    __reset_flight_pricing_for_testing()
    __reset_route_state_for_testing()
    geocode_service._DEAD_URL_CACHE.clear()
