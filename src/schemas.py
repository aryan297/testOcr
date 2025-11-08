from pydantic import BaseModel, Field
from typing import Any, List, Optional, Dict


class OCRField(BaseModel):
    value: Any | None = None
    confidence: float = 0.0
    bbox: List[List[float]] | None = None
    alts: Optional[List[Any]] = None
    raw: Optional[str] = None


class QualityMetrics(BaseModel):
    focus: float = 0.0
    glare: float = 0.0
    skewDeg: float = 0.0
    resolution: List[int] = Field(default_factory=lambda: [0, 0])


class MetaInfo(BaseModel):
    ocrConfidence: float = 0.0
    quality: QualityMetrics | Dict = Field(default_factory=dict)
    duplicateLikely: bool = False
    uploadHash: str = ""
    phash: str = ""


class EntityInfo(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    confidence: float = 0.0
    bbox: Optional[List[List[float]]] = None


class InvoiceNumber(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    bbox: Optional[List[List[float]]] = None
    alt: List[str] = Field(default_factory=list)


class InvoiceDate(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    raw: Optional[str] = None


class InvoiceInfo(BaseModel):
    number: InvoiceNumber = Field(default_factory=lambda: InvoiceNumber())
    date: InvoiceDate = Field(default_factory=lambda: InvoiceDate())
    placeOfSupply: Optional[str] = None


class ComputedTotals(BaseModel):
    net: float = 0.0
    tax: float = 0.0
    gross: float = 0.0


class QtyField(OCRField):
    unit: Optional[str] = None


class OCRLine(BaseModel):
    rowId: str
    description: OCRField = Field(default_factory=lambda: OCRField())
    hsn: Optional[str] = None
    qty: QtyField = Field(default_factory=lambda: QtyField())
    unitPrice: OCRField = Field(default_factory=lambda: OCRField())
    gstRate: OCRField = Field(default_factory=lambda: OCRField())
    computed: ComputedTotals = Field(default_factory=lambda: ComputedTotals())


class TotalsInfo(BaseModel):
    net: float = 0.0
    tax: float = 0.0
    gross: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    confidence: float = 0.0
    reconciled: bool = False
    roundOffDelta: float = 0.0


class Warning(BaseModel):
    code: str
    field: Optional[str] = None
    score: Optional[float] = None


class FullTextToken(BaseModel):
    text: str
    confidence: float
    bbox: List[List[float]]
    handwritten: Optional[bool] = None
    hw_score: Optional[float] = None


class OCRResponse(BaseModel):
    meta: MetaInfo = Field(default_factory=lambda: MetaInfo())
    seller: Optional[EntityInfo] = None
    buyer: Optional[EntityInfo] = None
    invoice: Optional[InvoiceInfo] = None
    lines: List[OCRLine] = Field(default_factory=list)
    totals: Optional[TotalsInfo] = None
    warnings: List[Warning] = Field(default_factory=list)
    fullText: Optional[List[FullTextToken]] = Field(default=None, description="All extracted text tokens with positions")

