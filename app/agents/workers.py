"""day55 workers.py를 CareerGraph에 맞게 직접 작성하는 연습 파일."""

from langchain.agents import create_agent

from careeragent.app.core.config import llm
from careeragent.app.core.prompts import (
    REASONER_SYSTEM_PROMPT,
    SEARCH_SYSTEM_PROMPT,
    VERIFIER_SYSTEM_PROMPT,
)
from careeragent.app.core.schemas import (
    ReasonerResult,
    SearchWorkerResult,
    VerificationResult,
)

from careeragent.app.tools.search import get_search_tools



# 워커 이름과 create_agent 결과를 저장할 딕셔너리
WORKERS: dict[str, object] = {}


# 워커별 시스템 프롬프트와 구조화 출력 스키마
WORKER_CONFIG = {
    "search": (SEARCH_SYSTEM_PROMPT, SearchWorkerResult),
    "reasoner": (REASONER_SYSTEM_PROMPT, ReasonerResult),
    "verifier": (VERIFIER_SYSTEM_PROMPT, VerificationResult),
}


def build_worker_tools() -> dict[str, list]:
    """워커별 도구 목록을 준비한다."""

    # 실제 도구는 나중에 tools/ 파일에서 가져온다.
    retriever_tools = get_search_tools(),
    reasoner_tools = []
    verifier_tools = []

    return {
        "search": retriever_tools,
        "reasoner": reasoner_tools,
        "verifier": verifier_tools,
    }


def create_workers(
    worker_tools: dict[str, list] | None = None,
) -> dict[str, object]:
    """세 워커를 create_agent로 만들어 WORKERS에 저장한다."""

    worker_tools = (
        build_worker_tools()
        if worker_tools is None
        else worker_tools
    )

    for worker_name, worker_config in WORKER_CONFIG.items():
        system_prompt, output_schema = worker_config

        WORKERS[worker_name] = create_agent(
            model=llm,
            tools=worker_tools.get(worker_name, []),
            system_prompt=system_prompt,
            response_format=output_schema,
        )

    return WORKERS


if __name__ == "__main__":
    # TODO: 작성이 끝난 뒤 uv run -m app.agents.workers로 생성 결과를 확인한다.
    workers = create_workers()
    print("생성된 워커:", list(workers))
