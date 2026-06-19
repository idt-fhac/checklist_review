import json
from typing import Dict, Any, List, Optional
from pathlib import Path

from src.review_workflow.engine.base import BaseComponent
from src.core.providers import get_provider, resolve_provider_config

from src.review_workflow.components.evaluators.criterion_evaluator.models import ReviewResponse, BatchReviewResponse
from src.review_workflow.components.evaluators.criterion_evaluator.helpers import clean_text_for_encoding
from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import (
    get_artifact_file_paths,
    get_evaluations_file_path,
    get_persona_evaluations_file_path,
    load_existing_evaluations,
    save_evaluations,
)
from src.review_workflow.components.evaluators.criterion_evaluator.text_processing import (
    extract_pages_from_markdown,
    enhance_supporting_texts_with_highlighting
)
from src.review_workflow.components.evaluators.criterion_evaluator.rag_context import prepare_rag_context
from src.review_workflow.components.evaluators.criterion_evaluator.prompt_builder import (
    build_prompt_with_pages,
    build_batch_prompt
)
from src.review_workflow.components.evaluators.criterion_evaluator.parsers import (
    extract_response_text,
    fallback_structured_output,
    fallback_batch_structured_output,
    extract_from_text_only,
    extract_batch_from_text_only
)
from src.review_workflow.components.evaluators.criterion_evaluator.agent_creator import create_review_agent
from src.review_workflow.engine.token_usage import add as token_usage_add

