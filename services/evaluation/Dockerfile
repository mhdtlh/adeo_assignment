FROM adeo-base:latest
WORKDIR /app/services/evaluation
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]