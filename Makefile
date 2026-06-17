BINARY := ess_comprestimator

.PHONY: all clean clean-all

all:
	go build -o $(BINARY) .

clean:
	rm -f $(BINARY)

clean-all: clean
	rm -rf .venv build/ dist/ dist-electron/ frontend/dist frontend/node_modules electron/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
