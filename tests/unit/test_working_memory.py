"""Unit tests for aletheia.memory.working_memory.

These tests use a real SQLite file in pytest's tmp_path (no mocks).
store_observation and store_critique always stamp "now", so tests that
depend on time order or age write the timestamp directly with raw SQL.
"""

from __future__ import annotations

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone

import pytest

from aletheia.memory.working_memory import AgentObservation, WorkingMemory


@pytest.fixture
def wm(tmp_path):
    """A WorkingMemory backed by a fresh database file."""
    return WorkingMemory(db_path=tmp_path / "wm.db")


def hours_ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def insert_obs(
    wm: WorkingMemory,
    *,
    agent: str = "oracle",
    ticker: str = "RELIANCE",
    text: str = "obs",
    timestamp: str | None = None,
    metadata: str | None = "{}",
    confidence: float = 0.5,
) -> int:
    """Insert one observation row with a chosen timestamp (ISO string)."""
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    with closing(wm._conn()) as conn:
        cur = conn.execute(
            "INSERT INTO agent_observations "
            "(agent_name, ticker, observation, confidence, timestamp, run_id, metadata) "
            "VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (agent, ticker, text, confidence, timestamp, metadata),
        )
        conn.commit()
        return cur.lastrowid


def set_critique_time(wm: WorkingMemory, critique_id: int, when: datetime) -> None:
    """Overwrite the timestamp of a stored critique."""
    with closing(wm._conn()) as conn:
        conn.execute(
            "UPDATE agent_critiques SET timestamp = ? WHERE id = ?",
            (when.isoformat(), critique_id),
        )
        conn.commit()


def set_observation_time(wm: WorkingMemory, obs_id: int, when: datetime) -> None:
    """Overwrite the timestamp of a stored observation."""
    with closing(wm._conn()) as conn:
        conn.execute(
            "UPDATE agent_observations SET timestamp = ? WHERE id = ?",
            (when.isoformat(), obs_id),
        )
        conn.commit()


class TestInit:
    def test_creates_missing_parent_folders(self, tmp_path):
        db_path = tmp_path / "a" / "b" / "wm.db"

        WorkingMemory(db_path=db_path)

        assert db_path.exists()


class TestRetrieveForTicker:
    def test_returns_only_rows_for_given_agent_and_ticker(self, wm):
        insert_obs(wm, agent="oracle", ticker="RELIANCE", text="wanted")
        insert_obs(wm, agent="oracle", ticker="TCS", text="other ticker")
        insert_obs(wm, agent="sentinel", ticker="RELIANCE", text="other agent")

        result = wm.retrieve_for_ticker("oracle", "RELIANCE")

        assert [o.observation for o in result] == ["wanted"]

    def test_lowercase_store_is_found_by_uppercase_read(self, wm):
        wm.store_observation("oracle", "reliance", "stored in lowercase")

        result = wm.retrieve_for_ticker("oracle", "RELIANCE")

        assert [o.observation for o in result] == ["stored in lowercase"]
        assert result[0].ticker == "RELIANCE"

    def test_uppercase_store_is_found_by_lowercase_read(self, wm):
        wm.store_observation("oracle", "RELIANCE", "stored in uppercase")

        result = wm.retrieve_for_ticker("oracle", "reliance")

        assert [o.observation for o in result] == ["stored in uppercase"]

    # The index idx_agent_ticker_ts already returns rows newest first,
    # so this test cannot catch a missing ORDER BY in retrieve_for_ticker.
    def test_returns_newest_first(self, wm):
        insert_obs(wm, text="old", timestamp=hours_ago(3).isoformat())
        insert_obs(wm, text="newest", timestamp=hours_ago(1).isoformat())
        insert_obs(wm, text="middle", timestamp=hours_ago(2).isoformat())

        result = wm.retrieve_for_ticker("oracle", "RELIANCE")

        assert [o.observation for o in result] == ["newest", "middle", "old"]

    def test_respects_limit(self, wm):
        for hours in (3, 1, 4, 2):
            insert_obs(wm, text=f"{hours}h", timestamp=hours_ago(hours).isoformat())

        result = wm.retrieve_for_ticker("oracle", "RELIANCE", limit=2)

        assert [o.observation for o in result] == ["1h", "2h"]

    def test_excludes_rows_older_than_max_age_days(self, wm):
        insert_obs(wm, text="too old", timestamp=hours_ago(10 * 24).isoformat())
        insert_obs(wm, text="recent", timestamp=hours_ago(2 * 24).isoformat())

        result = wm.retrieve_for_ticker("oracle", "RELIANCE", max_age_days=5)

        assert [o.observation for o in result] == ["recent"]

    def test_default_max_age_is_14_days(self, wm):
        insert_obs(wm, text="13 days", timestamp=hours_ago(13 * 24).isoformat())
        insert_obs(wm, text="15 days", timestamp=hours_ago(15 * 24).isoformat())

        result = wm.retrieve_for_ticker("oracle", "RELIANCE")

        assert [o.observation for o in result] == ["13 days"]

    def test_returns_agent_observation_with_fields_round_tripped(self, wm):
        row_id = wm.store_observation(
            "oracle",
            "RELIANCE",
            "strong earnings",
            confidence=0.8,
            run_id="run-42",
            metadata={"source": "10-K", "score": 3},
        )
        stored_at = hours_ago(3)
        set_observation_time(wm, row_id, stored_at)
        (obs,) = wm.retrieve_for_ticker("oracle", "RELIANCE")
        assert isinstance(obs, AgentObservation)
        assert obs.id == row_id
        assert obs.agent_name == "oracle"
        assert obs.ticker == "RELIANCE"
        assert obs.observation == "strong earnings"
        assert obs.confidence == pytest.approx(0.8)
        assert obs.run_id == "run-42"
        assert obs.metadata == {"source": "10-K", "score": 3}
        assert obs.timestamp == stored_at


