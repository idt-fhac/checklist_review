from typing import List
from pydantic import BaseModel, Field


class SupportingTextItem(BaseModel):
    page_number: int = Field(description="Page number (1-indexed) where supporting text is found. Use -1 for analysis-only supporting text that doesn't reference a specific page.")
    text_crop: str = Field(description="Exact verbatim text snippet from the paper that supports the answer. For analysis-only items (page_number=-1), this can be the full analysis text.")
    short_explanation: str = Field(description="A brief explanation of why this supporting text is relevant to the answer. This should be a concise analysis of how the text supports the answer.")


class ReviewResponse(BaseModel):
    answer: bool = Field(description="The answer to the question (True/False)")
    supporting_texts: List[SupportingTextItem] = Field(description="List of supporting text items. Each item should have a page_number (or -1 for analysis-only), text_crop, and short_explanation. At least one item should reference a specific page when possible.")


class QuestionAnswer(BaseModel):
    question_id: str = Field(description="The ID of the question being answered")
    answer: bool = Field(description="The answer to the question (True/False)")
    supporting_texts: List[SupportingTextItem] = Field(description="List of supporting text items. Each item should have a page_number (or -1 for analysis-only), text_crop, and short_explanation. At least one item should reference a specific page when possible.")


class BatchReviewResponse(BaseModel):
    answers: List[QuestionAnswer] = Field(description="List of answers, one for each question. The order must match the order of questions provided.")
