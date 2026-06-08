from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseSkill(ABC):
    """Skill基类，定义统一接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill名称（唯一标识）"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Skill版本"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill描述"""
        pass

    @property
    def input_params(self) -> Dict[str, Dict[str, Any]]:
        """输入参数定义"""
        return {}

    @property
    def output_format(self) -> Dict[str, Any]:
        """输出格式定义"""
        return {}

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行Skill，返回结果"""
        pass

    def validate_input(self, **kwargs) -> Optional[str]:
        """验证输入参数"""
        params = self.input_params
        # 类型映射：字符串类型名到Python类型
        type_mapping = {
            "string": str,
            "integer": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict
        }
        
        for param_name, param_info in params.items():
            if param_info.get("required", False) and param_name not in kwargs:
                return f"缺少必填参数: {param_name}"
            if param_name in kwargs:
                type_def = param_info.get("type", str)
                # 如果类型定义是字符串，转换为对应的Python类型
                expected_type = type_mapping.get(type_def, type_def)
                if not isinstance(kwargs[param_name], expected_type):
                    type_name = type_def if isinstance(type_def, str) else type_def.__name__
                    return f"参数 {param_name} 类型错误，期望 {type_name}"
        return None
