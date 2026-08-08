FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "app:app"]
