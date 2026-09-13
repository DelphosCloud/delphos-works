FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice-writer && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# (#8) Run as an ordinary, restricted user rather than root, so that if
# anything inside the container is ever compromised, the blast radius is
# limited to what this user can touch.
RUN groupadd --system app && useradd --system --gid app --home /app app && \
    chown -R app:app /app
USER app

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
