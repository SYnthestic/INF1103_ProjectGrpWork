FROM python:3.11-slim

WORKDIR /app

ENV SME_DATA_DIR=/app/data
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]