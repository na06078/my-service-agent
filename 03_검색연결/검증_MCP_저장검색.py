"""MCP 프로토콜로 실제 저장·검색을 확인합니다. LLM이 선택하는 실험과는 별개입니다."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
SENTENCES = ["환불은 구매 후 7일 이내에 가능하다.", "배송은 영업일 기준 2일이 걸린다.",
             "회원 등급은 매월 1일에 갱신된다."]


async def main():
    config = json.loads((ROOT / "검색연결설정.json").read_text(encoding="utf-8"))["mcpServers"]["qdrant"]
    directory = ROOT / "실행기록"
    directory.mkdir(exist_ok=True)
    index = 1
    while (directory / f"MCP검증-{index:02d}.json").exists():
        index += 1
    record_path = directory / f"MCP검증-{index:02d}.json"
    stderr_path = directory / f"MCP검증-{index:02d}-서버로그.txt"
    record = {"started_at": datetime.now().astimezone().isoformat(),
              "scope": "SDK 직접 MCP 검사. LLM 선택·llama-server 네이티브 연결 검증 아님.",
              "settings": config["env"], "operations": []}
    exit_code = 0
    try:
        parameters = StdioServerParameters(command=config["command"], args=config["args"],
                                           cwd=config["cwd"], env={**os.environ, **config["env"]})
        with stderr_path.open("x", encoding="utf-8") as errlog:
            async with stdio_client(parameters, errlog=errlog) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    initialized = await session.initialize()
                    record["initialize"] = initialized.model_dump(mode="json")
                    tools = await session.list_tools()
                    record["tools"] = tools.model_dump(mode="json")
                    names = sorted(tool.name for tool in tools.tools)
                    assert names == ["qdrant-find", "qdrant-store"], names
                    print("TOOLS:", names, flush=True)
                    for sentence in SENTENCES:
                        arguments = {"information": sentence, "metadata": None}
                        result = await session.call_tool("qdrant-store", arguments)
                        record["operations"].append({"tool": "qdrant-store", "arguments": arguments,
                                                     "result": result.model_dump(mode="json")})
                        assert not result.isError, result
                        print("STORED:", sentence, flush=True)
                    arguments = {"query": "환불 기한이 어떻게 돼?"}
                    result = await session.call_tool("qdrant-find", arguments)
                    record["operations"].append({"tool": "qdrant-find", "arguments": arguments,
                                                 "result": result.model_dump(mode="json")})
                    assert not result.isError, result
                    returned = "\n".join(part.text for part in result.content if part.type == "text")
                    assert all(sentence in returned for sentence in SENTENCES), returned
                    record["same_session_store_then_find_pass"] = True
                    print("FIND_RESULT:", returned, flush=True)
        record["status"] = "pass"
        print("MCP_PROTOCOL_STORE_FIND_PASS", flush=True)
    except Exception as error:
        exit_code = 1
        record["status"] = "error"
        record["error_type"] = type(error).__name__
        record["traceback"] = traceback.format_exc()
        print(record["traceback"], flush=True)
    finally:
        record["finished_at"] = datetime.now().astimezone().isoformat()
        record["exit_code"] = exit_code
        with record_path.open("x", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
        print("RECORD:", record_path, flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
