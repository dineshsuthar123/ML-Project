FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir confluent-kafka pandas pyarrow
COPY . .
CMD ["python", "sensor_simulator.py"]

