"""发送引擎（FR-048/049/050/051/054）。

- 按通道配额与节奏节流；主通道失败切备用通道；
- 每条记录：发送前二次合规校验（suppression/客户状态）→ 渲染 → 发送 → 写台账（冻结内容版本）；
- 失败分类处理：recipient_rejected 不重试（bounced）；rate_limit/timeout/network/server 有限重试；
  quota/auth 直接尝试备用通道；所有通道额度用尽 → 停止（pending 保留，断点续发）；
- 协作点：每条记录前 ``ctx.checkpoint()``（暂停/取消即时生效）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from saler.core.campaigns import audience as audience_service
from saler.core.campaigns import service as campaign_service
from saler.core.content import service as content_service
from saler.core.content.match import choose_variant
from saler.core.content.render import render
from saler.core.errors import ValidationFailed
from saler.core.sending import channel_service
from saler.db.models import Channel, Company, Contact, SendRecord
from saler.jobs.engine import JobContext
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.mail.base import OutgoingMail
from saler.services.operation_log import log_op

MAX_ATTEMPTS_PER_CHANNEL = 3
RETRY_BASE_DELAY_S = 0.5
#: 连续 N 条网络类失败 → 判定网络/代理中断，停止本轮（记录保持 pending，恢复后断点续发；Edge Case）
NETWORK_BREAKER_THRESHOLD = 5
_TERMINAL_NO_RETRY = {ErrorKind.RECIPIENT_REJECTED}
# 值得在原通道重试的瞬时错误
_TRANSIENT = {ErrorKind.RATE_LIMIT, ErrorKind.TIMEOUT, ErrorKind.NETWORK, ErrorKind.SERVER}
# 网络类错误（触发熔断计数；成功/其他结果重置计数）
_NETWORK_KINDS = {ErrorKind.NETWORK, ErrorKind.TIMEOUT}


def _channel_chain(db: Session, campaign_id: int) -> list[Channel]:
    """按角色排序的通道链：primary → backup（跳过停用/不存在）。"""
    out: list[Channel] = []
    for row in audience_service.channel_rows(db, campaign_id):
        channel = db.get(Channel, row.channel_id)
        if channel is not None and channel.status == "active":
            out.append(channel)
    return out


def _channel_exhausted(db: Session, channel: Channel) -> bool:
    channel_service.ensure_used_today(db, channel)
    return channel.daily_limit > 0 and channel.used_today >= channel.daily_limit


def _render_for_record(
    db: Session, campaign, round_theme_id: int | None, company: Company, channel: Channel
) -> tuple[str, str, object, object, str, bool] | None:
    theme_id = round_theme_id or campaign.content_theme_id
    variants = {
        v.lang: v for v in content_service.list_published(db) if v.theme_id == theme_id
    }
    if not variants:
        return None
    variant, lang, fallback = choose_variant(
        variants,
        customer_lang=company.language,
        strategy=campaign.lang_strategy or "auto",
        fixed_lang=campaign.fixed_lang,
        fallback_lang=campaign.fallback_lang or "en",
    )
    if variant is None or lang is None:
        return None
    version = content_service.get_current_version(db, variant)
    if version is None:
        return None
    identity = channel.identity or {}
    variables = {
        "company_name": company.name or "",
        "contact_name": "",
        "country": company.country or "",
        "language": lang,
        "sender_name": str(identity.get("from_name") or ""),
        "signature": str(identity.get("signature") or ""),
        "today": datetime.now(UTC).date().isoformat(),
    }
    subject, _w1 = render(version.subject or "", variables)
    body, _w2 = render(version.body_md, variables)
    return subject, body, variant, version, lang, fallback


def _build_send_call(channel: Channel, *, to: str, subject: str, body: str):
    identity = channel.identity or {}
    if channel.channel_type == "sms":
        return lambda adapter: adapter.send(
            phone_e164=to, text=f"{subject}\n{body}".strip(), signature=identity.get("signature")
        )
    message = OutgoingMail(
        from_name=str(identity.get("from_name") or ""),
        from_addr=str(identity.get("from_addr") or ""),
        reply_to=identity.get("reply_to"),
        to=to,
        subject=subject or "（无主题）",
        body_text=body,
        body_html=f"<p>{body.replace(chr(10), '<br/>')}</p>",
    )
    return lambda adapter: adapter.send(message=message)


async def _send_with_policy(
    ctx: JobContext,
    *,
    chain: list[Channel],
    to: str,
    subject: str,
    body: str,
    sleep,
) -> tuple[Channel | None, object | None, ProviderError | None]:
    """主→备通道发送：瞬时错误有限重试；quota/auth 立即换通道；recipient_rejected 终态。"""
    last_error: ProviderError | None = None
    for channel in chain:
        try:
            adapter = channel_service.build_adapter(channel)
        except Exception as exc:  # noqa: BLE001
            last_error = ProviderError(ErrorKind.AUTH, f"通道不可用：{exc}")
            continue
        call = _build_send_call(channel, to=to, subject=subject, body=body)
        for attempt in range(MAX_ATTEMPTS_PER_CHANNEL):
            await ctx.checkpoint()
            try:
                result = await asyncio.to_thread(call, adapter)
                return channel, result, None
            except ProviderError as err:
                last_error = err
                if err.kind in _TERMINAL_NO_RETRY:
                    return None, None, err
                if err.kind in _TRANSIENT and attempt < MAX_ATTEMPTS_PER_CHANNEL - 1:
                    await sleep(RETRY_BASE_DELAY_S * (2**attempt))
                    continue
                break  # 换下一个通道
            except Exception as exc:  # noqa: BLE001 —— 适配器意外异常不终止整轮
                last_error = ProviderError(
                    ErrorKind.NETWORK, f"{type(exc).__name__}: {exc}"
                )
                break
    return None, None, last_error


async def run_campaign_round(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    campaign_id: int,
    round_no: int = 1,
    *,
    sleep=None,
) -> dict:
    sleep = sleep or asyncio.sleep
    with session_factory() as db:
        campaign = campaign_service.get_campaign(db, campaign_id)
        round_row = campaign_service.get_round(db, campaign_id, round_no)
        chain_ids = [c.id for c in _channel_chain(db, campaign_id)]
        if not chain_ids:
            raise ProviderError(ErrorKind.AUTH, "计划没有可用的发送通道")
        record_ids = [
            row.id
            for row in db.query(SendRecord)
            .filter_by(campaign_id=campaign_id, round_no=round_no, status="pending")
            .order_by(SendRecord.id.asc())
            .all()
        ]
        if round_row.status == "done" and not record_ids:
            return {"already_done": True, "sent": 0}
        total = len(record_ids)
        ctx.log(f"开始发送：共 {total} 条待发（第 {round_no} 轮）")
        ctx.progress(phase="sending", sent=0, failed=0, total=total, remaining=total)

    stats = {"sent": 0, "failed": 0, "bounced": 0, "skipped": 0, "suppressed": 0}
    stopped: str | None = None
    last_sent_monotonic: dict[int, float] = {}
    consecutive_network_failures = 0

    for record_id in record_ids:
        await ctx.checkpoint()
        with session_factory() as db:
            record = db.get(SendRecord, record_id)
            if record is None or record.status != "pending":
                continue
            company = db.get(Company, record.company_id)
            contact = db.get(Contact, record.contact_id)
            campaign = campaign_service.get_campaign(db, campaign_id)

            # 发送前二次合规校验（FR-051/054 即时生效）
            if contact is None or audience_service.is_contact_suppressed(db, contact) or audience_service.is_company_suppressed(db, company):
                record.status = "suppressed"
                record.skip_reason = "suppressed"
                db.commit()
                stats["suppressed"] += 1
                continue
            if company.status in audience_service.EXCLUDED_COMPANY_STATUSES:
                record.status = "skipped"
                record.skip_reason = f"company_{company.status}"
                db.commit()
                stats["skipped"] += 1
                continue

            # 计划每日上限（schedule.daily_max）
            daily_max = (campaign.schedule or {}).get("daily_max")
            if daily_max:
                today = datetime.now(UTC).date()
                sent_today = sum(
                    1
                    for r in db.query(SendRecord).filter_by(campaign_id=campaign_id, status="sent").all()
                    if r.sent_at and r.sent_at.date() == today
                )
                if sent_today >= int(daily_max):
                    stopped = "daily_max"
                    break

            # 通道选择（额度用尽跳过；全部用尽 → 停止保留 pending）
            # 注意：在本会话内重新加载通道对象，确保用量记账落到当前会话
            usable: list[Channel] = []
            for channel_id in chain_ids:
                channel = db.get(Channel, channel_id)
                if channel is None or channel.status != "active":
                    continue
                if _channel_exhausted(db, channel):
                    ctx.log(f"通道「{channel.name}」今日额度用尽，跳过", level="warn")
                    continue
                usable.append(channel)
            if not usable:
                stopped = "quota"
                break

            # 渲染（冻结内容版本）
            rendered = _render_for_record(db, campaign, round_row.content_theme_id, company, usable[0])
            if rendered is None:
                record.status = "failed"
                record.error_code = "no_content"
                record.error_message = "没有可用的已发布内容版本"
                db.commit()
                stats["failed"] += 1
                continue
            subject, body, variant, version, lang, fallback = rendered

            # 节奏节流（单通道间隔 ≥ 60/rate）
            primary = usable[0]
            interval = 60.0 / max(primary.rate_per_minute, 1)
            last_ts = last_sent_monotonic.get(primary.id)
            if last_ts is not None and time.monotonic() - last_ts < interval:
                await sleep(interval - (time.monotonic() - last_ts))

            channel, result, error = await _send_with_policy(
                ctx, chain=usable, to=record.contact_value, subject=subject, body=body, sleep=sleep
            )

            if channel is not None and result is not None:
                record.status = "sent"
                record.channel_id = channel.id
                record.content_variant_id = variant.id
                record.content_version_id = version.id
                record.lang_used = lang
                record.fallback_used = bool(fallback)
                record.sent_at = datetime.now(UTC)
                last_sent_monotonic[channel.id] = time.monotonic()
                channel_service.record_sent(db, channel)
                if company.status == "new":
                    company.status = "contacted"  # 触达联动（FR-054）
                db.commit()
                stats["sent"] += 1
                consecutive_network_failures = 0
                log_op(
                    db, "send", f"发送成功：{company.name or company.id} → {record.contact_value}",
                    ref_type="campaign", ref_id=campaign_id,
                )
            else:
                err = error or ProviderError(ErrorKind.NETWORK, "未知发送错误")
                if err.kind == ErrorKind.RECIPIENT_REJECTED:
                    record.status = "bounced"
                else:
                    record.status = "failed"
                record.error_code = str(err.kind)
                record.error_message = str(err)[:2000]
                record.channel_id = usable[0].id
                db.commit()
                if record.status == "bounced":
                    stats["bounced"] += 1
                    consecutive_network_failures = 0
                else:
                    stats["failed"] += 1
                    if err.kind in _NETWORK_KINDS:
                        consecutive_network_failures += 1
                    else:
                        consecutive_network_failures = 0
                logger.info("发送失败 campaign={} record={} kind={}", campaign_id, record.id, err.kind)
                if consecutive_network_failures >= NETWORK_BREAKER_THRESHOLD:
                    stopped = "network"  # Edge Case：网络/代理中断 → 停止并提示（记录保留 pending）
                    ctx.log(
                        f"连续 {consecutive_network_failures} 条网络失败：判定网络或代理中断，"
                        "已停止本轮（剩余记录保留待发，网络恢复后重新启动即可续发）",
                        level="warn",
                    )
                    break

        done = stats["sent"] + stats["failed"] + stats["bounced"] + stats["skipped"] + stats["suppressed"]
        ctx.progress(
            phase="sending", **stats, total=total, remaining=max(total - done, 0)
        )

    with session_factory() as db:
        campaign = campaign_service.get_campaign(db, campaign_id)
        final = {key: 0 for key in ("pending", "sent", "failed", "bounced", "skipped", "suppressed")}
        for row in db.query(SendRecord).filter_by(campaign_id=campaign_id, round_no=round_no).all():
            final[row.status] = final.get(row.status, 0) + 1
        if stopped is None:
            campaign_service.finish_round(db, campaign, round_no, final)
        else:
            campaign_service.recompute_stats(db, campaign)
            db.commit()
        result = {**final, "total": total, "round": round_no}
        if stopped:
            result["stopped"] = stopped
            result["hint"] = (
                "网络/代理恢复后重新启动即可断点续发（本轮已失败条目可在台账中重试）"
                if stopped == "network"
                else "剩余记录保持待发：调整限额后重新启动即可断点续发"
            )
        ctx.log(
            f"本轮结束：成功 {final['sent']}，失败 {final['failed']}，退信 {final['bounced']}，"
            f"跳过 {final['skipped']}，排除 {final['suppressed']}"
            + (f"（因 {stopped} 停止）" if stopped else "")
        )
    return result


def test_send(db: Session, campaign, *, n: int = 2, to: str | None = None, to_self: bool = False) -> dict:
    """试发（FR-053）：用前 n 个候选客户的真实内容渲染后发到指定地址；不写台账、不占日限额。"""
    chain = _channel_chain(db, campaign.id)
    if not chain:
        raise ValidationFailed("计划没有可用的发送通道")
    channel = chain[0]
    target = (to or "").strip()
    if not target and to_self:
        target = str((channel.identity or {}).get("from_addr") or "")
    if not target:
        raise ValidationFailed("请提供收件地址（to），或启用 to_self（通道需配置发件地址）")

    contact_type = audience_service.required_contact_type(db, campaign)
    candidates = audience_service.filter_companies(db, campaign.audience or {})
    sent = 0
    failures: list[dict] = []
    for company in candidates:
        if sent >= max(n, 1):
            break
        if company.status in audience_service.EXCLUDED_COMPANY_STATUSES:
            continue
        if audience_service.is_company_suppressed(db, company):
            continue
        if audience_service.pick_contact(db, company.id, contact_type) is None:
            continue
        rendered = _render_for_record(db, campaign, None, company, channel)
        if rendered is None:
            raise ValidationFailed("没有可用的已发布内容版本")
        subject, body, _variant, _version, _lang, _fallback = rendered
        outcome = channel_service.send_content_test(
            db, channel, to=target, subject=subject, body_text=body
        )
        if outcome.get("ok"):
            sent += 1
        else:
            failures.append({"company_id": company.id, "detail": outcome.get("detail")})
    return {"ok": not failures, "sent": sent, "to": target, "failures": failures}
