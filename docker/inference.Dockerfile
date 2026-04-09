FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.122.0 uvicorn==0.38.0

COPY apps/training/training/inference_app.py /app/inference_app.py

ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "inference_app:app", "--host", "0.0.0.0", "--port", "8080"]
