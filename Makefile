.PHONY: install test once daemon clean

install:
	@bash install.sh

test:
	@bash run.sh test

once:
	@bash run.sh once

daemon:
	@bash run.sh daemon

clean:
	rm -rf .venv __pycache__ texts/cache output logs
