VENVPATH=.venv

.PHONY: all check_uv setup clean

all: check_uv setup

check_uv:
	@if ! command -v uv > /dev/null 2>&1; then \
	    echo "==> uv is not installed. Installing via Homebrew..."; \
	    brew install uv || exit 1; \
	else \
	    echo "==> uv is already installed."; \
	fi

setup: check_uv
	@if [ ! -d ${VENVPATH} ]; then \
	    echo "==> Creating virtual environment using uv..."; \
	    uv venv ${VENVPATH} || exit 1; \
	else \
	    echo "==> Virtual environment already exists."; \
	fi
	@. ./${VENVPATH}/bin/activate
	@echo "==> Installing dependencies from requirements.txt..."
	@uv pip install -r requirements.txt || exit 1

clean:
	@echo "==> Removing virtual environment..."
	@rm -rf ${VENVPATH}