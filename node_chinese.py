# -*- coding: utf-8 -*-
"""PromptScale 中文扩写工作节点。

模型与推理参数全部来自上游「PromptScale LLM 模型加载器」的 ps模型
连线(PSLLM 句柄)。中文 master 自带尺度逻辑(默认 SFW,输入词点名
NSFW 才升级),因此本节点没有档位开关,也永不追加覆盖指令。
"""

from .llm_enhancer_core import (
    run_enhance,
    list_system_presets,
    MODE_CHOICES,
    MODE_INSTRUCTION_ZH,
    DEFAULT_CHINESE,
)


class PSChinese:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ps模型": ("PSLLM",),
                "想法文本": ("STRING", {"default": "",
                            "multiline": True,
                            "tooltip": "expand 模式填一行想法;upgrade 模式粘贴整段旧提示词。尺度由输入词决定:默认保守,点名 NSFW 才升级。"}),
                "输出模式": (MODE_CHOICES,
                              {"default": MODE_CHOICES[0]}),
                "master预设": (list_system_presets("chinese"),
                                {"default": DEFAULT_CHINESE,
                                 "tooltip": "prompts/chinese/ 目录下的中文 master,随便命名;新增文件后按 R 刷新出现。"}),
                "master覆盖": ("STRING", {"default": "",
                               "tooltip": "填写后优先于上方下拉;支持纯文件名(去 chinese 目录找)或任意完整路径,运行时解析、免刷新。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "info")
    FUNCTION = "enhance"
    CATEGORY = "PromptScale/LLM增强"

    def enhance(self, ps模型, 想法文本, 输出模式, master预设, master覆盖=""):
        return run_enhance(
            handle=ps模型,
            text=想法文本,
            mode_display=输出模式,
            subdir="chinese",
            system_preset=master预设,
            mode_instructions=MODE_INSTRUCTION_ZH,
            node_label="PromptScale 中文扩写",
            tier_key=None,
            tier_override=None,
            custom_preset=master覆盖,
        )


NODE_CLASS_MAPPINGS = {"PSChinese": PSChinese}
NODE_DISPLAY_NAME_MAPPINGS = {"PSChinese": "PromptScale 中文扩写"}
