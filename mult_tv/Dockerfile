FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn starlette python-multipart bcrypt httpx

# Создаем папки
RUN mkdir -p /app/static /app/data

# Копируем код
COPY main.py config.py db.py auth.py models.py video.py ./
COPY routes/ ./routes/
COPY index.html ./static/
COPY assets/ ./static/assets/

# Открываем порт
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]