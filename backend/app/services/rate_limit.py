"""Small process-local sliding-window limiter for authentication endpoints.

Public multi-replica deployments should replace this backend with Redis while
keeping the same call sites.
"""
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException


_events: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def enforce_rate_limit(bucket: str, key: str, maximum: int, window_seconds: int) -> None:
    now = monotonic()
    identity = f"{bucket}:{key.strip().lower()}"
    with _lock:
        rows = _events[identity]
        cutoff = now - window_seconds
        while rows and rows[0] <= cutoff:
            rows.popleft()
        if len(rows) >= maximum:
            retry_after = max(1, int(window_seconds - (now - rows[0])))
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": str(retry_after)},
            )
        rows.append(now)


def client_key(request) -> str:
    # 不直接信任客户端可伪造的 X-Forwarded-For。正式反向代理应把真实来源地址
    # 传给 ASGI server，或在受信代理中间件完成校验后再扩展这里。
    return request.client.host if request.client else "unknown"
