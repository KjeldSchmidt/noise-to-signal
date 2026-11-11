from state import EvaluationResults, ShoppingState


def check_for_data(state: ShoppingState) -> ShoppingState:
    return {
        "data": [
            {
                "title": "A Night With Pablo",
                "description": "This movie is largely forgettable, with minor moments of great animation that only make it worthwhile to animation enthusiasts.",
            },
            {
                "title": "Arcane",
                "description": "This show is a masterpiece and a genuine revolution in animation. The art is stunning and the story is engaging. It is widely beloved.",
            },
            {
                "title": "Farting on Faces",
                "description": "This movie is genuinely awful. Under no circumstances should you watch it.",
            },
            {
                "title": "Burning Flowers",
                "description": "This movie is widely regarded as a cultural touchstone that is widely recommended, despite it's low budget showing in the cinematogrophy.",
            },
        ]
    }


def get_next_item(state: ShoppingState) -> ShoppingState:
    evaluations = state["evaluations"].evaluations
    if len(evaluations) == 0:
        return {"current_item": None}

    sorted_evaluations = sorted(evaluations, key=lambda x: x.enjoyment_prediction, reverse=True)

    best_item = sorted_evaluations.pop(0)
    remaining_evaluations = EvaluationResults(evaluations=sorted_evaluations)

    print(
        f"Best item is {best_item.title} with enjoyment prediction: {best_item.enjoyment_prediction}"
    )

    if (
        best_item.enjoyment_prediction < state["user_minimum_enjoyment_prediction"]
        or not best_item.show_to_user
    ):
        return {"current_item": None, "evaluations": remaining_evaluations}

    return {"current_item": best_item, "evaluations": remaining_evaluations}
