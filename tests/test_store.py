"""The runs database keeps the last checkpoint of each run, and a run goes on from it."""

import sqlite3
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from vault_watch_agent import store


class State(TypedDict, total=False):
    text: str
    answer: str


def graph(saver):
    """Three steps, a pause before the last one: the shape of a run with its review."""
    g = StateGraph(State)
    g.add_node("write", lambda s: {"text": "x" * 900_000})
    g.add_node("ask", lambda s: {"answer": interrupt({"step": "review"})})
    g.add_node("end", lambda s: {"text": s["text"][:10] + s["answer"]})
    g.add_edge(START, "write")
    g.add_edge("write", "ask")
    g.add_edge("ask", "end")
    g.add_edge("end", END)
    return g.compile(checkpointer=saver)


def count(db, table):
    with sqlite3.connect(db) as c:
        return dict(c.execute(f"SELECT thread_id, COUNT(*) FROM {table} GROUP BY thread_id").fetchall())


def test_only_the_last_checkpoint_of_a_run_is_kept_and_the_run_goes_on_from_it(tmp_path):
    db = tmp_path / "checkpoints.sqlite"
    assert store.tidy(db) == {"checkpoints": 0, "writes": 0, "freed": 0}  # no database yet: nothing, no error
    with SqliteSaver.from_conn_string(str(db)) as saver:
        app = graph(saver)
        for thread in ("paused", "other"):
            app.invoke({"text": ""}, {"configurable": {"thread_id": thread}})  # stops at the pause
        cfg = {"configurable": {"thread_id": "paused"}}
        before = app.get_state(cfg)
        assert before.next == ("ask",) and count(db, "checkpoints")["paused"] >= 3
    size = store.weight(db)
    done = store.tidy(db)
    assert done["checkpoints"] >= 4 and done["writes"] >= 1
    assert done["freed"] > 1_000_000 and store.weight(db) == size - done["freed"]  # the space is given back to the disk
    assert count(db, "checkpoints") == {"paused": 1, "other": 1}
    assert store.tidy(db) == {"checkpoints": 0, "writes": 0, "freed": 0}  # tidy already: nothing more
    with SqliteSaver.from_conn_string(str(db)) as saver:
        app = graph(saver)
        after = app.get_state(cfg)
        # The run as it was: its state, where it waits, what it asks
        assert after.values == before.values and after.next == before.next
        assert [i.value for t in after.tasks for i in t.interrupts] == [{"step": "review"}]
        assert app.invoke(Command(resume="!"), cfg)["text"] == "x" * 10 + "!"  # and it goes on from there
        assert app.get_state({"configurable": {"thread_id": "other"}}).next == ("ask",)
    store.tidy(db)
    assert count(db, "checkpoints") == {"paused": 1, "other": 1}


def test_a_database_that_is_not_one_is_left_alone(tmp_path):
    db = tmp_path / "checkpoints.sqlite"
    db.write_text("not a database", encoding="utf-8")
    assert store.tidy(db) == {"checkpoints": 0, "writes": 0, "freed": 0} and db.read_text(encoding="utf-8") == "not a database"
    empty = tmp_path / "empty.sqlite"
    sqlite3.connect(empty).close()
    assert store.tidy(empty) == {"checkpoints": 0, "writes": 0, "freed": 0}  # no table yet
