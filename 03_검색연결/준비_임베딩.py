"""승인된 ONNX 모델 다운로드와 실제 임베딩 검증. 리랭커는 사용하지 않습니다."""
from datetime import datetime
from importlib.metadata import version
import json
from pathlib import Path
import hashlib

from fastembed import TextEmbedding

root = Path(__file__).resolve().parent
cache = root / "임베딩모델"
print("CACHE:", cache, flush=True)
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=str(cache), threads=2)
vector = list(model.embed(["환불은 구매 후 7일 이내에 가능하다."]))[0]
assert len(vector) == 384, f"예상과 다른 차원: {len(vector)}"
files = []
for path in sorted(cache.rglob("*")):
    if not path.is_file() or ".locks" in path.parts:
        continue
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    files.append({"file": str(path.relative_to(cache)), "bytes": path.stat().st_size,
                  "sha256": digest.hexdigest()})
manifest = {"checked_at": datetime.now().astimezone().isoformat(),
            "model": "BAAI/bge-small-en-v1.5", "runtime": "FastEmbed / ONNX Runtime",
            "versions": {name: version(name) for name in ("fastembed", "onnxruntime", "mcp-server-qdrant")},
            "embedding_dimension": len(vector), "reranker": False, "files": files}
output = root / "임베딩_검증결과.json"
output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("EMBEDDING_DIMENSION:", len(vector), flush=True)
print("MODEL_DIR:", model.model._model_dir, flush=True)
print("MANIFEST:", output, flush=True)
print("PREPARE_EMBEDDING_PASS", flush=True)
