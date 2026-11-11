import json

from llm_model import get_model
from state import EvaluationResults, ShoppingState


def evaluate_data(state: ShoppingState) -> ShoppingState:
    strcutured_model = get_model().with_structured_output(EvaluationResults)
    evaluation = strcutured_model.invoke(
        f"""
        Instruction: Evaluate whether the movies described here should be recommended to the end user.
        
        This is the data to evaluate: {json.dumps(state["data"])}

        These are the users relevant preferences: {json.dumps(state["relevant_preferences"])}
        """
    )

    return {"evaluations": evaluation}
