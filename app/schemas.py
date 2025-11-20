from pydantic import BaseModel
from typing import Optional, List

class ProductBase(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    active: Optional[bool] = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    active: bool
    class Config:
        from_attributes = True

class PaginatedProducts(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductOut]

class WebhookCreate(BaseModel):
    url: str
    event: str = "import.completed"
    enabled: bool = True

class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    event: Optional[str] = None
    enabled: Optional[bool] = None

class WebhookOut(BaseModel):
    id: int
    url: str
    event: str
    enabled: bool
    last_status_code: Optional[int] = None
    last_response_ms: Optional[int] = None
    class Config:
        from_attributes = True

class JobStatus(BaseModel):
    id: str
    stage: str
    status: str
    processed_rows: int
    total_rows: int
    error_message: Optional[str] = None