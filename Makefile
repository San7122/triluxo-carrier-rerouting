# Common flows for the carrier-rerouting assignment.
# Reproducibility in one command each.

.PHONY: install smoke run claude deck docker clean

install:            ## Create venv + install deps
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

smoke:              ## Offline sanity check (no API key, no network)
	python -m eval.smoke_offline

run:               ## Full eval: 5 scenarios x both open models (needs GROQ_API_KEY)
	python -m eval.runner

claude:            ## Add the closed-source column (needs ANTHROPIC_API_KEY)
	python -m eval.runner --models claude llama70b llama8b

deck:              ## Regenerate the Part 3 deck
	python docs/build_deck.py

docker:            ## Build the image and run the offline smoke test in it
	docker build -t carrier-rerouting . && docker run --rm carrier-rerouting

clean:
	rm -rf __pycache__ */__pycache__ .pytest_cache
