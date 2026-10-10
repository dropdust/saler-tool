"""LLM 连通性测试流程（FR-030/041）：由配置行构建适配器并执行测试。

- GET /models 优先、1-token ping 回退（见 OpenAICompatibleProvider.test_connection）；
- 错误文本原样呈现（国内服务商的配额/实名/区域报错需对用户可读）；
- 密钥只从加密列读入内存构建客户端，绝不进入返回值与日志。
"""

from __future__ import annotations

from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.llm.openai_compatible import OpenAICompatibleProvider


def build_provider_from_row(row) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=row.base_url,
        api_key=row.secret_encrypted or "",
        model=row.model,
        supports_json_schema=bool((row.params or {}).get("supports_json_schema")),
        provider_name=row.name,
    )


def run_connection_test(row) -> TestResult:
    """同步执行（由 API 层在 threadpool 中调用），永不抛出。"""
    try:
        provider = build_provider_from_row(row)
        return provider.test_connection()
    except ProviderError as exc:
        return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")
    except Exception as exc:  # noqa: BLE001 - 测试端点必须给出结果而非堆栈
        return TestResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
