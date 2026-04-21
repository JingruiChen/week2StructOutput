from pydantic import BaseModel, Field, field_validator
from typing import Literal

class Character(BaseModel):
    # 基础身份信息
    # ... 表示该字段是必填项
    code_name: str = Field(..., min_length=2, max_length=10, description="角色代号，例如：白墨、米雪儿")
    real_name: str = Field(..., min_length=2, description="角色真名")
    
    # 势力与定位枚举约束
    faction: Literal["欧泊", "剪刀手", "防卫队", "未知"] = Field(..., description="所属阵营")
    role: Literal["决斗", "控场", "先锋", "支援"] = Field(..., description="战术定位")

    # 战斗数值约束
    # gt=0: 必须大于0; le=200: 必须小于等于200
    max_hp: int = Field(..., gt=0, le=200, description="最大生命值")
    
    # ge=0: 必须大于等于0 (允许0血死亡状态)
    current_hp: int = Field(..., ge=0, description="当前生命值")
    
    # 技能信息
    passive: str = Field(..., description="被动技能名称")
    tactical: str = Field(..., description="战术技能名称")
    ultimate: str = Field(..., description="终极技能名称")

    # --- 字段验证器 (业务逻辑校验) ---

    @field_validator("code_name")
    @classmethod
    # 这里的 v 代表 code_name 的值
    def check_code_name(cls, v: str) -> str:
        # 校验：代号不能包含空格
        if " " in v:
            raise ValueError("角色代号中不能包含空格")
        return v

    @field_validator("current_hp")
    @classmethod
    # 这里的 v 代表 current_hp 的值，values是其他已经验证过的字段
    def check_hp_consistency(cls, v: int, info) -> int:
        # 获取同一对象中的 max_hp 进行对比
        # 注意：在 V2 中通过 info.data 获取其他字段（如果已解析）
        if 'max_hp' in info.data and v > info.data['max_hp']:
            raise ValueError("当前生命值不能大于最大生命值")
        return v

    @field_validator("tactical", "ultimate")
    @classmethod
    def skill_name_not_empty(cls, v: str) -> str:
        # 校验：技能名称去除首尾空格后不能为空
        if not v.strip():
            raise ValueError("技能名称不能为空或纯空格")
        return v.strip()