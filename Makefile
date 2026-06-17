CC     = gcc
CFLAGS = -O2
LDFLAGS = -lm

# On macOS the bundled libz.a is a Linux ELF archive and cannot be linked.
# Use the macOS system zlib (-lz) instead; the local zlib.h header is still
# used for compilation since it lives in the same directory.
UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
    ZLIB_LIB = -lz
    ZLIB_DEP =
    # deflate_cont is an IBM custom extension not in macOS system zlib.
    # It has the same signature and call-sites as deflate, so aliasing is safe
    # for local estimation purposes.
    CFLAGS += -Ddeflate_cont=deflate
else
    ZLIB_LIB = libz.a
    ZLIB_DEP = libz.a
endif

all: comprestimator

comprestimator: comprestimator.o $(ZLIB_DEP)
	$(CC) $(CFLAGS) -o $@ comprestimator.o $(ZLIB_LIB) $(LDFLAGS)

comprestimator.o: comprestimator.c
	$(CC) $(CFLAGS) -c comprestimator.c

clean:
	rm -f comprestimator comprestimator.o

clean-all: clean
	rm -rf .venv build/ dist/ dist-electron/ frontend/dist frontend/node_modules electron/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
