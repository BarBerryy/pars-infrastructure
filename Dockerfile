FROM python:3.12-slim

WORKDIR /app

# Сначала зависимости — для кэширования слоёв
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Хостинг передаёт порт через $PORT; по умолчанию 8000
ENV PORT=8000
# БД по умолчанию в /tmp (гарантированно записываемо в контейнере; для постоянного
# хранения хостинг переопределяет DB_PATH на смонтированный диск, напр. /data).
ENV DB_PATH=/tmp/osm_poi.db
EXPOSE 8000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
