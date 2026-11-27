"""The command line's own pieces; the commands themselves are run by the tests of each area."""
from vault_watch_agent import cli


def test_a_run_config_names_its_thread_and_bounds_its_jobs():
    # 1.6.0 to 1.9.0: run_config called itself, so every command that runs the graph from the command line (run,
    # resume, fix, mirror, crosscheck, eval) died of a RecursionError before its first model call. The page has its own.
    assert cli.run_config("issue-77") == {"configurable": {"thread_id": "issue-77"}, "max_concurrency": 4}
    assert cli.run_config("issue-77", jobs=False) == {"configurable": {"thread_id": "issue-77"}}
