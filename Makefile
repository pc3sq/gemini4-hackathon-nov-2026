SERVICE := legal-agent

.PHONY: help up down build logs shell scrape generate eval pipeline clean

help:
	@echo "5-Sigma Legal Agent Commands:"
	@echo "  make up        - Start the FastAPI + SPA container in detached mode"
	@echo "  make build     - Rebuild the Docker image and start the container"
	@echo "  make down      - Stop and remove containers"
	@echo "  make logs      - Tail live FastAPI and agent logs"
	@echo "  make shell     - Open an interactive bash shell inside the container"
	@echo "  make scrape    - Download real Exhibit 10 MSAs from SEC EDGAR"
	@echo "  make generate  - Inject adversarial poison pills & create ground-truth labels"
	@echo "  make eval      - Run the 3-way benchmark (Baseline vs. Decisions vs. Hybrid)"
	@echo "  make pipeline  - Run scrape -> generate -> eval end-to-end"
	@echo "  make clean     - Remove generated test suite and eval results"

up:
	docker compose up -d

build:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f $(SERVICE)

shell:
	docker compose exec $(SERVICE) /bin/bash

scrape:
	docker compose exec $(SERVICE) python -m app.eval.scrape_msas

generate:
	docker compose exec $(SERVICE) python -m app.eval.make_contracts_bad

eval:
	docker compose exec $(SERVICE) python -m app.eval.run_eval

pipeline: scrape generate eval

clean:
	rm -rf data/test_suite/* data/eval_results.json