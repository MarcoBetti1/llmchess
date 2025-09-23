from __future__ import annotations
"""
OpenAI transport for move prompts and batched/parallel submissions.

- Responses API: interactive requests with retry and concurrency controls (ThreadPoolExecutor).
- Batches API: offline JSONL uploads with polling; chunking via LLMCHESS_ITEMS_PER_BATCH.
- Robust _extract_output_text_from_response_obj() to normalize text across response shapes.

Environment knobs: OPENAI_BATCH_COMPLETION_WINDOW, LLMCHESS_MAX_CONCURRENCY, LLMCHESS_RESPONSES_TIMEOUT_S,
LLMCHESS_RESPONSES_RETRIES, LLMCHESS_TURN_MAX_WAIT_S, LLMCHESS_BATCH_POLL_S, LLMCHESS_BATCH_TIMEOUT_S,
LLMCHESS_ITEMS_PER_BATCH. See README for details.
"""
from typing import Optional, List, Dict
import io, json, logging, os, random, time, math
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

from ..config import SETTINGS


class OpenAIProvider:
    def __init__(self):
        self.client = OpenAI(api_key=SETTINGS.openai_api_key)
        self.log = logging.getLogger("llm_client.openai")

        # Settings-driven knobs (YAML > env > defaults via config)
        self.DEFAULT_COMPLETION_WINDOW = SETTINGS.openai_batch_completion_window
        self.RESPONSES_TIMEOUT_S = SETTINGS.responses_timeout_s
        self.RESPONSES_RETRIES = SETTINGS.responses_retries
        self.MAX_CONCURRENCY = SETTINGS.max_concurrency
        self.ITEMS_PER_BATCH = SETTINGS.items_per_batch
        self.TURN_MAX_WAIT_S = SETTINGS.turn_max_wait_s
        self.BATCH_POLL_INTERVAL_S = SETTINGS.batch_poll_s
        self.BATCH_TIMEOUT_S = SETTINGS.batch_timeout_s

    # ---------------- Plain prompts ----------------
    def ask_for_best_move_raw(self, fen: str, pgn_tail: str = "", side: str = "", model: Optional[str] = None) -> str:
        user = (
            f"Position (FEN): {fen}\n"
            + (f"Side to move: {side}\n" if side else "")
            + (f"Recent moves (PGN tail):\n{pgn_tail}\n" if pgn_tail else "")
            + "Respond with the best chess move."
        )
        if not model:
            raise ValueError("Model is required; set it in your JSON config (key 'model') or CLI.")
        rsp = self.client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": "You are a strong chess player. When asked for a move, decide the best move."},
                {"role": "user", "content": user},
            ],
        )
        return rsp.output_text.strip()

    def ask_for_best_move_conversation(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        if not model:
            raise ValueError("Model is required; set it in your JSON config (key 'model') or CLI.")
        rsp = self.client.responses.create(model=model, input=messages)
        return rsp.output_text.strip()

    def ask_for_best_move_plain(self, side: str, history_text: str = "", model: Optional[str] = None) -> str:
        parts = [f"Side to move: {side}"]
        if history_text:
            parts.append("Recent moves:\n\n" + history_text)
        parts.append("\nRespond with your best chess move.")
        user_content = "\n".join(parts)
        if not model:
            raise ValueError("Model is required; set it in your JSON config (key 'model') or CLI.")
        rsp = self.client.responses.create(model=model, input=[
            {"role": "system", "content": "You are a strong chess player. When asked for a move, decide the best move."},
            {"role": "user", "content": user_content},
        ])
        return rsp.output_text.strip()

    # ---------------- Transports ----------------
    @staticmethod
    def _extract_output_text_from_response_obj(resp_obj: dict) -> str:
        if not isinstance(resp_obj, dict):
            return ""
        ot = resp_obj.get("output_text")
        if isinstance(ot, str) and ot.strip():
            return ot.strip()
        body = resp_obj.get("body")
        if isinstance(body, dict):
            ot = body.get("output_text")
            if isinstance(ot, str) and ot.strip():
                return ot.strip()
            out = body.get("output")
            if isinstance(out, list) and out:
                texts: List[str] = []
                for elem in out:
                    if not isinstance(elem, dict):
                        continue
                    if elem.get("type") == "message" and isinstance(elem.get("content"), list):
                        for c in elem["content"]:
                            if isinstance(c, dict) and c.get("type") == "output_text":
                                t = c.get("text")
                                if isinstance(t, str):
                                    texts.append(t)
                    t = elem.get("content")
                    if isinstance(t, str):
                        texts.append(t)
                if texts:
                    return "\n".join(s.strip() for s in texts if s.strip())
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    msg = first.get("message") or {}
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str):
                            return content.strip()
                        if isinstance(content, list):
                            parts = []
                            for p in content:
                                if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
                                    parts.append(p["text"])
                            if parts:
                                return "\n".join(parts).strip()
        return ""

    def _request_with_retry(self, model: str, messages: List[dict], timeout_s: float, retries: int, idempotency_key: Optional[str] = None) -> str:
        delay = 0.5
        for attempt in range(retries + 1):
            try:
                extra_headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
                rsp = self.client.responses.create(model=model, input=messages, timeout=timeout_s, extra_headers=extra_headers)
                text = getattr(rsp, "output_text", None) or ""
                return text.strip() if isinstance(text, str) else ""
            except Exception:
                if attempt >= retries:
                    self.log.exception("Responses request failed after %d attempts", attempt + 1)
                    break
                sleep_s = delay * (2 ** attempt) * (0.8 + 0.4 * random.random())
                time.sleep(min(sleep_s, 10.0))
        return ""

    def submit_responses_parallel(self, items: List[Dict], max_concurrency: int | None = None, request_timeout_s: float | None = None) -> Dict[str, str]:
        if not items:
            return {}
        results: Dict[str, str] = {}
        max_concurrency = max_concurrency or self.MAX_CONCURRENCY
        request_timeout_s = request_timeout_s or self.RESPONSES_TIMEOUT_S

        def _one(it: Dict) -> tuple[str, str]:
            cid = str(it["custom_id"])  # ensure string keys
            model = it.get("model")
            if not model:
                raise ValueError("Each item must include a 'model' field.")
            messages = it["messages"]
            text = self._request_with_retry(model=model, messages=messages, timeout_s=request_timeout_s, retries=self.RESPONSES_RETRIES, idempotency_key=cid)
            return cid, text

        with ThreadPoolExecutor(max_workers=min(max_concurrency, max(1, len(items)))) as ex:
            futs = [ex.submit(_one, it) for it in items]
            for fut in as_completed(futs):
                try:
                    cid, text = fut.result()
                    if text:
                        results[cid] = text
                except Exception:
                    self.log.exception("Parallel responses future failed")
        return results

    @staticmethod
    def _read_file_text(file_obj) -> str:
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
            logging.getLogger("llm_client.openai").exception("Failed to read file content")
        return ""

    def submit_responses_batch(self, items: List[Dict], poll_interval_s: float | None = None, timeout_s: float | None = None) -> Dict[str, str]:
        if not items:
            return {}

        buf = io.StringIO()
        for it in items:
            cid = str(it["custom_id"])  # ensure str
            model = it.get("model")
            if not model:
                raise ValueError("Each item must include a 'model' field.")
            body = {"model": model, "input": it["messages"]}
            line = {"custom_id": cid, "method": "POST", "url": "/v1/responses", "body": body}
            buf.write(json.dumps(line) + "\n")
        buf.seek(0)

        payload = buf.getvalue().encode("utf-8")
        up = self.client.files.create(file=("batch.jsonl", payload), purpose="batch")
        self.log.info(
            "Submitting one batch with %d items (window=%s)",
            len(items),
            self.DEFAULT_COMPLETION_WINDOW,
        )
        batch = self.client.batches.create(
            input_file_id=up.id,
            endpoint="/v1/responses",
            completion_window=self.DEFAULT_COMPLETION_WINDOW,
        )
        try:
            self.log.info(
                "Batch %s created: status=%s endpoint=%s created_at=%s input_file_id=%s",
                getattr(batch, "id", "<unknown>"),
                getattr(batch, "status", None),
                getattr(batch, "endpoint", None),
                getattr(batch, "created_at", None),
                getattr(batch, "input_file_id", None),
            )
        except Exception:
            pass

        poll_interval_s = float(poll_interval_s if poll_interval_s is not None else self.BATCH_POLL_INTERVAL_S)
        timeout_s = float(timeout_s if timeout_s is not None else self.BATCH_TIMEOUT_S)
        t0 = time.time()
        prev_status = None
        prev_counts = None
        while True:
            b = self.client.batches.retrieve(batch.id)
            status = getattr(b, "status", None) or ""
            counts = getattr(b, "request_counts", None)
            if status != prev_status or counts != prev_counts:
                try:
                    total = (counts or {}).get("total") if isinstance(counts, dict) else None
                    completed = (counts or {}).get("completed") if isinstance(counts, dict) else None
                    failed = (counts or {}).get("failed") if isinstance(counts, dict) else None
                    pct = None
                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        pct = (completed / total) * 100.0
                    self.log.info(
                        "Batch %s status=%s counts=%s in_progress_at=%s finalizing_at=%s completed_at=%s",
                        getattr(b, "id", "<unknown>"),
                        status,
                        counts,
                        getattr(b, "in_progress_at", None),
                        getattr(b, "finalizing_at", None) if hasattr(b, "finalizing_at") else None,
                        getattr(b, "completed_at", None),
                    )
                    if pct is not None:
                        self.log.info("Batch %s progress: %.1f%% (completed=%s failed=%s total=%s)", getattr(b, "id", "<unknown>"), pct, completed, failed, total)
                except Exception:
                    # Always prefer to continue polling rather than fail on logging
                    pass
                prev_status = status
                prev_counts = counts
            if status in ("completed", "failed", "canceled", "cancelled", "expired"):
                break
            if time.time() - t0 > timeout_s:
                self.log.error("Batch %s timed out after %.1fs", b.id, timeout_s)
                try:
                    self.client.batches.cancel(b.id)
                except Exception:
                    pass
                return {}
            time.sleep(poll_interval_s)

        if status != "completed":
            try:
                self.log.warning(
                    "Batch %s finished with status=%s output_file_id=%s error_file_id=%s counts=%s",
                    getattr(b, "id", "<unknown>"),
                    status,
                    getattr(b, "output_file_id", None),
                    getattr(b, "error_file_id", None),
                    getattr(b, "request_counts", None),
                )
            except Exception:
                pass
            err_id = getattr(b, "error_file_id", None)
            if err_id:
                try:
                    err_obj = self.client.files.content(err_id)
                    err_text = self._read_file_text(err_obj)
                    if err_text:
                        self.log.error("Batch %s error file:\n%s", b.id, err_text[:2000])
                except Exception:
                    self.log.exception("Failed reading error file %s", err_id)
            else:
                self.log.error("Batch %s finished with status=%s and no output.", b.id, status)
            return {}

        out_id = getattr(b, "output_file_id", None)
        if not out_id:
            self.log.error("Batch %s completed but has no output_file_id", b.id)
            return {}

        try:
            self.log.info(
                "Batch %s completed. output_file_id=%s error_file_id=%s counts=%s duration=%.1fs",
                getattr(b, "id", "<unknown>"),
                out_id,
                getattr(b, "error_file_id", None),
                getattr(b, "request_counts", None),
                time.time() - t0,
            )
        except Exception:
            pass

        out_obj = self.client.files.content(out_id)
        raw_text = self._read_file_text(out_obj)
        if not raw_text:
            self.log.error("Batch %s output file is empty or unreadable", b.id)
            return {}

        lines = raw_text.splitlines()
        self.log.info("Batch %s completed; output lines=%d", b.id, len(lines))
        results: Dict[str, str] = {}
        for line in lines:
            try:
                rec = json.loads(line)
                cid = str(rec.get("custom_id", ""))
                response = rec.get("response") or rec.get("body")
                text = self._extract_output_text_from_response_obj(response) if response else ""
                if cid and text:
                    results[cid] = text
            except Exception:
                self.log.exception("Failed to parse batch output line")
        if not results:
            self.log.warning("Batch returned 0 parsed results out of %d lines", len(lines))
            for i, line in enumerate(lines[:3]):
                self.log.debug("Batch output line %d: %s", i + 1, (line[:500] + ("…" if len(line) > 500 else "")))
        return results

    def submit_responses_batch_chunked(self, items: List[Dict], items_per_batch: Optional[int] = None) -> Dict[str, str]:
        if not items:
            return {}
        ipb = items_per_batch if items_per_batch is not None else self.ITEMS_PER_BATCH
        if ipb <= 0:
            return self.submit_responses_batch(items)
        merged: Dict[str, str] = {}
        for start in range(0, len(items), ipb):
            chunk = items[start:start + ipb]
            self.log.info("Submitting batch chunk %d/%d (items=%d)", (start // ipb) + 1, math.ceil(len(items)/ipb) if ipb else 1, len(chunk))
            part = self.submit_responses_batch(chunk)
            merged.update(part)
        return merged

    def submit_responses_transport(self, items: List[Dict], prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
        # Default to parallel unless explicitly told to batch
        use_batches = bool(prefer_batches)
        if use_batches:
            return self.submit_responses_batch_chunked(items, items_per_batch=items_per_batch)
        return self.submit_responses_parallel(items)

    def submit_responses(self, items: List[Dict]) -> Dict[str, str]:
        return self.submit_responses_transport(items, prefer_batches=None)

    def submit_responses_blocking_all(self, items: List[Dict], max_wait_s: float | None = None, prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
        if not items:
            return {}
        # Default to parallel unless explicitly told to batch
        use_batches = bool(prefer_batches)
        if use_batches:
            return self.submit_responses_batch_chunked(items, items_per_batch=items_per_batch)

        deadline = time.time() + max(1.0, float(max_wait_s if max_wait_s is not None else self.TURN_MAX_WAIT_S))
        item_by_cid: Dict[str, Dict] = {str(it["custom_id"]): it for it in items}
        pending: set[str] = set(item_by_cid.keys())
        results: Dict[str, str] = {}
        attempt = 0
        while pending and time.time() < deadline:
            attempt += 1
            to_send = [item_by_cid[cid] for cid in list(pending)]
            part = self.submit_responses_parallel(to_send)
            for cid, text in part.items():
                if text:
                    results[cid] = text
                    pending.discard(cid)
            if pending:
                time.sleep(min(1.0 + 0.25 * attempt, 3.0))
        if pending:
            self.log.warning("Did not receive all responses in turn window. missing=%d of %d", len(pending), len(items))
        return results
