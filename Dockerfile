FROM python:3.11-slim

WORKDIR /app

# The app reads DATA_DIR to decide where to save its JSON files
# (saved records, users.json, audit_history.json).
# Mount a host folder here with -v to keep them (see README).
ENV DATA_DIR=/app/data
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

CMD ["python", "main.py"]