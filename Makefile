BINARY := ess_comprestimator

.PHONY: all stamp-version version-check clean clean-all

all: stamp-version
	go build -o $(BINARY) .

# Stamp cmd/root.go's VERSION (source of truth) into the manpage and
# electron/package.json.
stamp-version:
	./scripts/stamp-version.sh

# Fail if any version copy has drifted from cmd/root.go (used by CI/hooks).
version-check:
	./scripts/stamp-version.sh --check

clean:
	rm -f $(BINARY)

clean-all: clean
	rm -rf .venv build/ dist/ dist-electron/ frontend/dist frontend/node_modules electron/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