class TestRetrieveRecent:
    def test_returns_rows_across_tickers_for_one_agent_only(self, wm):
        insert_obs(wm, agent="oracle", ticker="RELIANCE", text="apple")
        insert_obs(wm, agent="oracle", ticker="TCS", text="microsoft")
        insert_obs(wm, agent="sentinel", ticker="RELIANCE", text="other agent")

        result = wm.retrieve_recent("oracle")

        assert {o.observation for o in result} == {"apple", "microsoft"}

    def test_returns_newest_first(self, wm):
        insert_obs(wm, ticker="RELIANCE", text="old", timestamp=hours_ago(3).isoformat())
        insert_obs(wm, ticker="TCS", text="newest", timestamp=hours_ago(1).isoformat())
        insert_obs(wm, ticker="INFY", text="middle", timestamp=hours_ago(2).isoformat())

        result = wm.retrieve_recent("oracle")

        assert [o.observation for o in result] == ["newest", "middle", "old"]

    def test_respects_limit(self, wm):
        for hours in (3, 1, 4, 2):
            insert_obs(wm, text=f"{hours}h", timestamp=hours_ago(hours).isoformat())

        result = wm.retrieve_recent("oracle", limit=2)

        assert [o.observation for o in result] == ["1h", "2h"]

    def test_has_no_age_filter(self, wm):
        insert_obs(wm, text="ancient", timestamp=hours_ago(365 * 24).isoformat())

        result = wm.retrieve_recent("oracle")

        assert [o.observation for o in result] == ["ancient"]


class TestListAllObservations:
    def test_without_filters_returns_rows_of_all_agents(self, wm):
        insert_obs(wm, agent="oracle", text="from oracle")
        insert_obs(wm, agent="sentinel", text="from sentinel")

        result = wm.list_all_observations()

        assert {r["observation"] for r in result} == {"from oracle", "from sentinel"}

    def test_filters_by_agent(self, wm):
        insert_obs(wm, agent="oracle", text="mine")
        insert_obs(wm, agent="sentinel", text="not mine")

        result = wm.list_all_observations(agent_name="oracle")

        assert [r["observation"] for r in result] == ["mine"]

    def test_filters_by_ticker_in_any_case(self, wm):
        insert_obs(wm, ticker="RELIANCE", text="apple")
        insert_obs(wm, ticker="TCS", text="microsoft")

        result = wm.list_all_observations(ticker="reliance")

        assert [r["observation"] for r in result] == ["apple"]

    def test_combines_agent_and_ticker_filters(self, wm):
        insert_obs(wm, agent="oracle", ticker="RELIANCE", text="wanted")
        insert_obs(wm, agent="oracle", ticker="TCS", text="other ticker")
        insert_obs(wm, agent="sentinel", ticker="RELIANCE", text="other agent")

        result = wm.list_all_observations(agent_name="oracle", ticker="RELIANCE")

        assert [r["observation"] for r in result] == ["wanted"]

    def test_returns_newest_first_and_respects_limit(self, wm):
        for hours in (3, 1, 4, 2):
            insert_obs(wm, text=f"{hours}h", timestamp=hours_ago(hours).isoformat())

        result = wm.list_all_observations(limit=2)

        assert [r["observation"] for r in result] == ["1h", "2h"]


