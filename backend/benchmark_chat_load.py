"""测量演示账号在大规模聊天数据下的只读接口响应时间。"""
import json
import statistics
import time

import httpx


BASE_URL = "http://127.0.0.1:8000"


def timed_get(client, path, repeats=5):
    samples = []
    response = None
    for _ in range(repeats):
        started = time.perf_counter()
        response = client.get(path)
        response.raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)
    return response, {
        "median_ms": round(statistics.median(samples), 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def main():
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        login = client.post("/api/auth/login", json={
            "email": "demo.a@example.com",
            "password": "Demo123456!",
        })
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        count_response, count_timing = timed_get(client, "/api/chat/count")
        history_response, history_timing = timed_get(client, "/api/chat/history?limit=100")
        old_response, old_timing = timed_get(
            client,
            "/api/chat/history?limit=100&before=2020-06-01T00:00:00Z",
        )
        calendar_response, calendar_timing = timed_get(
            client,
            "/api/chat/calendar?timezone_offset=480",
        )

        calendar = calendar_response.json()
        print(json.dumps({
            "message_count": count_response.json()["total"],
            "latest_history_items": len(history_response.json()),
            "old_history_items": len(old_response.json()),
            "calendar_days": len(calendar["days"]),
            "calendar_first": calendar["first_date"],
            "calendar_last": calendar["last_date"],
            "timings": {
                "count": count_timing,
                "latest_history_100": history_timing,
                "old_history_100": old_timing,
                "calendar": calendar_timing,
            },
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
