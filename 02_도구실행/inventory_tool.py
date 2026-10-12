"""실제 로컬 LLM과 교재의 모의 재고 함수를 사용하는 실습.

교재의 함수·고정 수량·고정 시각은 보존합니다. 연결만 llama.cpp의
OpenAI 호환 API로 변경하며 모든 모델 응답과 오류를 별도 기록합니다.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = "BUSAN-02 창고의 SKU A-17 재고를 알려 줘"


def get_inventory(sku: str, warehouse_id: str) -> dict[str, Any]:
    """승인된 창고에서 특정 상품의 현재 가용 재고를 읽기 전용으로 조회합니다.
    sku에는 상품 SKU를, warehouse_id에는 SEOUL-01 또는 BUSAN-02만 넣습니다.
    수량을 변경하지 않습니다. INVALID_SKU이면 SKU를 확인해 달라고 물어야 합니다.
    """
    if warehouse_id not in ("SEOUL-01", "BUSAN-02"):
        return {"error": "WAREHOUSE_NOT_ALLOWED"}
    return {"sku": sku, "warehouse_id": warehouse_id,
            "available_quantity": 7, "checked_at": "2026-08-27T01:55:00+09:00"}


def definition_description() -> str:
    """실습 1의 사용 조건·실패 대응만 도구 설명에 추가합니다. 함수는 그대로입니다."""
    document = (ROOT.parent / "01_도구정의" / "tool-definition.md").read_text(encoding="utf-8")
    usage = document.split("## 3.", 1)[1].split("## 4.", 1)[0]
    failure = document.split("## 6.", 1)[1].split("## 문서 점검", 1)[0]
    return get_inventory.__doc__ + "\n\n실습 1의 사용 규칙:\n" + usage + failure


def build_followup_messages(prompt: str, first: Any, result: dict[str, Any]) -> list[Any]:
    """Qwen 템플릿이 요구하는 최초 질문을 결과 재입력에도 보존합니다."""
    from langchain_core.messages import HumanMessage, ToolMessage
    return [
        HumanMessage(content=prompt),
        first,
        ToolMessage(content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=first.tool_calls[0]["id"]),
    ]


def reserve_record() -> tuple[Path, Path]:
    directory = ROOT / "실행기록"
    directory.mkdir(exist_ok=True)
    index = 1
    while True:
        text_path = directory / f"실행기록-{index:02d}.txt"
        json_path = directory / f"실행기록-{index:02d}.json"
        if json_path.exists():
            index += 1
            continue
        try:
            with text_path.open("x", encoding="utf-8"):
                pass
            return text_path, json_path
        except FileExistsError:
            index += 1


def read_server_metadata(base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(base_url.removesuffix("/v1") + "/props")
    key = os.environ.get("LLAMA_API_KEY")
    if key:
        request.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    return {name: data.get(name) for name in ("build_info", "model_alias", "model_path")}


async def run_lab(args: argparse.Namespace) -> int:
    from langchain_core.tools import tool
    from langchain_core.utils.function_calling import convert_to_openai_tool
    from langchain_openai import ChatOpenAI

    description = get_inventory.__doc__ if args.description == "textbook" else definition_description()
    inventory = tool(get_inventory, description=description)
    llm = ChatOpenAI(
        base_url=args.base_url, model=args.model,
        api_key=os.environ.get("LLAMA_API_KEY", "not-needed"),
        temperature=0, max_tokens=1024, timeout=180, max_retries=0,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    ).bind_tools([inventory])
    text_path, json_path = reserve_record()
    record: dict[str, Any] = {
        "started_at": datetime.now().astimezone().isoformat(),
        "command": [sys.executable, *sys.argv], "base_url": args.base_url,
        "model": args.model, "temperature": 0, "max_tokens": 1024,
        "thinking_request": {"enable_thinking": False},
        "description_mode": args.description, "prompt": args.prompt,
        "packages": {name: version(name) for name in ("langchain-core", "langchain-openai")},
        "tool_schema": convert_to_openai_tool(inventory),
        "limitations": [
            "교재 함수는 모의 수량 7과 고정 시각을 반환하며 실제 창고에 연결하지 않습니다.",
            "SKU 길이·존재 검사와 INVALID_SKU 반환 경로는 구현하지 않습니다.",
            "교재처럼 첫 도구 호출만 실행하고 두 번째 모델 응답에서 중단합니다.",
            "교재와 달리 Qwen 템플릿 호환을 위해 결과 재입력에도 최초 사용자 질문을 보존합니다. 원래 입력의 실패는 실행기록-01에 보존했습니다.",
            "definition 모드도 설명만 바꾸며 입력 스키마·함수는 강화하지 않습니다.",
        ],
    }
    lines: list[str] = []

    def report(label: str, value: Any) -> None:
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        line = f"{label}\n{rendered}"
        lines.append(line)
        print(line, flush=True)

    exit_code = 0
    try:
        record["server"] = read_server_metadata(args.base_url)
        report("== 실행 조건 ==", {key: record[key] for key in (
            "started_at", "model", "temperature", "description_mode", "server", "thinking_request")})
        report("== 사용자 요청 ==", args.prompt)
        first = await llm.ainvoke(args.prompt)
        record["first_response"] = first.model_dump(mode="json")
        report("[1] 모델의 호출 요청", first.tool_calls)
        report("[1] 모델의 일반 답변", first.content)
        # 교재의 미호출 IndexError까지 관찰 결과로 보존합니다.
        call = first.tool_calls[0]
        if call["name"] != "get_inventory":
            raise ValueError("허용되지 않은 도구 이름: " + call["name"])
        result = inventory.invoke(call["args"])
        record["tool_result"] = result
        report("[2] 하네스의 실행 결과", result)
        second = await llm.ainvoke(build_followup_messages(args.prompt, first, result))
        record["second_response"] = second.model_dump(mode="json")
        report("[3] 결과를 읽은 최종 답", second.content)
        report("[3] 추가 도구 호출 요청 (실행하지 않음)", second.tool_calls)
        record["status"] = "completed_two_turns"
    except Exception as error:
        exit_code = 1
        record["status"] = "error"
        record["error_type"] = type(error).__name__
        record["error"] = str(error)
        record["traceback"] = traceback.format_exc()
        report("== 실행 오류 원문 ==", record["traceback"])
    finally:
        record["finished_at"] = datetime.now().astimezone().isoformat()
        record["exit_code"] = exit_code
        report("== 실행 종료 ==", {"status": record["status"], "exit_code": exit_code,
                                     "finished_at": record["finished_at"]})
        text_path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        with json_path.open("x", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
        print("RECORD:", text_path, flush=True)
        print("JSON:", json_path, flush=True)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="실제 llama.cpp 서버를 사용하는 재고 도구 실습")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--description", choices=["textbook", "definition"], default="textbook")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", default="Qwen 3.8 27B")
    args = parser.parse_args()
    return asyncio.run(run_lab(args))


if __name__ == "__main__":
    raise SystemExit(main())
