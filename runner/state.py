from typing import TypedDict

from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    show_to_user: bool = Field(
        description="Decides whether human-in-the-loop feedback is requested. Should be True if the user is reasonably likely to like the movie, and False if they are unlikely to like it."
    )
    title: str = Field(description="The title of the movie.")
    reason: str = Field(
        description="A short summary of why this might be relevant to the user. Must be addressed to the user in the second person, e.g. 'You might like this movie because...', rather than 'This movie is relevant to the user because...'."
    )
    pro_arguments: list[str] = Field(
        description="A list of arguments in favor of the show_to_user decision."
    )
    con_arguments: list[str] = Field(
        description="A list of arguments against the show_to_user decision."
    )
    enjoyment_prediction: float = Field(
        description="A confidence score between 0 and 1 indicating the confidence in the show_to_user decision. 0 means absolute certainty that the user will not like the movie, and 1 means absolute certainty that the user will like the movie. This prediction will be used for ranking; it should therefore be nuanced and not biased towards the extremes of the scale."
    )


class EvaluationResults(BaseModel):
    evaluations: list[EvaluationResult]


class ShoppingState(TypedDict):
    data: list
    current_item: EvaluationResult
    evaluations: EvaluationResults
    human_feedback: str
    classification: str
    user_id: str
    relevant_preferences: list[str]
    user_minimum_enjoyment_prediction: float
