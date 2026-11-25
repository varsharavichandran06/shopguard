.PHONY: install seed test chat app docker

install:
	python -m pip install -r requirements.txt

seed:
	python -m data.seed

test:
	python -m pytest -q

chat:
	python chat_cli.py

app:
	streamlit run app.py

docker:
	docker build -t shopguard . && docker run --rm -p 8501:8501 --env-file .env shopguard
