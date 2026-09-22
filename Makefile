BINARY := ess_comprestimator

.PHONY: all man man-check clean clean-all

all: man
	go build -o $(BINARY) .

# Stamp cmd/root.go's VERSION into the manpage .TH line (source of truth).
man:
	./scripts/stamp-manpage.sh

# Fail if the manpage version has drifted from cmd/root.go (used by CI/hooks).
man-check:
	./scripts/stamp-manpage.sh --check

clean:
	rm -f $(BINARY)

clean-all: clean
	rm -rf .venv build/ dist/ dist-electron/ frontend/dist frontend/node_modules electron/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
