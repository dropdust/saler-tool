"""AI 辅助编写提示词（006 契约 §5 / research R8）：单轮生成或润色，建议不入库。

- 辅助提示词携带：功能名、变量目录（含渲染语义）、保留槽位与固定段原文
  （"不得重复或修改"）、模式参数（generate 的意图 / polish 的草稿）与输出要求；
- 调用经 `provider.generate_structured`（PROMPT_ASSIST_V1_SCHEMA，60s 硬时限），
  逐次尝试以 `CallRecorder(job_id=None, operation="prompt_assist")` 落 llm_call 明细
  （FR-011：与运行类调用同口径）；同时写 operation_log 遥测；
- 建议仅随返回值到编辑器（"采用"≠保存，FR-010）；本模块不触碰业务库。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session, sessionmaker

from saler.core.prompts import registry
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm import call_log, telemetry
from saler.providers.llm.schemas import PROMPT_ASSIST_V1_SCHEMA

#: 辅助调用的硬时限（交互式短调用；SC-005 常规 ≤30s、上限 60s）
ASSIST_DEADLINE_S = 60.0

_ASSIST_SYSTEM = (
    "你是资深的提示词工程助手：帮助用户完善发给大模型的『业务指令模板』。"
    "只输出严格 JSON（json 对象），不要 Markdown 围栏、不要额外解释；"
    "输出必须满足调用方给出的 JSON Schema。"
)


def build_assist_prompt(
    feature_key: str, *, mode: str, intent: str | None = None, draft: str | None = None
) -> str:
    feature = registry.FEATURES[feature_key]
    var_lines = "\n".join(
        f"- {{{v.name}}}（{v.label}）：{v.render}" for v in feature.variables
    )
    reserved = registry.RESERVED_OUTPUT_CONTRACT
    blocks = [
        f"功能：{feature.label}（{feature.key}）。",
        "可用变量（运行时会被替换为对应内容；建议保留必要变量）：",
        var_lines,
        f"保留槽位 {{{reserved.name}}}：{reserved.render}。建议保留，不要改写或展开。",
        "固定段原文（系统在运行期用它替换槽位；你不得重复、扩写或修改它）：",
        feature.output_contract,
    ]
    if mode == "generate":
        blocks.append(
            "任务：根据以下意图撰写一份完整的候选模板（模板正文用中文，"
            "JSON 输出约定由固定段承担，不要在模板里重复它）：\n"
            f"意图：{(intent or '').strip()}"
        )
    else:
        blocks.append(
            "任务：在不改变业务意图的前提下润色/优化以下模板——更清晰、更结构化、更少歧义；"
            "保留全部必要变量与保留槽位：\n"
            f"模板：\n{(draft or '').strip()}"
        )
    blocks.append(
        '输出 JSON：{"suggestion": "完整候选模板文本", "notes": "修改要点或说明（可为 null）"}。'
    )
    return "\n".join(blocks)


def run_prompt_assist(
    session_factory: sessionmaker[Session],
    provider,
    *,
    feature: str,
    mode: str,
    intent: str | None = None,
    draft: str | None = None,
) -> dict:
    """同步执行一次辅助调用（路由在线程池中调用）；返回 {suggestion, notes}。"""
    prompt = build_assist_prompt(feature, mode=mode, intent=intent, draft=draft)
    recorder = call_log.make_call_recorder(
        session_factory, job_id=None, operation="prompt_assist"
    )
    data = provider.generate_structured(
        prompt=prompt,
        schema=PROMPT_ASSIST_V1_SCHEMA,
        system=_ASSIST_SYSTEM,
        timeout_s=ASSIST_DEADLINE_S,
        deadline_s=ASSIST_DEADLINE_S,
        on_attempt=recorder,
    )
    suggestion = str(data.get("suggestion") or "").strip()
    if not suggestion:
        raise ProviderError(
            ErrorKind.INVALID_OUTPUT,
            "辅助结果缺少 suggestion",
            provider=getattr(provider, "provider_name", None),
            detail=json.dumps(data, ensure_ascii=False)[:500],
        )
    with session_factory() as db:
        telemetry.record_from_provider(db, provider, operation="prompt_assist")
    notes = data.get("notes")
    return {"suggestion": suggestion, "notes": str(notes) if notes else None}
