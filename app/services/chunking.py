def chunk_text(text: str, chunk_size: int = 220, overlap: int = 40) -> list[str]:
    if chunk_size <= 0:
        raise ValueError('chunk_size must be greater than 0')
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError('overlap must satisfy 0 <= overlap < chunk_size')

    words = text.split()
    if not words:
        return []

    step = chunk_size - overlap
    chunks: list[str] = []
    for start in range(0, len(words), step):
        window = words[start:start + chunk_size]
        if not window:
            break
        chunks.append(' '.join(window))
        if start + chunk_size >= len(words):
            break
    return chunks
