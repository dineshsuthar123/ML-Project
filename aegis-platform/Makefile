# ============================================================
# AEGIS Makefile
# ============================================================
.PHONY: up down simulate train-all run-all logs clean help

## Start all infrastructure + services
up:
	docker compose up -d --build

## Stop all services
down:
	docker compose down

## Start the sensor simulator (publishes to Kafka)
simulate:
	docker compose run --rm sensor-simulator

## Train all AI models (run after digital-twin generates data)
train-all:
	@echo "=== Training Forecasting Model ==="
	docker compose run --rm forecasting python train.py --epochs 30
	@echo "=== Training RL Agent ==="
	docker compose run --rm rl-agent python train_agent.py --timesteps 100000
	@echo "=== All models trained ==="

## Start all AI services + gateway in foreground
run-all:
	docker compose up forecasting anomaly rl-agent demand-response api-gateway frontend

## Follow logs for all services
logs:
	docker compose logs -f --tail=50

## Follow logs for a specific service: make log SERVICE=forecasting
log:
	docker compose logs -f --tail=100 $(SERVICE)

## Remove all volumes (⚠ destroys data)
clean:
	docker compose down -v --remove-orphans

## Generate digital twin data only
generate-data:
	docker compose run --rm digital-twin

## Open API docs in browser (Linux/Mac)
docs:
	open http://localhost:8000/docs || xdg-open http://localhost:8000/docs

## Run Jupyter notebook server for research experiments
notebook:
	cd research && jupyter notebook experiments.ipynb

help:
	@echo ""
	@echo "AEGIS Makefile targets:"
	@echo "  make up            – Start all services (docker compose up -d)"
	@echo "  make down          – Stop all services"
	@echo "  make simulate      – Start sensor data simulation"
	@echo "  make train-all     – Train all AI models"
	@echo "  make run-all       – Start AI services + gateway (foreground)"
	@echo "  make logs          – Follow all logs"
	@echo "  make generate-data – Run digital twin data generator only"
	@echo "  make clean         – Remove all Docker volumes (destroys data)"
	@echo "  make notebook      – Open research Jupyter notebook"
	@echo ""
	@echo "Service URLs (after 'make up'):"
	@echo "  Frontend   : http://localhost:3000"
	@echo "  API Docs   : http://localhost:8000/docs"
	@echo "  Kafka UI   : http://localhost:8080"
	@echo "  MinIO      : http://localhost:9001"
	@echo "  Prometheus : http://localhost:9090"
	@echo "  Grafana    : http://localhost:3001  (admin/admin)"

