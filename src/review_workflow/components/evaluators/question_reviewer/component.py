import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from src.review_workflow.engine.base import BaseComponent
from src.core.providers import get_provider, resolve_provider_config

from src.review_workflow.components.evaluators.question_reviewer.models import ReviewResponse, BatchReviewResponse
from src.review_workflow.components.evaluators.question_reviewer.helpers import clean_text_for_encoding
from src.review_workflow.components.evaluators.question_reviewer.file_utils import (
    get_paper_file_paths,
    get_answer_file_path,
    load_existing_answers,
    save_answers
)
from src.review_workflow.components.evaluators.question_reviewer.text_processing import (
    extract_pages_from_markdown,
    enhance_supporting_texts_with_highlighting
)
from src.review_workflow.components.evaluators.question_reviewer.rag_context import prepare_rag_context
from src.review_workflow.components.evaluators.question_reviewer.prompt_builder import (
    build_prompt_with_pages,
    build_batch_prompt
)
from src.review_workflow.components.evaluators.question_reviewer.parsers import (
    extract_response_text,
    fallback_structured_output,
    fallback_batch_structured_output,
    extract_from_text_only,
    extract_batch_from_text_only
)
from src.review_workflow.components.evaluators.question_reviewer.agent_creator import create_review_agent
from src.review_workflow.engine.token_usage import add as token_usage_add

