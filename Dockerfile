FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Force cache invalidation
ENV REFRESHED_AT=2026-03-03_1650

COPY app.py start.sh ./
COPY templates/ templates/

RUN chmod +x start.sh

VOLUME /app/data
ENV DATA_DIR=/app/data

EXPOSE 8009

CMD ["./start.sh"]
