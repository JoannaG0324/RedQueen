from typing import Dict, Any
from src.engine.ai_engine import AIEngine
from src.utils.prompts import OPPORTUNITY_ANALYSIS_PROMPT
from .base import BaseSkill
from .registry import skill


@skill
class OpportunityAnalysisSkill(BaseSkill):
    """机会个股分析Skill - 基于AI的A股看多机会分析"""

    _ai_engine = None

    @property
    def name(self) -> str:
        return "opportunity_analysis"

    @property
    def version(self) -> str:
        return "2.0.0"

    @property
    def description(self) -> str:
        return "机会个股搜索 - 基于事件驱动的A股看多机会分析"

    @property
    def input_params(self) -> Dict[str, Dict[str, Any]]:
        return {
            "user_prompt": {
                "type": "string",
                "required": True,
                "description": "用户输入的分析主题或事件描述"
            },
            "max_stocks": {
                "type": "integer",
                "required": False,
                "description": "最大返回股票数量",
                "default": 10
            }
        }

    @property
    def output_format(self) -> Dict[str, Any]:
        return {
            "analysis": "分析报告文本（Markdown格式）",
            "stock_list": "推荐股票代码列表",
            "metadata": {
                "skill_name": "机会个股分析",
                "version": "2.0.0",
                "model": "doubao-seed-2-0-pro-260215"
            }
        }

    @property
    def ai_engine(self) -> AIEngine:
        """延迟初始化AI引擎"""
        if self._ai_engine is None:
            self._ai_engine = AIEngine()
        return self._ai_engine

    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行机会个股分析"""
        # 验证输入参数
        validation_error = self.validate_input(**kwargs)
        if validation_error:
            return {
                "status": "error",
                "error": validation_error
            }

        user_prompt = kwargs.get("user_prompt", "")
        max_stocks = kwargs.get("max_stocks", 10)

        try:
            # 构建完整prompt
            prompt = OPPORTUNITY_ANALYSIS_PROMPT.format(user_input=user_prompt)

            # 调用AI引擎
            result = self.ai_engine.call_doubao_api(prompt)

            if not result:
                return {
                    "status": "error",
                    "error": "AI分析失败"
                }

            # 解析结果
            analysis = self._parse_result(result)

            # 提取股票代码
            stock_list = self._extract_stock_codes(analysis)

            # 限制返回数量
            if len(stock_list) > max_stocks:
                stock_list = stock_list[:max_stocks]

            return {
                "status": "success",
                "analysis": analysis,
                "stock_list": stock_list,
                "metadata": {
                    "skill_name": self.name,
                    "version": self.version,
                    "model": "doubao-seed-2-0-pro-260215"
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"执行失败: {str(e)}"
            }

    def _parse_result(self, result: Dict[str, Any]) -> str:
        """解析AI返回结果"""
        analysis = ""

        # 适配新的API端点返回格式 (choices格式)
        if "choices" in result and isinstance(result["choices"], list):
            for choice in result["choices"]:
                if "message" in choice and "content" in choice["message"]:
                    analysis = choice["message"]["content"]
                    break
        # 适配旧的API端点返回格式 (output格式)
        elif "output" in result and isinstance(result["output"], list):
            for item in result["output"]:
                if "content" in item:
                    if isinstance(item["content"], list):
                        for content_item in item["content"]:
                            if "text" in content_item:
                                analysis = content_item["text"]
                                break
                    elif isinstance(item["content"], str):
                        analysis = item["content"]
                    break

        return analysis.strip()

    def _extract_stock_codes(self, analysis: str) -> list:
        """从分析结果中提取股票代码"""
        import re

        stock_list = []

        # 方式1：匹配Python列表格式 ['600426', '000422']
        list_match = re.search(r"机会个股：?\s*\[([^\]]+)\]", analysis)
        if list_match:
            codes_str = list_match.group(1)
            # 提取单引号或双引号内的内容
            codes = re.findall(r"'([^']+)'|\"([^\"]+)\"", codes_str)
            stock_list = [code[0] if code[0] else code[1] for code in codes]

        # 方式2：匹配中文括号内的股票代码 个股全称(600426)
        if not stock_list:
            code_pattern = r"\((\d{6})\)"
            codes = re.findall(code_pattern, analysis)
            stock_list = list(set(codes))  # 去重

        return stock_list

    
