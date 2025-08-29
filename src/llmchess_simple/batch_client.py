from __future__ import annotations
import json, time, logging, io, os, random
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from .config import SETTINGS

log = logging.getLogger("batch_client")
client = OpenAI(api_key=SETTINGS.openai_api_key)

USE_OPENAI_BATCH = os.environ.get("LLMCHESS_USE_OPENAI_BATCH", "0") != "0"
DEFAULT_COMPLETION_WINDOW = os.environ.get("OPENAI_BATCH_COMPLETION_WINDOW", "24h")
RESPONSES_TIMEOUT_S = float(os.environ.get("LLMCHESS_RESPONSES_TIMEOUT_S", "300"))
RESPONSES_RETRIES = int(os.environ.get("LLMCHESS_RESPONSES_RETRIES", "4"))
MAX_CONCURRENCY = int(os.environ.get("LLMCHESS_MAX_CONCURRENCY", "8"))
ITEMS_PER_BATCH = int(os.environ.get("LLMCHESS_ITEMS_PER_BATCH", "200"))
TURN_MAX_WAIT_S = float(os.environ.get("LLMCHESS_TURN_MAX_WAIT_S", "1200"))  # 20 minutes max wait per turn

# items: [{ 'custom_id': 'g0_ply3', 'messages': [{role, content}, ...], 'model': 'gpt-4o-mini' }]

def _extract_output_text_from_response_obj(resp_obj: dict) -> str:
    """Best-effort extraction of output text from a batch response line's 'response' object.
    Handles several shapes depending on SDK/raw formats.
    """
    if not isinstance(resp_obj, dict):
        return ""
    # 1) Direct convenience
    ot = resp_obj.get("output_text")
    if isinstance(ot, str) and ot.strip():
        return ot.strip()
    # 2) Body nesting
    body = resp_obj.get("body")
    if isinstance(body, dict):
        ot = body.get("output_text")
        if isinstance(ot, str) and ot.strip():
            return ot.strip()
        # 3) Construct from 'output' array pieces (Responses API)
        out = body.get("output")
        if isinstance(out, list) and out:
            texts: list[str] = []
            for elem in out:
                # elem may have content: [{type: 'output_text', text: '...'}]
                content = elem.get("content") if isinstance(elem, dict) else None
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") in ("output_text", "output_message", "text"):
                            t = c.get("text")
                            if isinstance(t, str):
                                texts.append(t)
            if texts:
                return "".join(texts).strip()
        # 4) Fallback for chat.completions-like body
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
    return ""


def _request_with_retry(model: str, messages: list[dict], timeout_s: float, retries: int, idempotency_key: Optional[str] = None) -> str:
    """Helper function to send a request with retries."""
    delay = 0.5
    for attempt in range(retries + 1):
        try:
            # Use extra_headers to pass Idempotency-Key so that SDK/internal retries and our retries do not duplicate work server-side.
            extra_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
            rsp = client.responses.create(model=model, input=messages, timeout=timeout_s, extra_headers=extra_headers)
            text = getattr(rsp, "output_text", None) or ""
            return text.strip() if isinstance(text, str) else ""
        except Exception as e:
            if attempt >= retries:
                log.warning("responses.create failed after %d attempts: %s", attempt + 1, type(e).__name__)
                return ""
            # Exponential backoff with jitter
            sleep_s = delay * (2 ** attempt) * (0.8 + 0.4 * random.random())
            time.sleep(min(sleep_s, 10.0))
    return ""


