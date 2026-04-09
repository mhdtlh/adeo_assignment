FROM adeo-base:latest
WORKDIR /app/services/ui
ENV PYTHONPATH=/app
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]