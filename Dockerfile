FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY corpus ./corpus
COPY scripts ./scripts
ENV PYTHONPATH=/app/src RAG_CORPUS_DIR=/app/corpus
EXPOSE 8000
CMD ["uvicorn", "rag_engine.api:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