def submit_responses_parallel(items: List[Dict], max_concurrency: int = MAX_CONCURRENCY, request_timeout_s: float = RESPONSES_TIMEOUT_S) -> Dict[str, str]:
    """Send /v1/responses requests concurrently for interactive latency.
    Returns mapping custom_id -> text. Missing entries indicate a request failure and will be retried next cycle.
    """
    if not items:
        return {}
    results: Dict[str, str] = {}

    def _one(it: Dict) -> tuple[str, str]:
        cid = it["custom_id"]
        model = it.get("model") or SETTINGS.openai_model
        messages = it["messages"]
        text = _request_with_retry(model=model, messages=messages, timeout_s=request_timeout_s, retries=RESPONSES_RETRIES, idempotency_key=str(cid))
        return cid, text

    with ThreadPoolExecutor(max_workers=min(max_concurrency, max(1, len(items)))) as ex:
        futs = [ex.submit(_one, it) for it in items]
        for fut in as_completed(futs):
            try:
                cid, text = fut.result()
                if text:
                    results[cid] = text
            except Exception:
                # Should be rare because _one handles retries; keep quiet
                log.debug("Parallel responses call raised after retries")
    return results


def _read_file_text(file_obj) -> str:
    """Robustly read text from files.content return value across SDK versions."""
    # file_obj may be a stream with .read(), an httpx Response with .text/.content, bytes, or str
    try:
        if hasattr(file_obj, "read"):
            data = file_obj.read()
            if isinstance(data, (bytes, bytearray)):
                return data.decode("utf-8", errors="replace")
            if isinstance(data, str):
                return data
        if hasattr(file_obj, "text"):
            t = file_obj.text
            if isinstance(t, str):
                return t
        if hasattr(file_obj, "content"):
            c = file_obj.content
            if isinstance(c, (bytes, bytearray)):
                return c.decode("utf-8", errors="replace")
            if isinstance(c, str):
                return c
        if isinstance(file_obj, (bytes, bytearray)):
            return file_obj.decode("utf-8", errors="replace")
        if isinstance(file_obj, str):
            return file_obj
    except Exception:
        log.exception("Failed to read file content")
    return ""


def submit_responses_batch(items: List[Dict], poll_interval_s: float = 2.0, timeout_s: float = 600.0) -> Dict[str, str]:
    """Submit a batch of /v1/responses calls and return a mapping custom_id -> output_text.

    Uses the OpenAI Batches API. Not recommended for low-latency game loops; prefer submit_responses_parallel.
    """
    if not items:
        return {}

    # Build JSONL in-memory
    buf = io.StringIO()
    for it in items:
        cid = it["custom_id"]
        model = it.get("model") or SETTINGS.openai_model
        body = {"model": model, "input": it["messages"]}
        line = {
            "custom_id": cid,
            "method": "POST",
            "url": "/v1/responses",
            "body": body,
        }
        buf.write(json.dumps(line) + "\n")
    buf.seek(0)

    # Upload and create batch
    up = client.files.create(file=("batch.jsonl", buf.getvalue()), purpose="batch")
    batch = client.batches.create(input_file_id=up.id, endpoint="/v1/responses", completion_window=DEFAULT_COMPLETION_WINDOW)
    log.info("Submitted batch id=%s items=%d", batch.id, len(items))

    # Poll until terminal
    t0 = time.time()
    prev_status = None
    while True:
        b = client.batches.retrieve(batch.id)
        status = getattr(b, "status", None) or ""
        if status != prev_status:
            counts = getattr(b, "request_counts", None)
            log.info("Batch %s status=%s counts=%s", b.id, status, counts)
            prev_status = status
        if status in ("completed", "failed", "canceled", "cancelled", "expired"):
            break
        if time.time() - t0 > timeout_s:
            log.error("Batch %s timed out after %.1fs", b.id, timeout_s)
            try:
                client.batches.cancel(b.id)
            except Exception:
                pass
            return {}
        time.sleep(poll_interval_s)

    if status != "completed":
        # Log error file if present
        err_id = getattr(b, "error_file_id", None)
        if err_id:
            try:
                err_obj = client.files.content(err_id)
                err_text = _read_file_text(err_obj)
                log.error("Batch %s failed. First 1KB of error file:\n%s", b.id, err_text[:1024])
            except Exception:
                log.error("Batch %s failed and error file could not be read.", b.id)
        else:
            log.error("Batch %s finished with status=%s and no output.", b.id, status)
        return {}

    out_id = getattr(b, "output_file_id", None)
    if not out_id:
        log.error("Batch %s completed but has no output_file_id", b.id)
        return {}

    out_obj = client.files.content(out_id)
    raw_text = _read_file_text(out_obj)
    if not raw_text:
        log.error("Batch %s output file is empty or unreadable", b.id)
        return {}

    lines = raw_text.splitlines()
    results: Dict[str, str] = {}
    for line in lines:
        try:
            obj = json.loads(line)
            cid = obj.get("custom_id")
            resp = obj.get("response") or {}
            text = _extract_output_text_from_response_obj(resp)
            if cid is not None and text:
                results[str(cid)] = text.strip()
        except Exception:
            log.exception("Failed to parse batch output line")
    if not results:
        log.warning("Batch %s returned 0 parsed results out of %d lines", b.id, len(lines))
    return results


