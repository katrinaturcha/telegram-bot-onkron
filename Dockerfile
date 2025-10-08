# Используем совместимый Python
FROM python:3.11-slim

# Устанавливаем зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY . .

# Стартуем
CMD ["python", "main.py"]
