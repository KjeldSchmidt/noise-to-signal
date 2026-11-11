import os

from mem0 import MemoryClient

from state import ShoppingState

client = MemoryClient(api_key=os.getenv("mem0_key"))


def fetch_preferences(state: ShoppingState):
    preferences = client.search(
        f"What opinions might be relevant for the user in regards to this: {state['data']}",
        filters={"user_id": state["user_id"]},
    )

    print(f"Relevant preferences: {preferences}")

    return {"relevant_preferences": preferences}


def update_preferences(state: ShoppingState):
    if not state["human_feedback"]:
        print("No human feedback, skipping update")
        return

    messages = [{"role": "user", "content": f"The user thinks: {state['human_feedback']}"}]

    client.add(messages, user_id=state["user_id"])

    print(f"Updating user preferences based on {state['human_feedback']}")