def submit_responses_batch_chunked(items: List[Dict], items_per_batch: Optional[int] = None) -> Dict[str, str]:
    """Split the items into multiple OpenAI batch jobs to control batch size via ITEMS_PER_BATCH.
    Returns merged mapping custom_id -> output_text.
    """
    if not items:
        return {}
    ipb = items_per_batch if items_per_batch is not None else int(os.environ.get("LLMCHESS_ITEMS_PER_BATCH", str(ITEMS_PER_BATCH)))
    if ipb <= 0:
        # Fallback to single batch
        return submit_responses_batch(items)
    merged: Dict[str, str] = {}
    for start in range(0, len(items), ipb):
        chunk = items[start:start + ipb]
        log.info("Submitting batch chunk %d..%d of %d", start + 1, min(start + len(chunk), len(items)), len(items))
        part = submit_responses_batch(chunk)
        merged.update(part)
    return merged


def submit_responses(items: List[Dict]) -> Dict[str, str]:
    """Dispatch to parallel or batches based on env flag (legacy helper)."""
    return submit_responses_transport(items, prefer_batches=None)


def submit_responses_transport(items: List[Dict], prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
    """Select transport explicitly: Batches vs Parallel. If prefer_batches is None, use env flag."""
    use_batches = USE_OPENAI_BATCH if prefer_batches is None else bool(prefer_batches)
    if use_batches:
        return submit_responses_batch_chunked(items, items_per_batch=items_per_batch)
    return submit_responses_parallel(items)


def submit_responses_blocking_all(items: List[Dict], max_wait_s: float = TURN_MAX_WAIT_S, prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
    """Ensure we collect responses for all items in this LLM turn before returning.
    Uses Idempotency-Key so repeated attempts don't create duplicate work at the API (parallel mode only).
    In Batches mode, we submit once per turn and return whatever completes in that job (no resubmits this turn).
    """
    if not items:
        return {}
    use_batches = USE_OPENAI_BATCH if prefer_batches is None else bool(prefer_batches)
    if use_batches:
        # Single submission per turn; do not resubmit missing within the same turn.
        return submit_responses_batch_chunked(items, items_per_batch=items_per_batch)

    # Parallel mode: loop until all received or deadline
    deadline = time.time() + max(1.0, max_wait_s)
    item_by_cid: Dict[str, Dict] = {str(it["custom_id"]): it for it in items}
    pending: set[str] = set(item_by_cid.keys())
    results: Dict[str, str] = {}
    attempt = 0
    while pending and time.time() < deadline:
        attempt += 1
        to_send = [item_by_cid[cid] for cid in list(pending)]
        part = submit_responses_parallel(to_send)
        for cid, text in part.items():
            if cid in pending and text:
                results[cid] = text
                pending.discard(cid)
        if pending:
            time.sleep(min(2.0 + 0.25 * attempt, 10.0))
    if pending:
        log.warning("Did not receive all responses in turn window. missing=%d of %d", len(pending), len(items))
    return results
