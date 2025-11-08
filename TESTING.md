# Testing Guide

## Quick Start

### 1. Build and Test

```bash
./build_and_test.sh
```

This will:
- Build the Docker image with all dependencies
- Start the container
- Run health and version checks
- Display service URLs

### 2. Manual Testing

#### Test Health Endpoint
```bash
curl http://localhost:8080/ocr/health
```

Expected response:
```json
{
  "status": "ok",
  "modelsLoaded": true,
  "uptimeSec": 123
}
```

#### Test Version Endpoint
```bash
curl http://localhost:8080/ocr/version
```

Expected response:
```json
{
  "opencv": "4.6.0",
  "paddleocr": "2.7.0.3",
  "pillow": "10.4.0",
  "numpy": "1.26.4"
}
```

#### Test OCR Parse Endpoint
```bash
curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@sample_invoice.pdf" \
  -F "lang=en" \
  | python3 -m json.tool
```

## Feature-Specific Testing

### Testing PP-Structure

1. **Enable PP-Structure** (default):
```bash
docker run -p 8080:8080 \
  -e USE_PP_STRUCTURE=true \
  ocr-fastapi:local
```

2. **Test with table-heavy invoice**:
```bash
curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@invoice_with_table.pdf" \
  | jq '.lines | length'
```

3. **Check debug info**:
```bash
curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@invoice_with_table.pdf" \
  | jq '.lines[0] | keys'
```

Look for `debug.method: "pp_structure"` in response.

### Testing Handwriting Detection

1. **Enable handwriting detection** (default):
```bash
docker run -p 8080:8080 \
  -e ENABLE_HANDWRITING_DETECTION=true \
  -e HANDWRITING_THRESHOLD=0.6 \
  ocr-fastapi:local
```

2. **Test with handwritten invoice**:
```bash
curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@handwritten_invoice.jpg" \
  | jq '.lines[0].description'
```

3. **Check for handwriting metadata**:
```bash
# Look for "handwritten": true and "hw_score" fields
curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@handwritten_invoice.jpg" \
  | jq '.lines[] | select(.handwritten == true)'
```

### Testing TrOCR

1. **Run handwriting test script**:
```bash
python3 test_handwriting.py
```

2. **Check TrOCR model loading**:
```bash
docker logs ocr-test 2>&1 | grep -i trocr
```

## Performance Testing

### Measure Processing Time

```bash
time curl -X POST http://localhost:8080/ocr/parse \
  -F "file=@invoice.pdf" \
  -o /dev/null -s
```

### Compare with/without PP-Structure

```bash
# With PP-Structure
docker run -p 8080:8080 -e USE_PP_STRUCTURE=true ocr-fastapi:local &
time curl -X POST http://localhost:8080/ocr/parse -F "file=@invoice.pdf" -o /dev/null -s

# Without PP-Structure
docker run -p 8081:8080 -e USE_PP_STRUCTURE=false ocr-fastapi:local &
time curl -X POST http://localhost:8081/ocr/parse -F "file=@invoice.pdf" -o /dev/null -s
```

### Compare with/without Handwriting Detection

```bash
# With handwriting detection
docker run -p 8080:8080 -e ENABLE_HANDWRITING_DETECTION=true ocr-fastapi:local &
time curl -X POST http://localhost:8080/ocr/parse -F "file=@invoice.pdf" -o /dev/null -s

# Without handwriting detection
docker run -p 8081:8080 -e ENABLE_HANDWRITING_DETECTION=false ocr-fastapi:local &
time curl -X POST http://localhost:8081/ocr/parse -F "file=@invoice.pdf" -o /dev/null -s
```

## Accuracy Testing

### Test Table Extraction Accuracy

1. **Prepare ground truth**:
   - Create `test_invoices/` directory
   - Add invoices with known line items
   - Create `ground_truth.json` with expected values

2. **Run accuracy test**:
```python
import requests
import json

with open('ground_truth.json') as f:
    ground_truth = json.load(f)

for invoice_file, expected in ground_truth.items():
    with open(f'test_invoices/{invoice_file}', 'rb') as f:
        response = requests.post(
            'http://localhost:8080/ocr/parse',
            files={'file': f}
        )
        result = response.json()
        
        # Compare
        extracted_items = len(result['lines'])
        expected_items = len(expected['lines'])
        
        accuracy = extracted_items / expected_items * 100
        print(f"{invoice_file}: {accuracy:.1f}% accuracy")
```

### Test Handwriting Recognition Accuracy

1. **Create test set** with handwritten fields
2. **Run OCR with/without TrOCR**
3. **Compare results**:

```python
import requests

files_to_test = ['hw_invoice1.jpg', 'hw_invoice2.jpg']

for file in files_to_test:
    # With TrOCR
    with open(file, 'rb') as f:
        response = requests.post(
            'http://localhost:8080/ocr/parse',
            files={'file': f}
        )
        with_trocr = response.json()
    
    # Without TrOCR (disable handwriting detection)
    # ... compare results
```

## Debugging

### Enable Debug Mode

```bash
docker run -p 8080:8080 -e DEBUG=true ocr-fastapi:local
```

### View Logs

```bash
docker logs -f ocr-test
```

### Test Visualization Endpoint

```bash
curl -X POST http://localhost:8080/ocr/debug/visualize \
  -F "file=@invoice.pdf" \
  -o debug_output.png

open debug_output.png  # macOS
# or
xdg-open debug_output.png  # Linux
```

### Check Model Loading

```bash
# Check if PP-Structure models are loaded
docker exec ocr-test ls -la /root/.paddleocr/whl/table/

# Check if TrOCR models are cached
docker exec ocr-test ls -la /root/.cache/huggingface/
```

## Integration Testing

### Test with Python Client

```python
import requests
import json

def test_ocr_service():
    # Health check
    health = requests.get('http://localhost:8080/ocr/health')
    assert health.json()['status'] == 'ok'
    
    # Parse invoice
    with open('test_invoice.pdf', 'rb') as f:
        response = requests.post(
            'http://localhost:8080/ocr/parse',
            files={'file': ('invoice.pdf', f, 'application/pdf')},
            data={'lang': 'en'}
        )
    
    assert response.status_code == 200
    result = response.json()
    
    # Validate response structure
    assert 'meta' in result
    assert 'lines' in result
    assert 'totals' in result
    
    # Check PP-Structure was used
    if result.get('lines'):
        print(f"Extracted {len(result['lines'])} line items")
    
    # Check for handwriting detection
    handwritten_count = sum(
        1 for line in result['lines'] 
        if line.get('description', {}).get('handwritten', False)
    )
    print(f"Found {handwritten_count} handwritten fields")
    
    return result

if __name__ == '__main__':
    result = test_ocr_service()
    print(json.dumps(result, indent=2))
```

### Test with cURL Scripts

Create `test_suite.sh`:

```bash
#!/bin/bash

echo "Running OCR Service Test Suite..."

# Test 1: Health
echo "Test 1: Health Check"
curl -s http://localhost:8080/ocr/health | jq '.status' | grep -q "ok" && echo "✅ PASS" || echo "❌ FAIL"

# Test 2: Version
echo "Test 2: Version Check"
curl -s http://localhost:8080/ocr/version | jq '.paddleocr' | grep -q "2.7" && echo "✅ PASS" || echo "❌ FAIL"

# Test 3: Parse Invoice
echo "Test 3: Parse Invoice"
curl -s -X POST http://localhost:8080/ocr/parse \
  -F "file=@test_invoice.pdf" \
  | jq '.lines | length' | grep -q "[0-9]" && echo "✅ PASS" || echo "❌ FAIL"

echo "Test suite complete!"
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: OCR Service Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Build Docker image
      run: docker build -t ocr-fastapi:test .
    
    - name: Start service
      run: |
        docker run -d -p 8080:8080 --name ocr-test ocr-fastapi:test
        sleep 15
    
    - name: Run health check
      run: |
        curl -f http://localhost:8080/ocr/health
    
    - name: Run tests
      run: |
        pytest tests/
    
    - name: Stop service
      run: docker stop ocr-test
```

## Troubleshooting

### Common Issues

1. **Models not loading**:
   ```bash
   # Check if models exist
   docker exec ocr-test ls -la /root/.paddleocr/
   
   # Rebuild with --no-cache
   docker build --no-cache -t ocr-fastapi:local .
   ```

2. **TrOCR out of memory**:
   ```bash
   # Use smaller model
   docker run -e TROCR_MODEL=microsoft/trocr-base-handwritten ...
   
   # Or disable
   docker run -e ENABLE_HANDWRITING_DETECTION=false ...
   ```

3. **Slow processing**:
   ```bash
   # Enable GPU
   docker run --gpus all -e OCR_USE_GPU=true ...
   
   # Or disable features
   docker run -e USE_PP_STRUCTURE=false -e ENABLE_HANDWRITING_DETECTION=false ...
   ```

4. **PP-Structure fails**:
   ```bash
   # Check logs
   docker logs ocr-test 2>&1 | grep -i "structure"
   
   # Disable and use fallback
   docker run -e USE_PP_STRUCTURE=false ...
   ```