class TestRowToObsFallbacks:
    def test_invalid_timestamp_falls_back_to_recent_datetime(self, wm):
        insert_obs(wm, text="bad time", timestamp="not-a-date")
        before = datetime.now(UTC)

        (obs,) = wm.retrieve_recent("oracle")
        after = datetime.now(UTC)
        assert obs.observation == "bad time"
        assert isinstance(obs.timestamp, datetime)
        assert before <= obs.timestamp <= after

    def test_invalid_json_metadata_becomes_empty_dict(self, wm):
        insert_obs(wm, text="bad meta", metadata="{not valid json")

        (obs,) = wm.retrieve_recent("oracle")

        assert obs.observation == "bad meta"
        assert obs.metadata == {}

    def test_null_metadata_becomes_empty_dict(self, wm):
        insert_obs(wm, text="null meta", metadata=None)
        (obs,) = wm.retrieve_recent("oracle")

        assert obs.metadata == {}


class TestGetCritiques:
    def test_returns_newest_first(self, wm):
        new_id = wm.store_critique("oracle", "new critique")
        old_id = wm.store_critique("oracle", "old critique")

        set_critique_time(wm, old_id, hours_ago(5))
        set_critique_time(wm, new_id, hours_ago(1))

        result = wm.get_critiques("oracle")

        assert [c["critique"] for c in result] == ["new critique", "old critique"]
        assert new_id != old_id and new_id > 0

    def test_returns_only_critiques_of_given_agent(self, wm):
        wm.store_critique("oracle", "mine")
        wm.store_critique("sentinel", "not mine")

        result = wm.get_critiques("oracle")

        assert [c["critique"] for c in result] == ["mine"]

    def test_respects_limit(self, wm):
        for hours in (3, 1, 4, 2):
            critique_id = wm.store_critique("oracle", f"{hours}h")
            set_critique_time(wm, critique_id, hours_ago(hours))

        result = wm.get_critiques("oracle", limit=2)

        assert [c["critique"] for c in result] == ["1h", "2h"]

    def test_returns_empty_list_when_agent_has_no_critiques(self, wm):
        assert wm.get_critiques("oracle") == []


class TestGetLatestCritique:
    def test_returns_none_when_there_are_no_critiques(self, wm):
        assert wm.get_latest_critique("oracle") is None

    def test_returns_the_newest_critique(self, wm):
        new_id = wm.store_critique("oracle", "new critique")
        old_id = wm.store_critique("oracle", "old critique")

        set_critique_time(wm, old_id, hours_ago(5))
        set_critique_time(wm, new_id, hours_ago(1))

        assert wm.get_latest_critique("oracle") == "new critique"
        assert new_id != old_id and new_id > 0


