#!/bin/bash
set -e

echo "🔨 Building Docker image with PP-Structure and TrOCR support..."
docker build --no-cache -t ocr-fastapi:local .

echo ""
echo "✅ Build complete!"
echo ""
echo "🚀 Starting container..."
docker run -d -p 8080:8080 --name ocr-test ocr-fastapi:local

echo ""
echo "⏳ Waiting for service to start..."
sleep 10

echo ""
echo "🏥 Testing health endpoint..."
curl -s http://localhost:8080/ocr/health | python3 -m json.tool

echo ""
echo "📊 Testing version endpoint..."
curl -s http://localhost:8080/ocr/version | python3 -m json.tool

echo ""
echo "✅ All tests passed!"
echo ""
echo "📝 Service is running at http://localhost:8080"
echo "📖 API docs at http://localhost:8080/docs"
echo ""
echo "To stop: docker stop ocr-test && docker rm ocr-test"
