FROM adeo-base:latest
WORKDIR /app/services/api_gateway
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]