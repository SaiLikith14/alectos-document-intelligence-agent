FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Shell form so $PORT (supplied by Render and most PaaS) expands; 8000 locally.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
