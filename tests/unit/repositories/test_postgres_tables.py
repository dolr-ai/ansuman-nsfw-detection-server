from app.repositories.postgres.tables import metadata, nsfw_frame_results, nsfw_video_jobs


def test_metadata_includes_confirmed_postgres_tables() -> None:
    assert set(metadata.tables) == {
        "nsfw_video_jobs",
        "nsfw_frame_results",
        "nsfw_video_results",
        "nsfw_storage_actions",
    }


def test_video_jobs_has_terminal_idempotency_unique_constraint() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in nsfw_video_jobs.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("video_id", "source_object_version", "policy_version") in unique_columns


def test_frame_results_has_job_frame_unique_constraint() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in nsfw_frame_results.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("job_id", "frame_index") in unique_columns

