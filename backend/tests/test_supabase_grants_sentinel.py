"""
Supabase Data API Grant Sentinel (Post-2026-10-30 Breaking Change Defense)
Ensures that any PostgreSQL table or view created in public schema explicitly 
includes GRANT statements and RLS activation in the same migration file.
"""
import re
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MIGRATION_DIRS = [
    ROOT_DIR / "supabase" / "migrations",
    ROOT_DIR / "backend" / "migrations",
]

TABLE_CREATE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z0-9_]+)",
    re.IGNORECASE
)
VIEW_CREATE_PATTERN = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:public\.)?([a-zA-Z0-9_]+)",
    re.IGNORECASE
)

def test_all_future_migrations_contain_explicit_grants():
    """
    Asserts that any table created in migrations has corresponding GRANT statements.
    """
    violations = []
    
    for mig_dir in MIGRATION_DIRS:
        if not mig_dir.exists():
            continue
        for sql_file in mig_dir.glob("*.sql"):
            content = sql_file.read_text(encoding="utf-8")
            
            tables = TABLE_CREATE_PATTERN.findall(content)
            for table in tables:
                if table.lower().startswith("temp_"):
                    continue
                
                grant_pattern = re.compile(
                    rf"GRANT\s+[\s\S]*?ON\s+(?:TABLE\s+)?(?:public\.)?{table}\s+TO\s+[^;]*(?:authenticated|service_role)",
                    re.IGNORECASE
                )
                rls_pattern = re.compile(
                    rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
                    re.IGNORECASE
                )
                
                has_grant = bool(grant_pattern.search(content))
                has_rls = bool(rls_pattern.search(content))
                
                if sql_file.name >= "20261022" and not (has_grant and has_rls):
                    violations.append(
                        f"[{sql_file.name}] Table '{table}' missing explicit GRANT or RLS statement."
                    )

            views = VIEW_CREATE_PATTERN.findall(content)
            for view in views:
                view_grant_pattern = re.compile(
                    rf"GRANT\s+[\s\S]*?SELECT\s+[\s\S]*?ON\s+(?:VIEW\s+)?(?:public\.)?{view}\s+TO\s+[^;]*(?:authenticated|service_role)",
                    re.IGNORECASE
                )
                if sql_file.name >= "20261022" and not view_grant_pattern.search(content):
                    violations.append(
                        f"[{sql_file.name}] View '{view}' missing explicit GRANT SELECT statement."
                    )

    assert not violations, "🚨 Supabase 10/30 Data API 違規：\n" + "\n".join(violations)

def test_sentinel_catches_unauthenticated_table_without_grants():
    """
    Validates that the regex parser accurately detects a table missing GRANT or RLS.
    """
    vulnerable_sql = """
    CREATE TABLE public.vulnerable_passwords (
        id UUID PRIMARY KEY,
        secret TEXT
    );
    """
    tables = TABLE_CREATE_PATTERN.findall(vulnerable_sql)
    assert "vulnerable_passwords" in tables
    
    grant_pattern = re.compile(
        r"GRANT\s+[\s\S]*?ON\s+(?:TABLE\s+)?(?:public\.)?vulnerable_passwords\s+TO\s+[^;]*(?:authenticated|service_role)",
        re.IGNORECASE
    )
    rls_pattern = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?vulnerable_passwords\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        re.IGNORECASE
    )
    assert not grant_pattern.search(vulnerable_sql)
    assert not rls_pattern.search(vulnerable_sql)

    hardened_sql = """
    CREATE TABLE public.vulnerable_passwords (id UUID PRIMARY KEY);
    ALTER TABLE IF EXISTS public.vulnerable_passwords ENABLE ROW LEVEL SECURITY;
    GRANT SELECT, INSERT
    ON public.vulnerable_passwords
    TO anon, authenticated;
    """
    assert grant_pattern.search(hardened_sql)
    assert rls_pattern.search(hardened_sql)



