FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000 DB_PATH=/data/orders.db
VOLUME /data
CMD gunicorn -b 0.0.0.0:$PORT app:app
