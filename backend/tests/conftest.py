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
