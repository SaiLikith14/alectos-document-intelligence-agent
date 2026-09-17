"""Bounded parser for the existing backend's named JSON SSE contract."""
import codecs
import json
import re


async def iter_events(chunks):
    decoder = codecs.getincrementaldecoder('utf-8')()
    buffer = ''
    async for chunk in chunks:
        buffer += decoder.decode(chunk)
        while True:
            match = re.search(r'\r?\n\r?\n', buffer)
            if not match:
                break
            frame, buffer = buffer[:match.start()], buffer[match.end():]
            if len(frame) > 1_048_576:
                raise ValueError('SSE frame too large')
            name, data = 'message', []
            for line in frame.splitlines():
                if line.startswith('event:'): name = line[6:].strip()
                elif line.startswith('data:'): data.append(line[5:].lstrip(' '))
            if data:
                yield name, json.loads('\n'.join(data))
        if len(buffer) > 1_048_576:
            raise ValueError('SSE frame too large')
    buffer += decoder.decode(b'', final=True)
    if buffer.strip():
        raise ValueError('Truncated SSE frame')


def event(name, data):
    return f'event: {name}\ndata: {json.dumps(data, separators=(",", ":"))}\n\n'
