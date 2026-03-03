FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py start.sh ./
COPY templates/ templates/

RUN chmod +x start.sh

VOLUME /app/data
ENV DATA_DIR=/app/data

EXPOSE 8009

CMD ["./start.sh"]
