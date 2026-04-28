import re
from typing import Dict, Any, List, Optional

from src.review_workflow.components.evaluators.question_reviewer.helpers import clean_text_for_encoding


def extract_pages_from_markdown(md_content: str) -> List[Dict[str, Any]]:
    page_markers = re.findall(r"---\s+end\s+of\s+page=(\d+)\s+---", md_content)
    if not page_markers:
        return []
    
    pages = re.split(r"^---\s+end\s+of\s+page=\d+\s+---", md_content, flags=re.MULTILINE)
    return [
        {"page_number": i + 1, "content": clean_text_for_encoding(page_content.strip())}
        for i, page_content in enumerate(pages)
        if page_content.strip()
    ]


def enhance_supporting_texts_with_highlighting(
    supporting_texts_list: List[Dict[str, Any]], 
    paper_pages: Optional[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    page_lookup = {page.get("page_number"): page.get("text", "") for page in paper_pages} if paper_pages else {}
    enhanced_supporting_texts = []
    
    for st in supporting_texts_list:
        enhanced_st = st.copy()
        page_num = st.get("page_number", -1)
        text_crop = st.get("text_crop", "")
        enhanced_st["highlight_text"] = text_crop.strip()
        
        if page_num > 0 and page_num in page_lookup:
            text_lower = text_crop.strip().lower()
            page_lower = page_lookup[page_num].lower()
            if len(text_lower) > 20:
                pos = page_lower.find(text_lower[:50])
                if pos >= 0:
                    enhanced_st["text_start_position"] = pos
                    enhanced_st["text_end_position"] = pos + len(text_crop)
        
        enhanced_supporting_texts.append(enhanced_st)
    
    return enhanced_supporting_texts
