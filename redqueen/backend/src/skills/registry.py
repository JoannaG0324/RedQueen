from typing import Dict, Type, List, Any
from .base import BaseSkill


class SkillRegistry:
    """Skill注册中心，管理所有Skill"""
    
    _skills: Dict[str, Type[BaseSkill]] = {}
    
    @classmethod
    def register(cls, skill_class: Type[BaseSkill]) -> None:
        """注册Skill"""
        # 创建临时实例获取属性值
        try:
            instance = skill_class()
            skill_name = instance.name
            skill_version = instance.version
        except Exception as e:
            skill_name = skill_class.__name__
            skill_version = "unknown"
            print(f"警告：无法获取Skill属性，使用类名作为名称: {e}")
        
        if skill_name in cls._skills:
            try:
                existing_instance = cls._skills[skill_name]()
                existing_version = existing_instance.version
            except:
                existing_version = "unknown"
            print(f"Skill {skill_name} v{existing_version} 已存在，将被 v{skill_version} 覆盖")
        
        cls._skills[skill_name] = skill_class
        print(f"Skill注册成功: {skill_name} v{skill_version}")
    
    @classmethod
    def get(cls, skill_name: str) -> Type[BaseSkill]:
        """获取Skill类"""
        if skill_name not in cls._skills:
            raise ValueError(f"Skill不存在: {skill_name}")
        return cls._skills[skill_name]
    
    @classmethod
    def list_skills(cls) -> List[Dict[str, Any]]:
        """获取所有已注册Skill列表"""
        skills_info = []
        for skill_class in cls._skills.values():
            # 创建临时实例来获取属性值（因为@property需要实例访问）
            try:
                instance = skill_class()
                skills_info.append({
                    "name": instance.name,
                    "version": instance.version,
                    "description": instance.description,
                    "input_params": instance.input_params,
                    "output_format": instance.output_format
                })
            except Exception as e:
                print(f"获取Skill信息失败: {e}")
                skills_info.append({
                    "name": str(skill_class.__name__),
                    "version": "unknown",
                    "description": "获取失败",
                    "input_params": {},
                    "output_format": {}
                })
        return skills_info
    
    @classmethod
    def has_skill(cls, skill_name: str) -> bool:
        """检查Skill是否已注册"""
        return skill_name in cls._skills


def skill(cls: Type[BaseSkill]) -> Type[BaseSkill]:
    """装饰器：自动注册Skill"""
    SkillRegistry.register(cls)
    return cls
