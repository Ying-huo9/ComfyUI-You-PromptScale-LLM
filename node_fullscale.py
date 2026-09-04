# -*- coding: utf-8 -*-
"""PromptScale 全尺度三档工作节点。

模型与推理参数全部来自上游「PromptScale LLM 模型加载器」的 ps模型
连线(PSLLM 句柄),本节点只负责 master 提示词与尺度档位:
UI 选 SFW/Suggestive/NSFW 时在 master 之后追加英文硬覆盖指令,
Auto 则不追加、由 master 按输入词自判。
"""

from .llm_enhancer_core import (
    run_enhance,
    list_system_presets,
    MODE_CHOICES,
    TIER_CHOICES,
    TIER_KEY,
    TIER_OVERRIDE_EN,
    MODE_INSTRUCTION_EN,
    DEFAULT_FULLSCALE,
)


class PSFullScale:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ps模型": ("PSLLM",),
                "想法文本": ("STRING", {"default": "",
                            "multiline": True,
                            "tooltip": "expand 模式填一行想法;upgrade 模式粘贴整段旧提示词。"}),
                "输出模式": (MODE_CHOICES,
                              {"default": MODE_CHOICES[0]}),
                "尺度档位": (TIER_CHOICES,
                              {"default": "Auto (按输入词自动判定)",
                               "tooltip": "SFW/Suggestive/NSFW 为硬覆盖,无视输入词强制该尺度;Auto 由 master 按输入词自判(默认保守)。"}),
                "master预设": (list_system_presets("fullscale"),
                                {"default": DEFAULT_FULLSCALE,
                                 "tooltip": "prompts/fullscale/ 目录下的英文 master,随便命名;新增文件后按 R 刷新出现。"}),
                "master覆盖": ("STRING", {"default": "",
                               "tooltip": "填写后优先于上方下拉;支持纯文件名(去 fullscale 目录找)或任意完整路径,运行时解析、免刷新。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "info")
    FUNCTION = "enhance"
    CATEGORY = "PromptScale/LLM增强"

    def enhance(self, ps模型, 想法文本, 输出模式, 尺度档位,
                master预设, master覆盖=""):
        tier = TIER_KEY.get(尺度档位, "Auto")
        return run_enhance(
            handle=ps模型,
            text=想法文本,
            mode_display=输出模式,
            subdir="fullscale",
            system_preset=master预设,
            mode_instructions=MODE_INSTRUCTION_EN,
            node_label="PromptScale 全尺度三档",
            tier_key=tier,
            tier_override=TIER_OVERRIDE_EN,
            custom_preset=master覆盖,
        )


NODE_CLASS_MAPPINGS = {"PSFullScale": PSFullScale}
NODE_DISPLAY_NAME_MAPPINGS = {"PSFullScale": "PromptScale 全尺度三档"}
