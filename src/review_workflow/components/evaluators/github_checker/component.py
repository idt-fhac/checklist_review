import re
import subprocess
from pathlib import Path
from typing import List, Optional

from strands import Agent, tool

from src.core.criteria import criteria_set_stem
from src.core.providers import resolve_provider_config
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.token_usage import add as token_usage_add
from src.review_workflow.engine.utils import load_model_from_provider


def slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent.parent


class GithubChecker(BaseComponent):
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
        @tool(name="github_checker")
        def check_github_repo(question: str, github_url: str = "") -> str:
            """
            Analyze the file structure of a GitHub repository and answer questions about its organization, contents, and major files.

            Use this tool when you need to investigate the code layout or directory structure of a public GitHub repository referenced in a paper, checklist, or review workflow. The tool automatically clones or updates the repository to the latest version before analysis.

            Example use cases include:
                - Determining whether specific files or folders (e.g., README, requirements.txt, src/, datasets/) exist
                - Summarizing the overall organization or technology stack
                - Checking for the presence of documentation or code artifacts
                - Identifying main entry points, scripts, or configuration files

            Notes:
                - Only public GitHub repositories are supported; private repos may return errors
                - A shallow clone is performed for efficiency; file content is not fully inspected unless required
                - The analysis is based on the latest state of the default branch at the time of execution
                - If no URL is provided, the tool attempts to locate a GitHub repository link in the associated paper content

            Args:
                question: The specific question about the repository's file/directory structure or composition.
                          Example: "Does the repository include tests and how are they organized?"
                github_url: The GitHub repository URL to check.
                            Example: "https://github.com/org/project".
                            If omitted, the tool will attempt to infer a URL from the context.

            Returns:
                A natural language answer addressing the input question, based solely on the analyzed directory and file structure of the specified repository.
            """
            url_match = re.search(r"https?://github\.com/[\w-]+/[\w.-]+", github_url)
            if url_match:
                github_url = url_match.group(0)

            return self.execute_tool(
                github_url,
                question,
                collection_name,
                review_process_name,
                checklist_name,
                paper_name,
                log_callback,
                token_usage_accumulator,
                collections_root,
            )

        return check_github_repo

    def execute_tool(
        self,
        github_url: str,
        question: str,
        collection_name: str,
        review_process_name: str,
        checklist_name: str,
        paper_name: str,
        log_callback=None,
        token_usage_accumulator=None,
        collections_root: Optional[Path] = None,
    ) -> str:
        def get_repo_path() -> Path:
            if collections_root:
                base_dir = Path(collections_root)
            else:
                project_root = get_project_root()
                base_dir = project_root / "workspaces" / "guest" / "collections"

            checklist_name_clean = criteria_set_stem(checklist_name)
            return (
                base_dir
                / slug(collection_name)
                / "review_processes"
                / slug(review_process_name)
                / slug(checklist_name_clean)
                / paper_name
                / "artifacts"
                / "github_checker"
            )

        def sync_repo(url: str, path: Path) -> None:
            if not path.exists():
                subprocess.run(["git", "clone", url, str(path)], check=True)
            else:
                if (path / ".git").exists():
                    subprocess.run(["git", "-C", str(path), "pull"], check=True)
                else:
                    raise RuntimeError(
                        f"Directory {path} exists but is not a git repository."
                    )

        def list_files(path: Path) -> List[str]:
            return sorted(
                str(p.relative_to(path))
                for p in path.rglob("*")
                if p.is_file() and ".git" not in p.parts
            )

        def get_provider_config(provider_id):
            return resolve_provider_config(provider_id)

        def create_agent():
            provider_id = self.config.get("provider_id")
            if not provider_id:
                raise ValueError("No provider_id configured for GithubChecker")

            provider_config = get_provider_config(provider_id)
            system_prompt = (
                "You are a helpful assistant that checks repository structure."
            )
            model = load_model_from_provider(provider_config)
            return Agent(model=model, system_prompt=system_prompt)

        def answer_question(file_list: List[str], question: str) -> str:
            file_structure_str = "\n".join(file_list)
            agent = create_agent()

            prompt = f"""You are a code reviewer. You have checked the file structure of a repository.
        
            File Structure:
            {file_structure_str}

            Answer the following question based ONLY on the existence and names of files.

            Question: {question}

            Provide a clear and detailed explanation of your answer. Give a relative file path to the file where it is located if available. 
            Explain what files or file patterns you found (or did not find) that support your answer. 
            This explanation will be used to provide a meaningful reason for the final answer."""

            response = agent(prompt)
            if token_usage_accumulator is not None:
                token_usage_add(token_usage_accumulator, response, agent)
            return response.text if hasattr(response, "text") else str(response)

        if log_callback:
            log_callback(
                f"Using GithubChecker tool for repository: {github_url}", "info"
            )

        repo_path = get_repo_path()
        repo_name = github_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        repo_path = repo_path / repo_name
        sync_repo(github_url, repo_path)
        files_list = list_files(repo_path)

        result = answer_question(files_list, question)
        return result


if __name__ == "__main__":
    config = {
        "provider_id": "5a5b024d-5d7f-4aa9-b7c8-8350951d755b",
    }
    github_checker = GithubChecker(config=config)
    github_checker.execute_tool(
        github_url="https://github.com/mlfoundations/task_vectors",
        question="Does the repository contain a README file?",
        collection_name="ml_papers",
        review_process_name="Demo Review Process",
        criteria_set_name="example",
        paper_name="EDITING MODELS WITH TASK ARITHMETIC.pdf",
        # log_callback=lambda x: print(x),
    )
