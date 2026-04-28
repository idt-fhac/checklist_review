from typing import Dict, Any, Optional


class BaseComponent:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement execute(); "
            "use the component-specific API (e.g., as_tool/execute_tool) or override execute()."
        )

