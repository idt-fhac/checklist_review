"""
PDF processing utilities for converting PDFs to markdown and extracting metadata.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import pymupdf
    import pymupdf4llm

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    pymupdf = None
    pymupdf4llm = None

from src.review_workflow.engine.utils import load_model_from_provider
from src.web.settings.services import SettingsManager
from strands import Agent
from pydantic import BaseModel, Field

class PDFProcessingError(RuntimeError):
    """Error during PDF processing."""

    pass


# Legacy alias for backward compatibility
PaperProcessingError = PDFProcessingError


def derive_collection_name(folder_path: str) -> str:
    """Derive collection name from folder path."""
    folder = Path(folder_path).expanduser()
    candidate = folder.name or folder.stem
    return candidate or "untitled"


class PaperMetadata(BaseModel):
    """Structured output model for paper metadata extraction."""
    title: str = Field(description="Extract the actual title of the research paper from the first page. This should be the main heading or title text, not a placeholder.")
    abstract: str = Field(description="Extract the abstract text if present on the first page. Look for text under 'Abstract' heading. If not found, use empty string.")
    authors: list[str] = Field(description="Extract the list of author names from the first page. Look for author names typically listed below the title. If not found, use empty list.")


PDF_METADATA_EXTRACTION_METHOD_LLM = "llm"
PDF_METADATA_EXTRACTION_METHOD_RULE_BASED = "rule_based"


def _process_single_page(args: tuple) -> tuple[int, str]:
    """
    Process a single page of a PDF to markdown.
    This function is designed to be called in parallel.
    Imports are done inside to ensure they're available in worker processes.
    
    Args:
        args: Tuple of (pdf_path, page_number)
        
    Returns:
        Tuple of (page_number, markdown_content)
    """
    pdf_path_str, page_num = args
    try:
        # Import inside function for multiprocessing compatibility
        import pymupdf
        import pymupdf4llm
        
        doc = pymupdf.open(pdf_path_str)
        
        # Create a temporary single-page document for this page
        # pymupdf4llm.to_markdown works on documents, so we create a new doc with just this page
        temp_doc = pymupdf.open()  # Create empty document
        temp_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        # Convert to markdown
        md = pymupdf4llm.to_markdown(
            temp_doc,
            page_separators=False,  # No separators needed for single page
            write_images=False,
            write_tables=True,
        )
        
        temp_doc.close()
        doc.close()
        
        return (page_num, md)
    except Exception as e:
        # Return error info instead of raising to allow other pages to continue
        return (page_num, f"ERROR_PROCESSING_PAGE: {str(e)}")


def pdf_to_markdown(pdf_path: Path, output_path: Path, max_workers: int = 4) -> str:
    """
    Convert PDF to markdown using pymupdf4llm with parallel page processing.

    Args:
        pdf_path: Path to the PDF file
        output_path: Path where the markdown file should be saved
        max_workers: Number of parallel workers (default: 4, use None for CPU count)

    Returns:
        The markdown content as a string

    Raises:
        PDFProcessingError: If conversion fails
    """
    if not PYMUPDF_AVAILABLE:
        raise PDFProcessingError(
            "pymupdf and pymupdf4llm are required for PDF processing. Install with: pip install pymupdf pymupdf4llm"
        )

    if not pdf_path.exists():
        raise PDFProcessingError(f"PDF file not found: {pdf_path}")

    try:
        # Open document to get page count
        with pymupdf.open(str(pdf_path)) as doc:
            num_pages = doc.page_count
        
        if num_pages == 0:
            raise PDFProcessingError("PDF has no pages")
        
        # For small PDFs (1-2 pages), use sequential processing to avoid overhead
        if num_pages <= 2:
            with pymupdf.open(str(pdf_path)) as doc:
                md = pymupdf4llm.to_markdown(
                    doc,
                    page_separators=True,
                    write_images=False,
                    write_tables=True,
                )
        else:
            # Process pages in parallel
            pdf_path_str = str(pdf_path)
            page_numbers = list(range(num_pages))
            
            # Use ProcessPoolExecutor for true parallelism (bypasses GIL)
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                # Submit all pages for processing
                future_to_page = {
                    executor.submit(_process_single_page, (pdf_path_str, page_num)): page_num
                    for page_num in page_numbers
                }
                
                # Collect results as they complete
                page_results = {}
                for future in as_completed(future_to_page):
                    page_num, md_content = future.result()
                    page_results[page_num] = md_content
                
                # Combine pages in order with separators
                md_parts = []
                for page_num in sorted(page_results.keys()):
                    page_md = page_results[page_num]
                    # Check for errors
                    if page_md.startswith("ERROR_PROCESSING_PAGE:"):
                        raise PDFProcessingError(f"Error processing page {page_num + 1}: {page_md}")
                    md_parts.append(page_md)
                    if page_num < num_pages - 1:
                        md_parts.append(f"\n--- end of page={page_num} ---\n")
                
                md = "".join(md_parts)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use write_text for slightly better performance than encode + write_bytes
        output_path.write_text(md, encoding="utf-8")

        return md
    except Exception as e:
        raise PDFProcessingError(f"Failed to convert PDF to markdown: {e}") from e


def pdf_to_png(
    pdf_path: Path, output_folder: Path, dpi: int = 200
) -> list[Path]:
    """
    Convert each page of a PDF to a PNG image.

    Args:
        pdf_path: Path to the source PDF.
        output_folder: Directory to save images (e.g. .../paper_pages).
        dpi: Resolution for rendering (default 300).

    Returns:
        List of paths to the saved PNG files (page_1.png, page_2.png, ...).

    Raises:
        PDFProcessingError: If conversion fails or pymupdf is not available.
    """
    if not PYMUPDF_AVAILABLE:
        raise PDFProcessingError(
            "pymupdf is required for PDF to PNG. Install with: pip install pymupdf"
        )
    if not pdf_path.exists():
        raise PDFProcessingError(f"PDF file not found: {pdf_path}")
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    saved: list[Path] = []
    try:
        doc = pymupdf.open(str(pdf_path))
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat)
                filename = f"page_{page_num + 1}.png"
                filepath = output_folder / filename
                pix.save(str(filepath))
                saved.append(filepath)
        finally:
            doc.close()
        return saved
    except Exception as e:
        raise PDFProcessingError(f"Failed to convert PDF to PNG: {e}") from e


def extract_first_page(md_content: str) -> str:
    """
    Extract the ENTIRE first page from markdown content.
    Pages are separated by "--- end of page=N ---" markers.

    Args:
        md_content: Full markdown content

    Returns:
        Content of the entire first page (not cropped)
    """
    # Split by page separators (--- end of page=N ---)
    # The format is: --- end of page=0 ---, --- end of page=1 ---, etc.
    pages = re.split(r"^---\s+end\s+of\s+page=\d+\s+---", md_content, flags=re.MULTILINE)

    if pages:
        # First element is the first page (content before the first separator)
        first_page = pages[0].strip()

        # Return the entire first page without any cropping
        if first_page:
            return first_page

    # Fallback: if no page markers found, return entire content (might be single page or no markers)
    return md_content


def get_pdf_metadata_extraction_method() -> str:
    """Return the configured PDF metadata extraction method."""
    settings = SettingsManager.load_settings()
    method = settings.get(
        "pdf_metadata_extraction_method",
        PDF_METADATA_EXTRACTION_METHOD_LLM,
    )
    if method == PDF_METADATA_EXTRACTION_METHOD_RULE_BASED:
        return PDF_METADATA_EXTRACTION_METHOD_RULE_BASED
    return PDF_METADATA_EXTRACTION_METHOD_LLM


def is_rule_based_pdf_metadata_extraction() -> bool:
    """Return True when PDF metadata should be extracted without an LLM."""
    return get_pdf_metadata_extraction_method() == PDF_METADATA_EXTRACTION_METHOD_RULE_BASED


def _clean_metadata_line(line: str) -> str:
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", line)
    line = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", line)
    line = re.sub(r"<[^>]+>", " ", line)
    line = re.sub(r"^#+\s*", "", line.strip())
    line = re.sub(r"^[\-*]\s+", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" -\t")


def _first_page_lines(first_page_content: str) -> list[str]:
    lines = []
    for raw_line in first_page_content.splitlines():
        line = _clean_metadata_line(raw_line)
        if not line:
            continue
        if line.startswith("---") or line.lower().startswith("page "):
            continue
        lines.append(line)
    return lines


def _abstract_line_index(lines: list[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if re.match(r"(?i)^abstract\b", line):
            return index
    return None


def _is_section_heading(line: str) -> bool:
    return bool(
        re.match(
            r"(?i)^(\d+(\.\d+)*\.?\s+)?("
            r"keywords?|index terms|introduction|background|related work|"
            r"methods?|materials|experiments?|results?|discussion|conclusion|"
            r"acknowledg(e)?ments?|references|appendix"
            r")\b",
            line,
        )
    )


def _extract_rule_based_abstract(lines: list[str]) -> str:
    abstract_index = _abstract_line_index(lines)
    if abstract_index is None:
        return ""

    first_line = re.sub(r"(?i)^abstract\b[:.\-\s]*", "", lines[abstract_index]).strip()
    abstract_parts = [first_line] if first_line else []

    for line in lines[abstract_index + 1:]:
        if _is_section_heading(line):
            break
        if re.match(r"(?i)^(doi|http|www\.|copyright|received|accepted)\b", line):
            break
        abstract_parts.append(line)
        if len(" ".join(abstract_parts)) > 2500:
            break

    abstract = " ".join(part for part in abstract_parts if part).strip()
    return abstract if len(abstract) >= 20 else ""


def _has_enough_letters(value: str) -> bool:
    letters = re.findall(r"[A-Za-z]", value)
    return len(letters) >= max(8, int(len(value) * 0.45))


def _looks_like_affiliation_or_metadata(line: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b("
            r"university|institute|department|school|faculty|laborator|centre|center|"
            r"college|academy|hospital|inc\.|corp\.|ltd\.|gmbh|email|@|orcid|doi|"
            r"arxiv|preprint|conference|proceedings|journal|volume|vol\.|issue|"
            r"copyright|licensed|received|accepted|published"
            r")\b",
            line,
        )
    )


def _looks_like_authorish_line(line: str) -> bool:
    if re.search(r"[,;]|\s(and|&)\s", line):
        parts = [part.strip() for part in re.split(r"[,;]|\s+(?:and|&)\s+", line) if part.strip()]
        if len(parts) >= 2:
            authorish_parts = 0
            for part in parts:
                part_words = [word.strip(".-") for word in part.split() if word.strip(".-")]
                if 1 <= len(part_words) <= 4 and all(
                    re.match(r"^([A-Z]\.?|[A-Z][A-Za-z'\-]+)$", word)
                    for word in part_words
                ):
                    authorish_parts += 1
            if authorish_parts == len(parts):
                return True
    words = [word.strip(".-") for word in re.split(r"\s+", line) if word.strip(".-")]
    if len(words) < 2 or len(words) > 8 or len(words) % 2 != 0:
        return False
    lowercase_title_words = {"of", "for", "in", "on", "with", "using", "and", "the"}
    if any(word.lower() in lowercase_title_words for word in words):
        return False
    return all(re.match(r"^([A-Z]\.?|[A-Z][A-Za-z'\-]+)$", word) for word in words)


def _is_title_candidate(line: str) -> bool:
    if not 12 <= len(line) <= 220:
        return False
    if _is_section_heading(line) or _looks_like_affiliation_or_metadata(line):
        return False
    if _looks_like_authorish_line(line):
        return False
    if re.search(r"(?i)\b(abstract|keywords?|index terms)\b", line):
        return False
    if not _has_enough_letters(line):
        return False
    word_count = len(re.findall(r"[A-Za-z][A-Za-z\-]*", line))
    if word_count < 3 or word_count > 32:
        return False
    return True


def _title_score(title: str, first_line_index: int) -> int:
    score = 100 - first_line_index * 4
    length = len(title)
    if 35 <= length <= 160:
        score += 30
    if ":" in title:
        score += 8
    if title.endswith("."):
        score -= 8
    if title.isupper():
        score -= 20
    if re.search(r"(?i)\b(journal|conference|proceedings|workshop|volume|issue)\b", title):
        score -= 25
    return score


def _extract_rule_based_title(lines: list[str]) -> tuple[str, Optional[int], int]:
    abstract_index = _abstract_line_index(lines)
    search_end = abstract_index if abstract_index is not None else min(len(lines), 40)
    candidates: list[tuple[int, str, int, int]] = []

    for index in range(search_end):
        line = lines[index]
        if not _is_title_candidate(line):
            continue

        title_parts = [line]
        next_index = index + 1
        while next_index < search_end and len(" ".join(title_parts)) < 220:
            next_line = lines[next_index]
            if not _is_title_candidate(next_line):
                break
            if _looks_like_affiliation_or_metadata(next_line) or _looks_like_authorish_line(next_line):
                break
            title_parts.append(next_line)
            next_index += 1

        title = " ".join(title_parts).strip()
        candidates.append((_title_score(title, index), title, index, next_index))

    if candidates:
        _, title, start_index, end_index = max(candidates, key=lambda item: item[0])
        return title, start_index, end_index

    for index, line in enumerate(lines[:search_end]):
        if len(line) > 10 and not _looks_like_affiliation_or_metadata(line):
            return line, index, index + 1

    return "", None, 0


def _split_author_candidates(line: str) -> list[str]:
    cleaned = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", " ", line)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\b\d+(?:\s*,\s*\d+)*\b", " ", cleaned)
    cleaned = re.sub(r"[*\[\]{}]", " ", cleaned)
    cleaned = re.sub(r"\s+(and|&)\s+", ",", cleaned)
    return [part.strip(" ,;") for part in re.split(r"[,;]", cleaned) if part.strip(" ,;")]


def _is_author_name(candidate: str) -> bool:
    if not 3 <= len(candidate) <= 80:
        return False
    if _looks_like_affiliation_or_metadata(candidate) or re.search(r"\d|@|http", candidate):
        return False
    words = [word for word in re.split(r"\s+", candidate) if word]
    if len(words) < 2 or len(words) > 6:
        return False
    valid_words = 0
    for word in words:
        word = word.strip(".-")
        if len(word) == 1 and word.isupper():
            valid_words += 1
        elif re.match(r"^[A-Z][A-Za-z'\-]+$", word):
            valid_words += 1
    return valid_words >= max(2, len(words) - 1)


def _extract_rule_based_authors(
    lines: list[str],
    title_start: Optional[int],
    title_end: int,
) -> list[str]:
    abstract_index = _abstract_line_index(lines)
    start = title_end if title_start is not None else 1
    end = abstract_index if abstract_index is not None else min(len(lines), start + 12)
    authors: list[str] = []

    for line in lines[start:end]:
        if _is_section_heading(line) or _looks_like_affiliation_or_metadata(line):
            continue
        for candidate in _split_author_candidates(line):
            if _is_author_name(candidate) and candidate not in authors:
                authors.append(candidate)

    return authors[:20]


def extract_metadata_rule_based(first_page_content: str) -> Dict[str, Any]:
    """
    Extract paper metadata from the first page using deterministic layout/text rules.
    """
    lines = _first_page_lines(first_page_content)
    if not lines:
        return {"title": "", "abstract": "", "authors": []}

    title, title_start, title_end = _extract_rule_based_title(lines)
    abstract = _extract_rule_based_abstract(lines)
    authors = _extract_rule_based_authors(lines, title_start, title_end)

    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
    }


def extract_metadata_with_llm(
    first_page_content: str, provider_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract paper metadata (title, abstract, authors) from first page using LLM with structured output.

    Args:
        first_page_content: Markdown content of the entire first page
        provider_config: LLM provider configuration

    Returns:
        Dictionary with title, abstract, and authors
    """
    system_prompt = """You are an expert at extracting metadata from academic papers. 
Your task is to extract the actual title, abstract, and authors from the first page of a research paper.

IMPORTANT: Extract the REAL content, not placeholder text. For example:
- Title: Extract the actual paper title (usually the first major heading or large text at the top)
- Abstract: Extract the actual abstract text (usually under an "Abstract" heading)
- Authors: Extract the actual author names (usually listed below the title)

Do NOT use placeholder text like "The full title of the paper" or "Paper title here". Extract the actual content from the document."""

    user_prompt = f"""Extract the actual title, abstract, and authors from this first page of a research paper. 
Extract the REAL content from the document, not placeholder text.

{first_page_content}

Remember: Extract the actual title, abstract, and authors that appear in the document above."""

    try:
        model = load_model_from_provider(provider_config)
        agent = Agent(model=model, system_prompt=system_prompt)

        # Use structured output
        try:
            response = agent(user_prompt, structured_output_model=PaperMetadata)
            metadata = response.structured_output.model_dump()
        except Exception as e:
            # Fallback to text extraction if structured output fails
            error_msg = str(e).lower()
            if "structured output" in error_msg or "structured_output" in error_msg:
                # Try fallback: regular text response with JSON parsing
                response = agent(user_prompt)
                if hasattr(response, "text"):
                    response_text = response.text
                elif hasattr(response, "content"):
                    response_text = response.content
                elif isinstance(response, str):
                    response_text = response
                else:
                    response_text = str(response)

                # Try to parse JSON from response
                json_match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
                )
                if json_match:
                    response_text = json_match.group(1)
                else:
                    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(0)

                metadata = json.loads(response_text)
            else:
                raise

        # Ensure all required fields exist
        result = {
            "title": metadata.get("title", "").strip(),
            "abstract": metadata.get("abstract", "").strip(),
            "authors": metadata.get("authors", []),
        }

        # Validate title - check if it's a placeholder
        placeholder_patterns = [
            "the full title of the paper",
            "paper title here",
            "title here",
            "the title",
            "title",
        ]
        title_lower = result["title"].lower()
        if any(pattern in title_lower for pattern in placeholder_patterns) and len(result["title"]) < 100:
            # Title looks like a placeholder, try to extract from first page content
            # Look for the first line that looks like a title (usually starts with ## or is the first substantial line)
            # Use ENTIRE first page content, not just first 20 lines
            lines = first_page_content.split("\n")
            for line in lines:  # Check ALL lines in the first page
                line = line.strip()
                # Skip empty lines, page markers, and very short lines
                if (
                    line
                    and not line.startswith("---")
                    and len(line) > 10
                    and not line.lower().startswith("abstract")
                    and not line.lower().startswith("introduction")
                ):
                    # This might be the title
                    if not line.startswith("#"):
                        result["title"] = line
                    else:
                        # Remove markdown heading markers
                        result["title"] = re.sub(r"^#+\s*", "", line).strip()
                    break

        # Ensure authors is a list
        if not isinstance(result["authors"], list):
            if isinstance(result["authors"], str):
                # Try to parse comma-separated authors
                result["authors"] = [
                    a.strip() for a in result["authors"].split(",") if a.strip()
                ]
            else:
                result["authors"] = []

        return result

    except Exception as e:
        raise PDFProcessingError(f"Failed to extract metadata with LLM: {e}") from e


