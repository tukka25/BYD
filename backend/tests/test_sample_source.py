"""The planner reads a sample of each table; the sample has to look like the table.

On the Spotify table, stored sorted by genre, the first 2,000 rows were 1,991
pop and 9 rap, so the planner was told the data had 2 genres when it had 6.
"""
import pandas as pd

from app.api.v1.endpoints import comparison
from app.models.data_source import DataSourceType
from app.services import db_sources
from app.services.agents.architect import sample_source

GENRES = ["edm", "latin", "pop", "r&b", "rap", "rock"]


def _sorted_by_genre(per_genre: int = 1000) -> pd.DataFrame:
    """6,000 rows grouped by genre, the way the Spotify table is stored."""
    genres = [genre for genre in GENRES for _ in range(per_genre)]
    return pd.DataFrame({"row": range(len(genres)), "genre": genres, "popularity": range(len(genres))})


def _csv(tmp_path, frame: pd.DataFrame) -> dict:
    path = tmp_path / "songs.csv"
    frame.to_csv(path, index=False)
    return {"type": "file", "name": "songs.csv", "path": str(path)}


def test_a_sorted_file_is_sampled_from_all_its_rows(tmp_path):
    sample = sample_source(_csv(tmp_path, _sorted_by_genre()), str(tmp_path), rows=2000)
    assert len(sample) == 2000
    assert sorted(sample["genre"].unique()) == GENRES


def test_the_sample_is_the_same_on_every_run(tmp_path):
    # The profile becomes the planner's prompt; a different sample each run is a different prompt.
    source = _csv(tmp_path, _sorted_by_genre())
    first = sample_source(source, str(tmp_path), rows=2000)
    second = sample_source(source, str(tmp_path), rows=2000)
    assert first["row"].tolist() == second["row"].tolist()


def test_sampled_rows_keep_their_order(tmp_path):
    sample = sample_source(_csv(tmp_path, _sorted_by_genre()), str(tmp_path), rows=2000)
    assert sample["row"].is_monotonic_increasing


def test_a_table_smaller_than_the_sample_comes_back_whole(tmp_path):
    small = _sorted_by_genre(per_genre=5)
    sample = sample_source(_csv(tmp_path, small), str(tmp_path), rows=2000)
    assert sample["row"].tolist() == list(range(30))


def test_a_database_table_is_sampled_from_all_its_rows(monkeypatch):
    monkeypatch.setattr(db_sources, "load_table_by_id", lambda source_id, table: _sorted_by_genre())
    sample = sample_source({"type": "db", "source_id": "s1", "table": "tracks"}, "", rows=2000)
    assert len(sample) == 2000
    assert sorted(sample["genre"].unique()) == GENRES


def test_the_comparison_samples_a_database_table_from_all_its_rows(monkeypatch):
    # The comparison keeps 50,000 rows, so the bias shows on a longer table: 60,000 here.
    monkeypatch.setattr(db_sources, "tables_with_columns", lambda source, limit: [{"table": "tracks"}])
    monkeypatch.setattr(db_sources, "load_table", lambda source, table: _sorted_by_genre(per_genre=10_000))
    source = type("Source", (), {"source_type": DataSourceType.DB, "display_name": "Spotify"})()
    frame, label = comparison._load(source, "tracks")
    assert sorted(frame["genre"].unique()) == GENRES
