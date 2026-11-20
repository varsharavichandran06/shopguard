.PHONY: install seed test

install:
	python -m pip install -r requirements.txt

seed:
	python -m data.seed

test:
	python -m pytest -q