class CriterionEvaluator(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs["collection_name"]
        pipeline_name = inputs["pipeline_name"]
        artifact_name = inputs["artifact_name"]
        criteria_set_name = inputs["criteria_set_name"]
        criterion = inputs.get("criterion")
        criteria = inputs.get("criteria")
        log_callback = inputs.get("log_callback")
        token_usage_accumulator = inputs.get("token_usage_accumulator")
        collections_root = inputs.get("collections_root")

        if criteria and isinstance(criteria, list):
            return self._execute_batch(
                collection_name, pipeline_name, artifact_name, criteria_set_name,
                criteria, log_callback, token_usage_accumulator, collections_root,
                inputs.get("section_mapping"),
                inputs.get("reference_urls") or [],
            )
        if not criterion:
            return self._log_error("'criterion' or 'criteria' is required", log_callback)
        return self._execute_single(
            collection_name, pipeline_name, artifact_name, criteria_set_name,
            criterion, log_callback, token_usage_accumulator, collections_root,
            inputs.get("section_mapping"),
            inputs.get("reference_urls") or [],
            inputs.get("persona_id"),
            inputs.get("config_override"),
        )
    
    def _append_reference_urls(self, prompt: str, reference_urls: List[str]) -> str:
        if not reference_urls:
            return prompt
        lines = "\n".join(f"- {url}" for url in reference_urls)
        return f"{prompt}\n\nSupplementary reference links provided for this review:\n{lines}\n"
    
    def _apply_section_mapping(
        self,
        md_content: str,
        artifact_pages: List[Dict[str, Any]],
        criterion_id: Any,
        section_mapping: Optional[Dict[str, Any]],
    ):
        if not section_mapping or criterion_id is None:
            return md_content, artifact_pages
        mapped = section_mapping.get(str(criterion_id)) or section_mapping.get(criterion_id)
        if not mapped:
            return md_content, artifact_pages
        excerpt = mapped.get("excerpt")
        if excerpt:
            return clean_text_for_encoding(excerpt), []
        return md_content, artifact_pages

    def _runtime_config(self, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime = dict(self.config)
        if config_override:
            runtime.update(config_override)
        return runtime

    def _resolve_evaluations_file(
        self,
        collection_name: str,
        pipeline_name: str,
        artifact_name: str,
        criteria_set_name: str,
        collections_root: Optional[Path],
        persona_id: Optional[str],
    ) -> Path:
        if persona_id:
            return get_persona_evaluations_file_path(
                collection_name,
                pipeline_name,
                artifact_name,
                persona_id,
                criteria_set_name,
                collections_root,
            )
        return get_evaluations_file_path(
            collection_name, pipeline_name, artifact_name, criteria_set_name, collections_root
        )

    def _execute_single(self, collection_name: str, pipeline_name: str, artifact_name: str,
                        criteria_set_name: str, criterion: Dict[str, Any], log_callback,
                        token_usage_accumulator: Optional[Dict[str, Any]] = None,
                        collections_root: Optional[Path] = None,
                        section_mapping: Optional[Dict[str, Any]] = None,
                        reference_urls: Optional[List[str]] = None,
                        persona_id: Optional[str] = None,
                        config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        evaluations_file = self._resolve_evaluations_file(
            collection_name, pipeline_name, artifact_name, criteria_set_name, collections_root, persona_id
        )
        existing = load_existing_evaluations(evaluations_file)

        criterion_id = criterion.get("id")
        if criterion_id in existing and not self.config.get("force_review", False):
            return existing[criterion_id]

        artifact_json_path, artifact_md_path = get_artifact_file_paths(collection_name, pipeline_name, artifact_name, criteria_set_name, collections_root)
        
        if not artifact_json_path.exists():
            return self._log_error(f"Paper metadata JSON not found: {artifact_json_path}", log_callback)
        
        with open(artifact_json_path, "r", encoding="utf-8") as f:
            artifact_metadata = json.load(f)
        
        method = artifact_metadata.get("method", "")
        if method == "Direct File Upload":
            return self._log_error("Direct File Upload method is not yet implemented. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        if not artifact_md_path.exists():
            return self._log_error(f"Paper markdown file not found. Method was: '{method}'. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        md_content = artifact_md_path.read_text(encoding="utf-8")
        if not md_content.strip():
            return self._log_error(f"Paper content is empty. Method: {method}", log_callback)
        
        md_content = clean_text_for_encoding(md_content)
        artifact_pages = extract_pages_from_markdown(md_content)
        criterion_text = clean_text_for_encoding(criterion.get('description', ''))
        md_content, artifact_pages = self._apply_section_mapping(
            md_content, artifact_pages, criterion_id, section_mapping
        )
        
        context_content, context_pages = prepare_rag_context(
            md_content, artifact_pages, criterion_text, collection_name, 
            pipeline_name, artifact_name, criteria_set_name, self.config, log_callback, collections_root
        )
        if isinstance(context_content, str):
            context_content = clean_text_for_encoding(context_content)
        
        provider_config = self._get_provider_config(self.config.get("provider_id"))
        prompt = build_prompt_with_pages(criterion_text, context_content, context_pages)
        prompt = self._append_reference_urls(prompt, reference_urls or [])
        prompt = clean_text_for_encoding(prompt)
        context = {
            "collection_name": collection_name,
            "pipeline_name": pipeline_name,
            "criteria_set_name": criteria_set_name,
            "artifact_name": artifact_name,
            "log_callback": log_callback,
            "token_usage_accumulator": token_usage_accumulator,
            "collections_root": collections_root,
        }
        runtime_config = self._runtime_config(config_override)
        agent = create_review_agent(provider_config, runtime_config, artifact_pages, context=context)
        result = self._get_review_result(agent, prompt, provider_config, log_callback, token_usage_accumulator)
        result["criterion_id"] = criterion_id
        result["criterion_text"] = criterion.get("description") or criterion.get("text", "")
        if persona_id:
            result["persona_id"] = persona_id
        result["supporting_texts"] = enhance_supporting_texts_with_highlighting(result.get("supporting_texts", []), artifact_pages)
        
        existing_evaluations[criterion_id] = result
        save_evaluations(evaluations_file, existing_evaluations)

        return result
    
    def _execute_batch(self, collection_name: str, pipeline_name: str, artifact_name: str,
                       criteria_set_name: str, criteria: List[Dict[str, Any]], log_callback,
                       token_usage_accumulator: Optional[Dict[str, Any]] = None,
                       collections_root: Optional[Path] = None,
                       section_mapping: Optional[Dict[str, Any]] = None,
                       reference_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        evaluations_file = get_evaluations_file_path(collection_name, pipeline_name, artifact_name, criteria_set_name, collections_root)
        existing_evaluations = load_existing_evaluations(evaluations_file)
        
        force_review = self.config.get("force_review", False)
        questions_to_answer = []
        for q in criteria:
            criterion_id = q.get("id")
            if criterion_id not in existing_evaluations or force_review:
                questions_to_answer.append(q)
        
        if not questions_to_answer:
            if log_callback:
                log_callback(f"All {len(criteria)} questions already have answers", "info")
            return {"status": "completed", "answered": 0, "total": len(criteria)}
        
        artifact_json_path, artifact_md_path = get_artifact_file_paths(collection_name, pipeline_name, artifact_name, criteria_set_name, collections_root)
        
        if not artifact_json_path.exists():
            return self._log_error(f"Paper metadata JSON not found: {artifact_json_path}", log_callback)
        
        with open(artifact_json_path, "r", encoding="utf-8") as f:
            artifact_metadata = json.load(f)
        
        method = artifact_metadata.get("method", "")
        if method == "Direct File Upload":
            return self._log_error("Direct File Upload method is not yet implemented. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        if not artifact_md_path.exists():
            return self._log_error(f"Paper markdown file not found. Method was: '{method}'. Please reprocess the paper with 'Extracted Content' method.", log_callback)
        
        md_content = artifact_md_path.read_text(encoding="utf-8")
        if not md_content.strip():
            return self._log_error(f"Paper content is empty. Method: {method}", log_callback)
        
        md_content = clean_text_for_encoding(md_content)
        artifact_pages = extract_pages_from_markdown(md_content)
        
        if self.config.get("use_rag", False) and log_callback:
            log_callback("Warning: RAG is not supported in batch mode. Using full paper content instead.", "warning")
        
        context_content = md_content
        context_pages = artifact_pages
        
        if isinstance(context_content, str):
            context_content = clean_text_for_encoding(context_content)
        
        provider_config = self._get_provider_config(self.config.get("provider_id"))
        prompt = build_batch_prompt(questions_to_answer, context_content, context_pages)
        prompt = self._append_reference_urls(prompt, reference_urls or [])
        prompt = clean_text_for_encoding(prompt)
        context = {
            "collection_name": collection_name,
            "pipeline_name": pipeline_name,
            "criteria_set_name": criteria_set_name,
            "artifact_name": artifact_name,
            "log_callback": log_callback,
            "token_usage_accumulator": token_usage_accumulator,
            "collections_root": collections_root,
        }
        # Agent (and tools from self.config) is the same as in single mode; tools are used in batch mode too.
        agent = create_review_agent(provider_config, self.config, artifact_pages, context=context)
        batch_result = self._get_batch_review_result(agent, prompt, provider_config, questions_to_answer, log_callback, token_usage_accumulator)

        # Guarantee one result per question: index by normalized id and fill missing with error response.
        results_by_id = {}
        for answer_data in batch_result:
            qid = answer_data.get("criterion_id")
            if qid is not None and qid != "":
                results_by_id[str(qid)] = answer_data

        all_results = []
        for q in questions_to_answer:
            criterion_id = q.get("id")
            id_canon = str(criterion_id) if criterion_id is not None else ""
            answer_data = results_by_id.get(id_canon) if id_canon else None
            if not answer_data:
                if log_callback:
                    log_callback(f"No answer returned for question id {criterion_id}; using error placeholder", "warning")
                answer_data = self._error_response("Batch did not return an answer for this question.")

            result = {
                "criterion_id": criterion_id,
                "criterion_text": q.get("description") or q.get("text", ""),
                "answer": answer_data.get("answer", False),
                "supporting_texts": enhance_supporting_texts_with_highlighting(
                    answer_data.get("supporting_texts", []), artifact_pages
                )
            }
            existing_evaluations[criterion_id] = result
            all_results.append(result)

        save_evaluations(evaluations_file, existing_evaluations)

        if log_callback:
            log_callback(f"Successfully answered {len(all_results)} questions", "info")

        return {"status": "completed", "answered": len(all_results), "total": len(criteria), "results": all_results}

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
            qid = r.get("criterion_id")
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
                    "criterion_id": qid,
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
                    "criterion_id": answer.get("criterion_id", ""),
                    "answer": answer.get("answer", False),
                    "supporting_texts": answer.get("supporting_texts", [])
                })

            # Normalize IDs to str so "1" and 1 match when comparing
            answered_ids = {str(a.get("criterion_id", "")) for a in result_list}
            criterion_ids = {str(q.get("id", "")) for q in questions}
            missing_ids = criterion_ids - answered_ids

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
                                "criterion_id": raw_id,
                                "answer": single_result.get("answer", False),
                                "supporting_texts": single_result.get("supporting_texts", [])
                            })
                        except Exception as e:
                            if log_callback:
                                log_callback(f"Failed to answer question {raw_id} in fallback: {str(e)}", "error")
                            result_list.append({
                                "criterion_id": raw_id,
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
    
    reviewer = CriterionEvaluator(config=config)
    result = reviewer.execute({
        "collection_name": "ml_papers",
        "pipeline_name": "Demo Review Process",
        "artifact_name": "EDITING MODELS WITH TASK ARITHMETIC.pdf",
        "question": mock_question,
    })
    print(json.dumps(result, indent=2))