class QuestionReviewer(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs.get("collection_name")
        review_process_name = inputs.get("review_process_name")
        paper_name = inputs.get("paper_name")
        checklist_name = inputs.get("checklist_name")
        question_data = inputs.get("question")
        questions_data = inputs.get("questions")
        log_callback = inputs.get("log_callback")
        
        token_usage_accumulator = inputs.get("token_usage_accumulator")
        collections_root = inputs.get("collections_root")
        if questions_data and isinstance(questions_data, list):
            return self._execute_batch(collection_name, review_process_name, paper_name, checklist_name, questions_data, log_callback, token_usage_accumulator, collections_root)
        
        if not question_data:
            return self._log_error("Either 'question' or 'questions' must be provided", log_callback)
        
        return self._execute_single(collection_name, review_process_name, paper_name, checklist_name, question_data, log_callback, token_usage_accumulator, collections_root)
    
    def _execute_single(self, collection_name: str, review_process_name: str, paper_name: str,
                        checklist_name: str, question_data: Dict[str, Any], log_callback,
                        token_usage_accumulator: Optional[Dict[str, Any]] = None,
                        collections_root: Optional[Path] = None) -> Dict[str, Any]:
        answers_file = get_answer_file_path(collection_name, review_process_name, paper_name, checklist_name, collections_root)
        existing_answers = load_existing_answers(answers_file)

        question_id = question_data.get("id")
        if question_id in existing_answers and not self.config.get("force_review", False):
            return existing_answers[question_id]

        paper_json_path, paper_md_path = get_paper_file_paths(collection_name, review_process_name, paper_name, checklist_name, collections_root)
        
        if not paper_json_path.exists():
            return self._log_error(f"Paper metadata JSON not found: {paper_json_path}", log_callback)
        
        with open(paper_json_path, "r", encoding="utf-8") as f:
            paper_metadata = json.load(f)
        
        method = paper_metadata.get("method", "")
        if method == "Direct File Upload":
            return self._log_error("Direct File Upload method is not yet implemented. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        if not paper_md_path.exists():
            return self._log_error(f"Paper markdown file not found. Method was: '{method}'. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        md_content = paper_md_path.read_text(encoding="utf-8")
        if not md_content.strip():
            return self._log_error(f"Paper content is empty. Method: {method}", log_callback)
        
        md_content = clean_text_for_encoding(md_content)
        paper_pages = extract_pages_from_markdown(md_content)
        question_text = clean_text_for_encoding(question_data.get('text', ''))
        
        context_content, context_pages = prepare_rag_context(
            md_content, paper_pages, question_text, collection_name, 
            review_process_name, paper_name, checklist_name, self.config, log_callback, collections_root
        )
        if isinstance(context_content, str):
            context_content = clean_text_for_encoding(context_content)
        
        provider_config = self._get_provider_config(self.config.get("provider_id"))
        prompt = build_prompt_with_pages(question_text, context_content, context_pages)
        prompt = clean_text_for_encoding(prompt)
        context = {
            "collection_name": collection_name,
            "review_process_name": review_process_name,
            "checklist_name": checklist_name,
            "paper_name": paper_name,
            "log_callback": log_callback,
            "token_usage_accumulator": token_usage_accumulator,
            "collections_root": collections_root,
        }
        agent = create_review_agent(provider_config, self.config, paper_pages, context=context)
        result = self._get_review_result(agent, prompt, provider_config, log_callback, token_usage_accumulator)
        result["question_id"] = question_id
        result["question_text"] = question_data.get("text")
        result["supporting_texts"] = enhance_supporting_texts_with_highlighting(result.get("supporting_texts", []), paper_pages)
        
        existing_answers[question_id] = result
        save_answers(answers_file, existing_answers)

        return result
    
    def _execute_batch(self, collection_name: str, review_process_name: str, paper_name: str,
                       checklist_name: str, questions_data: List[Dict[str, Any]], log_callback,
                       token_usage_accumulator: Optional[Dict[str, Any]] = None,
                       collections_root: Optional[Path] = None) -> Dict[str, Any]:
        answers_file = get_answer_file_path(collection_name, review_process_name, paper_name, checklist_name, collections_root)
        existing_answers = load_existing_answers(answers_file)
        
        force_review = self.config.get("force_review", False)
        questions_to_answer = []
        for q in questions_data:
            question_id = q.get("id")
            if question_id not in existing_answers or force_review:
                questions_to_answer.append(q)
        
        if not questions_to_answer:
            if log_callback:
                log_callback(f"All {len(questions_data)} questions already have answers", "info")
            return {"status": "completed", "answered": 0, "total": len(questions_data)}
        
        paper_json_path, paper_md_path = get_paper_file_paths(collection_name, review_process_name, paper_name, checklist_name, collections_root)
        
        if not paper_json_path.exists():
            return self._log_error(f"Paper metadata JSON not found: {paper_json_path}", log_callback)
        
        with open(paper_json_path, "r", encoding="utf-8") as f:
            paper_metadata = json.load(f)
        
        method = paper_metadata.get("method", "")
        if method == "Direct File Upload":
            return self._log_error("Direct File Upload method is not yet implemented. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        if not paper_md_path.exists():
            return self._log_error(f"Paper markdown file not found. Method was: '{method}'. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        md_content = paper_md_path.read_text(encoding="utf-8")
        if not md_content.strip():
            return self._log_error(f"Paper content is empty. Method: {method}", log_callback)
        
        md_content = clean_text_for_encoding(md_content)
        paper_pages = extract_pages_from_markdown(md_content)
        
        if self.config.get("use_rag", False) and log_callback:
            log_callback("Warning: RAG is not supported in batch mode. Using full paper content instead.", "warning")
        
        context_content = md_content
        context_pages = paper_pages
        
        if isinstance(context_content, str):
            context_content = clean_text_for_encoding(context_content)
        
        provider_config = self._get_provider_config(self.config.get("provider_id"))
        prompt = build_batch_prompt(questions_to_answer, context_content, context_pages)
        prompt = clean_text_for_encoding(prompt)
        context = {
            "collection_name": collection_name,
            "review_process_name": review_process_name,
            "checklist_name": checklist_name,
            "paper_name": paper_name,
            "log_callback": log_callback,
            "token_usage_accumulator": token_usage_accumulator,
            "collections_root": collections_root,
        }
        # Agent (and tools from self.config) is the same as in single mode; tools are used in batch mode too.
        agent = create_review_agent(provider_config, self.config, paper_pages, context=context)
        batch_result = self._get_batch_review_result(agent, prompt, provider_config, questions_to_answer, log_callback, token_usage_accumulator)

        # Guarantee one result per question: index by normalized id and fill missing with error response.
        results_by_id = {}
        for answer_data in batch_result:
            qid = answer_data.get("question_id")
            if qid is not None and qid != "":
                results_by_id[str(qid)] = answer_data

        all_results = []
        for q in questions_to_answer:
            question_id = q.get("id")
            id_canon = str(question_id) if question_id is not None else ""
            answer_data = results_by_id.get(id_canon) if id_canon else None
            if not answer_data:
                if log_callback:
                    log_callback(f"No answer returned for question id {question_id}; using error placeholder", "warning")
                answer_data = self._error_response("Batch did not return an answer for this question.")

            result = {
                "question_id": question_id,
                "question_text": q.get("text"),
                "answer": answer_data.get("answer", False),
                "supporting_texts": enhance_supporting_texts_with_highlighting(
                    answer_data.get("supporting_texts", []), paper_pages
                )
            }
            existing_answers[question_id] = result
            all_results.append(result)

        save_answers(answers_file, existing_answers)

        if log_callback:
            log_callback(f"Successfully answered {len(all_results)} questions", "info")

        return {"status": "completed", "answered": len(all_results), "total": len(questions_data), "results": all_results}

    def _error_response(self, reason: str):
        return {"answer": False, "supporting_texts": [{"page_number": -1, "text_crop": reason, "short_explanation": reason}], "error": reason}

    def _ensure_batch_one_per_question(
        self,
        result_list: List[Dict[str, Any]],
        questions: List[Dict[str, Any]],
        log_callback,
        default_error: str = "No answer returned for this question.",
    ) -> List[Dict[str, Any]]:
        """Ensure exactly one result per question in order; fill missing with error placeholder."""
        by_id = {}
        for r in result_list:
            qid = r.get("question_id")
            if qid is not None and str(qid) not in by_id:
                by_id[str(qid)] = r
        ordered = []
        for q in questions:
            qid = q.get("id")
            id_canon = str(qid) if qid is not None else ""
            r = by_id.get(id_canon)
            if r is not None:
                ordered.append(r)
            else:
                if log_callback:
                    log_callback(f"Filling missing answer for question id {qid}", "warning")
                ordered.append({
                    "question_id": qid,
                    "answer": False,
                    "supporting_texts": [{"page_number": -1, "text_crop": default_error, "short_explanation": default_error}],
                })
        return ordered

    def _log_error(self, error_msg: str, log_callback):
        if log_callback:
            log_callback(f"✗ {error_msg}", "error")
        return self._error_response(error_msg)
    
    def _get_review_result(self, agent, prompt: str, provider_config: Dict[str, Any], log_callback,
                          token_usage_accumulator: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt = clean_text_for_encoding(prompt)
        
        if self.config.get("use_json_fallback", False):
            return fallback_structured_output(agent, prompt, provider_config, token_usage_accumulator)
        
        try:
            prompt = clean_text_for_encoding(str(prompt))
            response = agent(prompt, structured_output_model=ReviewResponse)
            if token_usage_accumulator is not None:
                token_usage_add(token_usage_accumulator, response, agent)
            return response.structured_output.model_dump()
        except Exception as e:
            error_msg = str(e).lower()
            if "structured output" not in error_msg and "structured_output" not in error_msg:
                raise
            
            if log_callback:
                log_callback(f"Structured output failed, attempting fallback parsing", "warning")
            
            try:
                result = fallback_structured_output(agent, prompt, provider_config, token_usage_accumulator)
                if log_callback:
                    log_callback("Successfully parsed response using fallback method", "info")
                return result
            except Exception:
                if log_callback:
                    log_callback("Fallback parsing failed, trying simplified extraction...", "warning")
                try:
                    result = extract_from_text_only(agent, prompt, provider_config, token_usage_accumulator)
                    if log_callback:
                        log_callback("Successfully extracted response using text-only method", "info")
                    return result
                except Exception as text_error:
                    error_detail = f"Structured output failed: {str(e)}. All fallback methods failed. Last error: {str(text_error)}"
                    if log_callback:
                        log_callback(error_detail, "error")
                    return self._error_response(error_detail)
    
    def _get_batch_review_result(self, agent, prompt: str, provider_config: Dict[str, Any],
                                  questions: List[Dict[str, Any]], log_callback,
                                  token_usage_accumulator: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        prompt = clean_text_for_encoding(prompt)
        
        if self.config.get("use_json_fallback", False):
            return fallback_batch_structured_output(agent, prompt, provider_config, questions, token_usage_accumulator)
        
        try:
            prompt = clean_text_for_encoding(str(prompt))
            response = agent(prompt, structured_output_model=BatchReviewResponse)
            if token_usage_accumulator is not None:
                token_usage_add(token_usage_accumulator, response, agent)
            batch_response = response.structured_output.model_dump()
            
            answers = batch_response.get("answers", [])
            result_list = []
            for answer in answers:
                result_list.append({
                    "question_id": answer.get("question_id", ""),
                    "answer": answer.get("answer", False),
                    "supporting_texts": answer.get("supporting_texts", [])
                })

            # Normalize IDs to str so "1" and 1 match when comparing
            answered_ids = {str(a.get("question_id", "")) for a in result_list}
            question_ids = {str(q.get("id", "")) for q in questions}
            missing_ids = question_ids - answered_ids

            if missing_ids and log_callback:
                log_callback(f"Warning: {len(missing_ids)} questions not answered in batch response. Attempting fallback.", "warning")
                for missing_id in missing_ids:
                    question = next((q for q in questions if str(q.get("id", "")) == missing_id), None)
                    if question:
                        raw_id = question.get("id")
                        single_prompt = f"Question (ID: {raw_id}): {question.get('text', '')}\n\n{prompt.split('Paper Content')[0] if 'Paper Content' in prompt else ''}"
                        try:
                            single_response = agent(single_prompt, structured_output_model=ReviewResponse)
                            if token_usage_accumulator is not None:
                                token_usage_add(token_usage_accumulator, single_response, agent)
                            single_result = single_response.structured_output.model_dump()
                            result_list.append({
                                "question_id": raw_id,
                                "answer": single_result.get("answer", False),
                                "supporting_texts": single_result.get("supporting_texts", [])
                            })
                        except Exception as e:
                            if log_callback:
                                log_callback(f"Failed to answer question {raw_id} in fallback: {str(e)}", "error")
                            result_list.append({
                                "question_id": raw_id,
                                "answer": False,
                                "supporting_texts": [{"page_number": -1, "text_crop": f"Failed to answer: {str(e)}", "short_explanation": "Error during batch processing"}]
                            })

            return self._ensure_batch_one_per_question(result_list, questions, log_callback)
            
        except Exception as e:
            error_msg = str(e).lower()
            if "structured output" not in error_msg and "structured_output" not in error_msg:
                raise
            
            if log_callback:
                log_callback(f"Structured output failed for batch, attempting fallback parsing", "warning")
            
            try:
                result = fallback_batch_structured_output(agent, prompt, provider_config, questions, token_usage_accumulator)
                if log_callback:
                    log_callback("Successfully parsed batch response using fallback method", "info")
                return self._ensure_batch_one_per_question(result, questions, log_callback)
            except Exception:
                if log_callback:
                    log_callback("Fallback parsing failed, trying simplified extraction...", "warning")
                try:
                    result = extract_batch_from_text_only(agent, prompt, provider_config, questions, token_usage_accumulator)
                    if log_callback:
                        log_callback("Successfully extracted batch response using text-only method", "info")
                    return self._ensure_batch_one_per_question(result, questions, log_callback)
                except Exception as text_error:
                    error_detail = f"Batch structured output failed: {str(e)}. All fallback methods failed. Last error: {str(text_error)}"
                    if log_callback:
                        log_callback(error_detail, "error")
                    return self._ensure_batch_one_per_question([], questions, log_callback, default_error=error_detail)

    def _get_provider_config(self, provider_id):
        try:
            return resolve_provider_config(provider_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


if __name__ == "__main__":
    mock_question = {
        "text": "Does the paper propose a new neural network architecture?",
        "type": "text",
        "id": "1",
    }
    
    config = {
        "provider_id": "5a5b024d-5d7f-4aa9-b7c8-8350951d755b",
        # "system_prompt": "You are supposed to answer the questions based on the paper content.",
        "force_review": True,
        "use_rag": False,
        "rag_top_k": 3,
        "rag_force_recreate": True,
        "rag_chunking_strategy": "page",
    }
    
    reviewer = QuestionReviewer(config=config)
    result = reviewer.execute({
        "collection_name": "ml_papers",
        "review_process_name": "Demo Review Process",
        "paper_name": "EDITING MODELS WITH TASK ARITHMETIC.pdf",
        "question": mock_question,
    })
    print(json.dumps(result, indent=2))
