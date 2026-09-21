FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
EXPOSE 8000
CMD ["uvicorn", "clip_api:api", "--host", "0.0.0.0", "--port", "8000"]
