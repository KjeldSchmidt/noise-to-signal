from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from data import check_for_data, get_next_item
from evaluate_user_preference import evaluate_data
from human_review import human_review
from state import ShoppingState
from user_preferences import fetch_preferences, update_preferences

checkpointer = SqliteSaver(sqlite3.connect("langgraph.db", check_same_thread=False))

graph = StateGraph(ShoppingState)
graph.add_node("check_for_data", check_for_data)
graph.add_node("fetch_preferences", fetch_preferences)
graph.add_node("evaluate_user_preference", evaluate_data)
graph.add_node("get_next_item", get_next_item)
graph.add_node("human_review", human_review)
graph.add_node("update_preferences", update_preferences)

graph.add_edge(START, "check_for_data")
graph.add_edge("check_for_data", "fetch_preferences")
graph.add_edge("fetch_preferences", "evaluate_user_preference")
graph.add_edge("evaluate_user_preference", "get_next_item")
graph.add_conditional_edges(
    "get_next_item",
    lambda x: "done" if x["current_item"] is None else "human_review",
    {"done": END, "human_review": "human_review"},
)

graph.add_edge("human_review", "update_preferences")
graph.add_edge("update_preferences", "get_next_item")

app = graph.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "thread-1"}}

stream = app.stream_events(
    {"user_id": "kjeld", "user_minimum_enjoyment_prediction": 0.5},  # todo: dynamic user id
    config=config,
    version="v3",
)

while True:
    if not stream.interrupted:
        final_state = stream.output
        break

    interrupt = stream.interrupts[0].value
    user_feedback = input(interrupt)

    stream = app.stream_events(Command(resume=user_feedback), config=config, version="v3")

pprint(final_state)
