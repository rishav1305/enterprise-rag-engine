.PHONY: install dev test demo lint api gate clean
install:        ## install runtime deps
	pip install -r requirements.txt
dev:            ## install dev deps + package (editable)
	pip install -r requirements-dev.txt && pip install -e .
test:           ## run the full suite (incl. adversarial leakage test)
	pytest
demo:           ## run the data-leakage governance demo
	python scripts/demo_leakage.py
api:            ## serve the FastAPI app
	uvicorn rag_engine.api:app --reload --app-dir src
lint:
	ruff check src tests
clean:
	rm -rf .pytest_cache **/__pycache__ .ruff_cache build dist *.egg-info
