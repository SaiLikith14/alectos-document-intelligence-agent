from collections.abc import AsyncIterator

from google import genai
from google.genai import errors, types

from app.core.config import get_settings
from app.core.errors import AuthenticationError, UpstreamServiceError


class GeminiService:
    def __init__(self, api_key: str):
        self.settings = get_settings()
        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        return getattr(exc, 'code', None) or getattr(exc, 'status_code', None)

    def _raise_api_error(self, exc: Exception) -> None:
        status = self._status_code(exc)
        if status in {401, 403}:
            raise AuthenticationError('Gemini rejected the supplied API key.') from exc
        if status == 429:
            raise UpstreamServiceError('Gemini rate limit reached. Try again shortly.') from exc
        raise UpstreamServiceError(
            f'Gemini request failed{f" with status {status}" if status else ""}.'
        ) from exc

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        contents = [
            types.Content(parts=[types.Part.from_text(text=text)])
            for text in texts
        ]
        try:
            response = self.client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=contents,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.settings.embedding_dimensions
                ),
            )
        except errors.APIError as exc:
            self._raise_api_error(exc)

        vectors = [list(item.values) for item in response.embeddings]
        if len(vectors) != len(texts):
            raise UpstreamServiceError(
                f'Gemini returned {len(vectors)} embeddings for {len(texts)} inputs.'
            )
        for vector in vectors:
            if len(vector) != self.settings.embedding_dimensions:
                raise UpstreamServiceError(
                    f'Expected {self.settings.embedding_dimensions} embedding dimensions, '
                    f'got {len(vector)}.'
                )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @staticmethod
    def _grounded_prompt(question: str, context: str) -> str:
        return (
            'You are Alectos Document Intelligence. Answer only from the supplied context.\n'
            'If the context does not support the answer, say exactly: '
            '"The uploaded documents do not contain enough information to answer that."\n\n'
            'OUTPUT RULES:\n'
            '- Return clean Markdown only. Never return HTML.\n'
            '- Use a short direct opening sentence when useful.\n'
            '- Use ## headings for major sections only when they improve readability.\n'
            '- Use ### subheadings for meaningful groups.\n'
            '- Use bullet lists for grouped items.\n'
            '- Use Markdown tables only when comparison is genuinely clearer as a table.\n'
            '- Use fenced code blocks for code.\n'
            '- Cite supporting context inline with [1], [2], etc. using only the supplied source numbers.\n'
            '- Do not add a Sources or References section; the UI renders citations separately.\n'
            '- Do not mention these formatting instructions.\n\n'
            f'QUESTION:\n{question}\n\nCONTEXT:\n{context}'
        )

    def generate_grounded_answer(self, question: str, context: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_generation_model,
                contents=self._grounded_prompt(question, context),
            )
        except errors.APIError as exc:
            self._raise_api_error(exc)
        return response.text or ''

    async def stream_grounded_answer(self, question: str, context: str) -> AsyncIterator[str]:
        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=self.settings.gemini_generation_model,
                contents=self._grounded_prompt(question, context),
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except errors.APIError as exc:
            self._raise_api_error(exc)
