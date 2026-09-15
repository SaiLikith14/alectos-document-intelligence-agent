import json


def sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return f'event: {event}\ndata: {payload}\n\n'
