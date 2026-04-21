FROM python:3.12-slim

WORKDIR /app

COPY mailreceiver/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mailreceiver/ mailreceiver/
COPY main.py .

ENV PORT=8000
ENV STORAGE_PATH=/app/storage

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
