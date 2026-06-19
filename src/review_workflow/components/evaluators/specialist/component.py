from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.utils import load_model_from_provider
from src.review_workflow.engine.token_usage import add as token_usage_add
from src.core.providers import resolve_provider_config
from strands import Agent, tool


class Specialist(BaseComponent):
    def as_tool(
        self,
        collection_name: str,
        review_process_name: str,
        checklist_name: str,
        paper_name: str,
        log_callback=None,
        token_usage_accumulator=None,
        collections_root=None,
    ):
        topic = self.config.get("topic", "")

        @tool(name="specialist")
        def specialist_tool(text: str) -> str:
            f"""
            Analyze and answer questions by leveraging specialist expertise within the specified topic: {topic}.

            Use this tool when you need focused review, critique, or assessment that is strictly limited to {topic}. The tool interprets and analyzes the given text by referencing best practices, current knowledge, or relevant frameworks within the topic domain.

            This tool is typically used during detailed review processes, peer assessments, or when specialized domain knowledge is necessary to accurately interpret or critique the provided content.

            Example use cases:
                - Evaluating scientific, technical, or creative work based on topic-specific criteria
                - Summarizing strengths and weaknesses in submissions with respect to {topic}
                - Providing improvement suggestions grounded in topic expertise
                - Identifying missing, incorrect, or ambiguous information unique to {topic}

            Notes:
                - All analysis and feedback will be strictly limited to the defined topic area: {topic}
                - The level of detail depends on the input text and configured criteria
                - Not intended for general review; for broad analysis, use a standard evaluation tool

            Args:
                text: Required. The content, response, or material to be analyzed by the specialist.
                      Example: "This section describes the model architecture and its advantages."

            Returns:
                A concise, topic-focused analysis of the input text, referencing relevant criteria or standards for {topic}.
            """
            return self.execute_tool(
                text, collection_name, review_process_name, checklist_name, paper_name, log_callback, token_usage_accumulator
            )

        return specialist_tool

    def execute_tool(
        self,
        text: str,
        collection_name: str,
        review_process_name: str,
        checklist_name: str,
        paper_name: str,
        log_callback=None,
        token_usage_accumulator=None,
    ) -> str:
        def get_provider_config(provider_id: str):
            return resolve_provider_config(provider_id)

        def create_agent() -> Agent:
            provider_id = self.config.get("provider_id")
            if not provider_id:
                raise ValueError("No provider_id configured for Specialist")

            provider_config = get_provider_config(provider_id)
            criteria = self.config.get("criteria", "")
            topic = self.config.get("topic", "")
            system_prompt = f"""You are a specialist expert. You answer and analyze only within this topic: {topic}.\n
                                Your task is to analyze the given text based on the following criteria: \n\n{criteria}.\n\n
                                Return a concise description of your analysis with details."""

            model = load_model_from_provider(provider_config)
            return Agent(model=model, system_prompt=system_prompt)

        if log_callback:
            log_callback("Using Specialist tool", "info")

        agent = create_agent()
        response = agent(f"Analyze this content within your topic: {text}")
        if token_usage_accumulator is not None:
            token_usage_add(token_usage_accumulator, response, agent)
        return response.text if hasattr(response, "text") else str(response)