class TestBuildMemoryContext:
    def test_returns_empty_string_when_no_data(self, wm):
        assert wm.build_memory_context("oracle", "RELIANCE") == ""

    def test_includes_header_and_observation_text(self, wm):
        wm.store_observation("oracle", "RELIANCE", "strong earnings", confidence=0.9)

        context = wm.build_memory_context("oracle", "RELIANCE")

        assert "RELEVANT PAST OBSERVATIONS (same ticker):" in context
        assert "strong earnings" in context
        assert "confidence=0.90]" in context

    def test_includes_critique_section_when_present(self, wm):
        wm.store_observation("oracle", "RELIANCE", "strong earnings")
        wm.store_critique("oracle", "be less optimistic")

        context = wm.build_memory_context("oracle", "RELIANCE")

        assert "YOUR RECENT SELF-CRITIQUE:" in context
        assert "be less optimistic" in context
        assert "Apply these insights to your current analysis." in context

    def test_works_with_only_a_critique_and_no_observations(self, wm):
        wm.store_critique("oracle", "be less optimistic")

        context = wm.build_memory_context("oracle", "RELIANCE")

        assert "RELEVANT PAST OBSERVATIONS" not in context
        assert "be less optimistic" in context

    def test_omits_critique_section_when_there_is_no_critique(self, wm):
        wm.store_observation("oracle", "RELIANCE", "strong earnings")

        context = wm.build_memory_context("oracle", "RELIANCE")

        assert "SELF-CRITIQUE" not in context

    def test_respects_limit(self, wm):
        for hours in (3, 1, 4, 2):
            insert_obs(wm, text=f"note-{hours}", timestamp=hours_ago(hours).isoformat())

        context = wm.build_memory_context("oracle", "RELIANCE", limit=1)

        assert "note-1" in context
        assert "note-2" not in context
        assert "note-3" not in context

    def test_full_text_has_observations_newest_first_then_critique(self, wm):
        insert_obs(wm, text="older note", timestamp=hours_ago(5).isoformat())
        insert_obs(wm, text="newer note", timestamp=hours_ago(2).isoformat())
        wm.store_critique("oracle", "be less optimistic")

        context = wm.build_memory_context("oracle", "RELIANCE")

        assert context == (
            "RELEVANT PAST OBSERVATIONS (same ticker):\n"
            "[ORACLE | RELIANCE | 2h ago | confidence=0.50]\n"
            "newer note\n"
            "[ORACLE | RELIANCE | 5h ago | confidence=0.50]\n"
            "older note\n"
            "\n"
            "YOUR RECENT SELF-CRITIQUE:\n"
            "be less optimistic\n"
            "Apply these insights to your current analysis."
        )


class TestAgentObservation:
    def test_as_prompt_text_upper_cases_agent_but_not_ticker(self):
        obs = AgentObservation(
            agent_name="oracle",
            ticker="reliance",
            observation="strong earnings",
            confidence=0.5,
            timestamp=hours_ago(3),
        )

        text = obs.as_prompt_text()

        assert text.startswith("[ORACLE | reliance | 3h ago | confidence=0.50]")
        assert text.endswith("\nstrong earnings")

    def test_as_prompt_text_formats_confidence_to_two_decimals(self):
        obs = AgentObservation("oracle", "RELIANCE", "x", 0.123456, hours_ago(1))

        assert "confidence=0.12]" in obs.as_prompt_text()

    def test_metadata_defaults_to_empty_dict_when_none(self):
        obs = AgentObservation("oracle", "RELIANCE", "x", 0.5, hours_ago(1), metadata=None)

        assert obs.metadata == {}

    def test_metadata_is_kept_when_given(self):
        obs = AgentObservation("oracle", "RELIANCE", "x", 0.5, hours_ago(1), metadata={"k": 1})

        assert obs.metadata == {"k": 1}

    def test_as_prompt_text_works_with_naive_timestamp(self):
        naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        obs = AgentObservation("oracle", "RELIANCE", "x", 0.5, naive)

        assert "2h ago" in obs.as_prompt_text()

    @pytest.mark.xfail(
        strict=True,
        reason="as_prompt_text replaces a non-UTC offset instead of converting it",
    )
    def test_as_prompt_text_converts_non_utc_offset(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        three_hours_ago_ist = hours_ago(3).astimezone(ist)
        obs = AgentObservation("oracle", "RELIANCE", "x", 0.5, three_hours_ago_ist)

        assert "3h ago" in obs.as_prompt_text()


class TestStoreObservation:
    @staticmethod
    def raw_metadata(wm):
        with closing(wm._conn()) as conn:
            return conn.execute("SELECT metadata FROM agent_observations").fetchone()["metadata"]

    def test_saves_metadata_as_json_text(self, wm):
        wm.store_observation("oracle", "RELIANCE", "x", metadata={"a": 1})

        assert json.loads(self.raw_metadata(wm)) == {"a": 1}

    def test_saves_missing_metadata_as_empty_json_object(self, wm):
        wm.store_observation("oracle", "RELIANCE", "x", metadata=None)

        assert self.raw_metadata(wm) == "{}"
