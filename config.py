import os
from dotenv import load_dotenv

load_dotenv()

APP_PORT = int(os.getenv("APP_PORT", "8080"))
APP_WORKERS = int(os.getenv("APP_WORKERS", "2"))
OCR_LANG = os.getenv("OCR_LANG", "en")
OCR_USE_GPU = os.getenv("OCR_USE_GPU", "false")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "12"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "2"))
MIN_FOCUS = float(os.getenv("MIN_FOCUS", "80"))
MAX_GLARE = float(os.getenv("MAX_GLARE", "0.08"))
REJECT_IF_BAD_QUALITY = os.getenv("REJECT_IF_BAD_QUALITY", "true").lower() == "true"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# PP-Structure settings
USE_PP_STRUCTURE = os.getenv("USE_PP_STRUCTURE", "true").lower() == "true"
TABLE_STRUCTURE_MODEL = os.getenv("TABLE_STRUCTURE_MODEL", "en")

# Handwriting detection settings
ENABLE_HANDWRITING_DETECTION = os.getenv("ENABLE_HANDWRITING_DETECTION", "true").lower() == "true"
HANDWRITING_THRESHOLD = float(os.getenv("HANDWRITING_THRESHOLD", "0.6"))
TROCR_MODEL = os.getenv("TROCR_MODEL", "microsoft/trocr-base-handwritten")

