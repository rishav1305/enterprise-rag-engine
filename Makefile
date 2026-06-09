.PHONY: install dev test ci demo seed lint api gate clean
install:        ## install runtime deps
	pip install -r requirements.txt
dev:            ## install dev deps + package (editable)
	pip install -r requirements-dev.txt && pip install -e .
test:           ## run the full suite (incl. adversarial leakage test)
	pytest
ci:             ## THE local pre-merge gate (RAG_DEV_ENV=1, surreal+deps required, 0 skips)
	bash scripts/ci.sh
demo:           ## run the data-leakage governance demo
	python scripts/demo_leakage.py
seed:           ## generate the Meridian data estate to seeds/_out (P0.1a)
	python -c "from seeds.emit import emit; import json; print(json.dumps(emit('seeds/_out', scale=1.0), indent=2))"
api:            ## serve the FastAPI app
	uvicorn rag_engine.api:app --reload --app-dir src
lint:
	ruff check src tests
clean:
	rm -rf .pytest_cache **/__pycache__ .ruff_cache build dist *.egg-info
