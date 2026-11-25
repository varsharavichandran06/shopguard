FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m data.seed

# Cloud Run sets PORT. Locally it defaults to 8501.
EXPOSE 8501
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
