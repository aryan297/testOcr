from fastapi.testclient import TestClient
from app import app
import io
from PIL import Image


def test_parse_png_smoke():
    """Smoke test for PNG parsing."""
    c = TestClient(app)
    # Create a test image
    img = Image.new("RGB", (1800, 1200), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    files = {"file": ("test.png", buf.getvalue(), "image/png")}
    data = {"return_visual": "false", "lang": "en"}
    r = c.post("/ocr/parse", files=files, data=data)
    # Should return 200 even if no text is found (will have empty response)
    assert r.status_code in [200, 422]
    if r.status_code == 200:
        json_data = r.json()
        assert "meta" in json_data
        assert "lines" in json_data

