from app.services.chunking import chunk_text


def test_chunk_text_preserves_content_and_overlap():
    text = ' '.join(f'w{i}' for i in range(30))
    chunks = chunk_text(text, chunk_size=10, overlap=2)
    assert len(chunks) == 4
    assert chunks[0].split()[-2:] == chunks[1].split()[:2]
    assert chunks[0].startswith('w0')
    assert chunks[-1].endswith('w29')
