"""The initContainer script that keeps backend pods waiting until migrations have run."""

from __future__ import annotations

from scripts.wait_for_schema import current_revision, expected_head, main, wait

UNREACHABLE = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none"


def test_expected_head_is_the_newest_migration():
    assert expected_head() == "0002_triage_correction"


async def test_unreachable_database_counts_as_not_migrated():
    assert await current_revision(UNREACHABLE) is None


async def test_times_out_instead_of_passing_when_schema_is_missing():
    assert await wait(UNREACHABLE, timeout=0) is False


def test_missing_database_url_is_an_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["wait_for_schema"])
    assert main() == 1
