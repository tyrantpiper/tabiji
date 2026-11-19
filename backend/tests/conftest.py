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
