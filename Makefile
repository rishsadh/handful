# Thin delegation to tasks.py, which is the entry point that works on every platform
# here (make is not installed on the Windows machine this was built on).
#
# `all` deliberately excludes `final`: the final test set is used exactly once, after the
# configuration is frozen.

PY ?= python

.PHONY: setup setup-ai acquire audit clean splits embeddings validate final \
        results-pack test lint smoke demo all help

help:
	@$(PY) tasks.py --help

setup:        ; $(PY) tasks.py setup
setup-ai:     ; $(PY) tasks.py setup-ai
acquire:      ; $(PY) tasks.py acquire
audit:        ; $(PY) tasks.py audit
clean:        ; $(PY) tasks.py clean
splits:       ; $(PY) tasks.py splits
embeddings:   ; $(PY) tasks.py embeddings
validate:     ; $(PY) tasks.py validate
final:        ; $(PY) tasks.py final
results-pack: ; $(PY) tasks.py results-pack
test:         ; $(PY) tasks.py test
lint:         ; $(PY) tasks.py lint
smoke:        ; $(PY) tasks.py smoke
demo:         ; $(PY) tasks.py demo
all:          ; $(PY) tasks.py all
