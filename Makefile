.PHONY: install seed test chat

install:
	python -m pip install -r requirements.txt

seed:
	python -m data.seed

test:
	python -m pytest -q

chat:
	python chat_cli.py
