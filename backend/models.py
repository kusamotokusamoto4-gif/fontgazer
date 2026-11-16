from typing import List, Optional
from pydantic import BaseModel, Field


class PropertyInfo(BaseModel):
    price: str = ""
    location: str = ""
    land_area: str = ""
    building_area: str = ""
    other_info: str = ""


class ProjectInput(BaseModel):
    property_info: PropertyInfo = Field(default_factory=PropertyInfo)
    appeal_bullets: List[str] = Field(default_factory=list)
    appeal_free_text: str = ""
    styles: List[str] = Field(default_factory=lambda: ["auto"])
    duration_mode: str = "auto"
    writing_mode: str = "auto"  # auto(おまかせ) / horizontal(横書きのみ) / vertical(縦書きのみ)


class AssetOrderRequest(BaseModel):
    ordered_ids: List[str]


class AssetUpdateRequest(BaseModel):
    selected: Optional[bool] = None


class FontUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    category: Optional[str] = None
    license_type: Optional[str] = None
    commercial_ok: Optional[bool] = None
    license_notes: Optional[str] = None
    display_name: Optional[str] = None


class EvaluateVideoRequest(BaseModel):
    action: str
    target_value: Optional[str] = None


class GenerateBatchRequest(BaseModel):
    project: ProjectInput
    count: int = 40
    regenerate_from_batch_id: Optional[str] = None