def extract_metadata_from_first_page(
    first_page_content: str,
    provider_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract metadata using the configured method."""
    if is_rule_based_pdf_metadata_extraction():
        return extract_metadata_rule_based(first_page_content)

    if provider_config is None:
        raise PDFProcessingError(
            "No LLM provider configured. Please add an LLM provider in settings or use rule-based PDF metadata extraction."
        )

    return extract_metadata_with_llm(first_page_content, provider_config)


def get_default_llm_provider() -> Optional[Dict[str, Any]]:
    """
    Get the LLM provider for PDF processing from settings.
    Returns the provider specified in settings, or the first provider if not specified, or None if no providers are configured.
    """
    settings = SettingsManager.load_settings()
    secrets = SettingsManager.load_secrets()

    if not secrets:
        return None

    # Check if a specific provider is configured in settings
    provider_id = settings.get("pdf_processing_llm_provider_id")
    if provider_id:
        provider = next((p for p in secrets if p.get("id") == provider_id), None)
        if provider:
            # Validate provider has required fields
            if provider.get("type") in ["openai", "litellm"]:
                if not provider.get("model_name"):
                    # Fall back to first provider
                    pass
                else:
                    return provider
            else:
                return provider

    # Fall back to first provider
    provider = secrets[0]

    # Ensure it has required fields
    if provider.get("type") in ["openai", "litellm"]:
        if not provider.get("model_name"):
            return None

    return provider


def get_checklist_extraction_llm_provider() -> Optional[Dict[str, Any]]:
    """
    Get the LLM provider for checklist extraction from settings.
    Returns the provider specified in settings, or the first provider if not specified, or None if no providers are configured.
    """
    settings = SettingsManager.load_settings()
    secrets = SettingsManager.load_secrets()

    if not secrets:
        return None

    # Check if a specific provider is configured in settings
    provider_id = settings.get("checklist_extraction_llm_provider_id")
    if provider_id:
        provider = next((p for p in secrets if p.get("id") == provider_id), None)
        if provider:
            # Validate provider has required fields
            if provider.get("type") in ["openai", "litellm"]:
                if not provider.get("model_name"):
                    # Fall back to first provider
                    pass
                else:
                    return provider
            else:
                return provider

    # Fall back to first provider
    if secrets:
        provider = secrets[0]
        # Ensure it has required fields
        if provider.get("type") in ["openai", "litellm"]:
            if not provider.get("model_name"):
                return None
        return provider

    return None


class ChecklistQuestion(BaseModel):
    """Structured output model for a single checklist question."""
    id: str = Field(description="Unique identifier for the question (e.g., 'q1', 'q2')")
    text: str = Field(description="The full question text extracted from the checklist")


class ChecklistQuestions(BaseModel):
    """Structured output model for checklist questions extraction."""
    questions: list[ChecklistQuestion] = Field(description="List of all questions extracted from the checklist")


def extract_checklist_questions_from_pdf(
    pdf_path: Path,
    provider_config: Optional[Dict[str, Any]] = None,
) -> list[Dict[str, str]]:
    """
    Extract checklist questions from a PDF using pymupdf with layout and LLM.
    
    Args:
        pdf_path: Path to the PDF checklist file
        provider_config: Optional LLM provider config. If None, uses default from settings.
    
    Returns:
        List of dictionaries with 'id' and 'text' keys for each question
    
    Raises:
        PDFProcessingError: If extraction fails
    """
    if not PYMUPDF_AVAILABLE:
        raise PDFProcessingError(
            "pymupdf is required for checklist extraction. Install with: pip install pymupdf"
        )

    if not pdf_path.exists():
        raise PDFProcessingError(f"PDF file not found: {pdf_path}")

    # Get provider config if not provided
    if provider_config is None:
        provider_config = get_checklist_extraction_llm_provider()
        if provider_config is None:
            raise PDFProcessingError(
                "No LLM provider configured for checklist extraction. Please add an LLM provider in settings."
            )

    try:
        # Extract text with layout using pymupdf
        doc = pymupdf.open(str(pdf_path))
        text_content = []
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            # Use get_text with layout=True to preserve structure
            text = page.get_text("text", sort=True)
            text_content.append(text)
        
        doc.close()
        
        full_text = "\n\n".join(text_content)
        
        if not full_text.strip():
            raise PDFProcessingError("Could not extract any text from the PDF")
        
        # Use LLM to extract questions
        # Use ENTIRE checklist content - no cropping
        system_prompt = """You are an expert at extracting checklist questions from documents.
Your task is to identify and extract all questions from a checklist document.
Extract each question as a separate item with a unique ID and the full question text.
Questions may be numbered, bulleted, or in other formats - extract them all."""
        
        user_prompt = f"""Extract all questions from this checklist document. 
Return each question with a unique ID (like 'q1', 'q2', etc.) and the full question text.

Document content (ENTIRE checklist):
{full_text}

Remember: Extract ALL questions from the ENTIRE checklist, including sub-questions if present. Do not skip any questions."""
        
        model = load_model_from_provider(provider_config)
        agent = Agent(model=model, system_prompt=system_prompt)
        
        # Use structured output
        try:
            response = agent(user_prompt, structured_output_model=ChecklistQuestions)
            questions = response.structured_output.model_dump()["questions"]
        except Exception as e:
            # Fallback to text extraction if structured output fails
            error_msg = str(e).lower()
            if "structured output" in error_msg or "structured_output" in error_msg:
                response = agent(user_prompt)
                if hasattr(response, "text"):
                    response_text = response.text
                elif hasattr(response, "content"):
                    response_text = response.content
                elif isinstance(response, str):
                    response_text = response
                else:
                    response_text = str(response)
                
                # Try to parse JSON from response
                json_match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
                )
                if json_match:
                    response_text = json_match.group(1)
                else:
                    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(0)
                
                parsed = json.loads(response_text)
                questions = parsed.get("questions", [])
            else:
                raise
        
        # Normalize questions format
        normalized_questions = []
        for i, q in enumerate(questions):
            if isinstance(q, dict):
                question_id = q.get("id", f"q{i+1}")
                question_text = q.get("text", q.get("question", str(q)))
            else:
                question_id = f"q{i+1}"
                question_text = str(q)
            
            normalized_questions.append({
                "id": question_id,
                "text": question_text.strip()
            })
        
        if not normalized_questions:
            raise PDFProcessingError("No questions could be extracted from the checklist")
        
        return normalized_questions
        
    except Exception as e:
        if isinstance(e, PDFProcessingError):
            raise
        raise PDFProcessingError(f"Failed to extract checklist questions: {e}") from e


def process_pdf_to_markdown_and_metadata(
    pdf_path: Path,
    collection_dir: Path,
    provider_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a PDF file: convert to markdown and extract metadata.

    Args:
        pdf_path: Path to the PDF file
        collection_dir: Collection directory where source_extracted folder should be created
        provider_config: Optional LLM provider config. If None, uses default from settings.

    Returns:
        Dictionary with metadata (title, abstract, authors) and paths to generated files
    """
    if not PYMUPDF_AVAILABLE:
        raise PDFProcessingError(
            "pymupdf and pymupdf4llm are required for PDF processing."
        )

    # Get provider config if not provided and the selected method needs one
    if provider_config is None and not is_rule_based_pdf_metadata_extraction():
        provider_config = get_default_llm_provider()
        if provider_config is None:
            raise PDFProcessingError(
                "No LLM provider configured. Please add an LLM provider in settings or use rule-based PDF metadata extraction."
            )

    from src.core import storage
    md_dir = storage._source_md_dir(collection_dir)
    meta_dir = storage._source_metadata_dir(collection_dir)
    pdf_stem = pdf_path.stem
    md_path = md_dir / f"{pdf_stem}.md"
    json_path = meta_dir / f"{pdf_stem}.json"

    # Check if files already exist
    md_content = None
    metadata = None

    if md_path.exists() and json_path.exists():
        # Try to load existing files
        try:
            md_content = md_path.read_text(encoding="utf-8")
            metadata = json.loads(json_path.read_text(encoding="utf-8"))
            return {
                "title": metadata.get("title", ""),
                "abstract": metadata.get("abstract", ""),
                "authors": metadata.get("authors", []),
                "md_path": str(md_path),
                "json_path": str(json_path),
                "cached": True,
            }
        except Exception:
            # If loading fails, reprocess
            pass

    # Convert PDF to markdown
    md_content = pdf_to_markdown(pdf_path, md_path)

    # Extract first page
    first_page = extract_first_page(md_content)

    # Extract metadata using the configured method
    metadata = extract_metadata_from_first_page(first_page, provider_config)

    # Save metadata to JSON
    json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "title": metadata.get("title", ""),
        "abstract": metadata.get("abstract", ""),
        "authors": metadata.get("authors", []),
        "md_path": str(md_path),
        "json_path": str(json_path),
        "cached": False,
    }
