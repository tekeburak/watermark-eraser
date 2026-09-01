.PHONY: help test smoke smoke-synthid bootstrap-synthid docker-synthid-build docker-synthid-help \
	smoke-synthid-text bootstrap-synthid-text \
	smoke-ctrlregen bootstrap-ctrlregen docker-ctrlregen-build docker-ctrlregen-help install-skill sync clean

SCRIPTS := skills/remove-ai-marks/scripts
# uv when available (uv run respects the lockfile), else .venv, else system python.
PYTHON ?= $(shell if command -v uv >/dev/null 2>&1; then echo "uv run --frozen python"; elif [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

sync: ## Create/sync the locked dev environment (uv)
	uv sync --frozen

test: ## Run the full pytest suite
	$(PYTHON) -m pytest

smoke: ## CLI smoke test on bundled fixtures
	-$(PYTHON) $(SCRIPTS)/inspect_text.py tests/fixtures/sample_watermarked.txt
	$(PYTHON) $(SCRIPTS)/clean_text.py tests/fixtures/sample_watermarked.txt -o /tmp/wm.cleaned.txt --stats
	$(PYTHON) $(SCRIPTS)/rewrite_text.py tests/fixtures/sample_watermarked.txt --backend print-prompt >/dev/null
	-$(PYTHON) $(SCRIPTS)/inspect_file.py tests/fixtures/sample_ai.md
	$(PYTHON) $(SCRIPTS)/clean_file.py tests/fixtures/sample_ai.md -o /tmp/sample_ai.cleaned.md
	$(PYTHON) $(SCRIPTS)/clean_file.py tests/fixtures/sample_ai.html -o /tmp/sample_ai.cleaned.html
	$(PYTHON) $(SCRIPTS)/clean_file.py tests/fixtures/sample_meta.svg -o /tmp/sample_meta.cleaned.svg
	@echo "smoke ok"

smoke-synthid: ## Check the pixel-scorer adapter (needs bootstrap)
	@if [ -z "$(REVERSE_SYNTHID_DIR)" ]; then \
	  echo "smoke-synthid skipped (set REVERSE_SYNTHID_DIR)"; \
	else \
	  $(PYTHON) $(SCRIPTS)/score_synthid.py --help >/dev/null && echo "score_synthid adapter present"; \
	fi

bootstrap-synthid: ## Clone+venv the reverse-SynthID scorer (pinned)
	./skills/remove-ai-marks/scripts/setup_synthid.sh

smoke-synthid-text: ## Check the SynthID-Text scorer adapter (needs bootstrap)
	@if [ ! -x "$(HOME)/.watermark-eraser/synthid-text/.venv/bin/python" ]; then \
	  echo "smoke-synthid-text skipped (run: make bootstrap-synthid-text)"; \
	else \
	  $(HOME)/.watermark-eraser/synthid-text/.venv/bin/python $(SCRIPTS)/score_synthid_text.py --help >/dev/null && echo "score_synthid_text adapter present"; \
	fi

bootstrap-synthid-text: ## Clone+venv google-deepmind/synthid-text (pinned, minimal)
	./skills/remove-ai-marks/scripts/setup_synthid_text.sh

docker-synthid-build: ## Build the scorer Docker image
	docker build -f Dockerfile.synthid -t watermark-eraser-synthid-scorer .

docker-synthid-help: ## Show scorer image help
	docker run --rm watermark-eraser-synthid-scorer --help

smoke-ctrlregen: ## Check the CtrlRegen adapter (needs bootstrap)
	@if [ -z "$(NOAI_WATERMARK_DIR)" ]; then \
	  echo "smoke-ctrlregen skipped (set NOAI_WATERMARK_DIR)"; \
	else \
	  $(PYTHON) $(SCRIPTS)/clean_ctrlregen.py --help >/dev/null && echo "clean_ctrlregen adapter present"; \
	fi

bootstrap-ctrlregen: ## Clone+venv the CtrlRegen backend (pinned, heavy)
	./skills/remove-ai-marks/scripts/setup_ctrlregen.sh

docker-ctrlregen-build: ## Build the CtrlRegen Docker image
	docker build -f Dockerfile.ctrlregen -t watermark-eraser-ctrlregen .

docker-ctrlregen-help: ## Show CtrlRegen image help
	docker run --rm watermark-eraser-ctrlregen --help

install-skill: ## Symlink the agent skill into ~/.grok/skills
	mkdir -p $(HOME)/.grok/skills
	ln -sfn $(CURDIR)/skills/remove-ai-marks $(HOME)/.grok/skills/remove-ai-marks
	@echo "linked -> $(HOME)/.grok/skills/remove-ai-marks"

clean: ## Remove caches and the local venv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .venv
