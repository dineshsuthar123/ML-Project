FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir numpy pandas asyncpg pyarrow
COPY . .
CMD ["python", "generate_digital_twin.py"]

