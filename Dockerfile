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

# Port used by the web version (Flask via gunicorn). Has no effect on the
# terminal app. Publish it with -p 5000:5000 when running the web version.
EXPOSE 5000

# Default: the terminal app. For the web version, override the command:
#   docker run --rm -p 5000:5000 --env-file .env -v "<folder>:/app/data" \
#     sme-grant-auditor gunicorn -w 1 --threads 4 --timeout 120 \
#     -b 0.0.0.0:5000 "app:create_app()"
CMD ["python", "main.py"]