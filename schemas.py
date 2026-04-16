from pydantic import BaseModel, Field, field_validator


class Commodity(BaseModel):
    id: int = Field(..., gt=0, description="商品编号，必须为正整数")
    name: str = Field(..., min_length=1, max_length=100, description="商品名称，1-100个字符")
    price: float = Field(..., gt=0, description="商品价格，必须大于0")
    stock: int = Field(..., ge=0, description="商品库存，必须大于等于0")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("商品名称不能为纯空白字符")
        return v.strip()

    @field_validator("price")
    @classmethod
    def price_precision(cls, v: float) -> float:
        return round(v, 2)