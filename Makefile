run:
	uvicorn app:app --reload --port 8080

test:
	pytest -q

build:
	docker build -t ocr-fastapi:local .

serve:
	docker run -p 8080:8080 ocr-fastapi:local

