# -*- coding: utf-8 -*-
"""PromptScale 扩写器(合并节点,取代原 全尺度三档 + 中文扩写 两节点)。

模型与推理参数全部来自上游加载器的 ps模型 连线(PSLLM 句柄)。
master 预设下拉合并中英文全部预设——输出语言由 master 决定,不再由节点决定;
尺度档位对任意 master 生效:SFW/Suggestive/NSFW 为硬覆盖(UI 选择优先级最高),
Auto 不追加覆盖段、由 master 按输入词自判。

三档指令文本可在 节点属性面板 或 右键菜单「编辑档位指令」中自定义
(前端 tier_editor.js 负责隐藏 widget 与属性同步);留空回退内置指令。
"""

from .llm_enhancer_core import (
    run_enhance,
    list_all_system_presets,
    MODE_CHOICES,
    TIER_CHOICES,
    TIER_KEY,
    TIER_OVERRIDE_EN,
    MODE_INSTRUCTION_EN,
    MODE_INSTRUCTION_ZH,
    DEFAULT_FULLSCALE,
)

_NODE_LABEL = "PromptScale 扩写器"

_TIER_TOOLTIP = (
    "SFW/Suggestive/NSFW 为硬覆盖,无视输入词强制该尺度(UI 选择优先级最高,"
    "压过 master 内部默认与输入词的尺度信号);Auto 不追加覆盖段,由 master "
    "按输入词自判(默认保守)。三档指令文本可在右键菜单「编辑档位指令」或"
    "属性面板自定义。"
)


class PSEnhancer:
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
                               "tooltip": _TIER_TOOLTIP}),
                "master预设": (list_all_system_presets(),
                                {"default": "fullscale/" + DEFAULT_FULLSCALE,
                                 "tooltip": "合并列出 prompts/fullscale/ 与 prompts/chinese/ 下的全部 master;"
                                            "选中文目录的 master → 输出中文提示词,英文目录 → 输出英文。"
                                            "新增文件后按 R 刷新。"}),
                "master覆盖": ("STRING", {"default": "",
                               "multiline": True,
                               "tooltip": "填写后优先于上方下拉;支持 fullscale/xxx、chinese/xxx、纯文件名"
                                          "(两个目录都找)或任意完整路径,运行时解析、免刷新。"}),
                "SFW指令": ("STRING", {"default": TIER_OVERRIDE_EN["SFW"],
                             "multiline": True,
                             "tooltip": "选 SFW 硬档位时追加的指令;留空=内置兜底。可在属性面板或右键菜单编辑。"}),
                "Suggestive指令": ("STRING", {"default": TIER_OVERRIDE_EN["Suggestive"],
                             "multiline": True,
                             "tooltip": "选 Suggestive 硬档位时追加的指令;留空=内置兜底。可在属性面板或右键菜单编辑。"}),
                "NSFW指令": ("STRING", {"default": TIER_OVERRIDE_EN["NSFW"],
                             "multiline": True,
                             "tooltip": "选 NSFW 硬档位时追加的指令;留空=内置兜底。可在属性面板或右键菜单编辑。"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "info")
    FUNCTION = "enhance"
    CATEGORY = "PromptScale/LLM增强"

    def enhance(self, ps模型, 想法文本, 输出模式, 尺度档位,
                master预设, master覆盖="", SFW指令="", Suggestive指令="",
                NSFW指令=""):
        tier = TIER_KEY.get(尺度档位, "Auto")
        # 子目录判定:决定模式指令语言(中文 master → 中文指令)
        ref = ((master覆盖 or "").strip() or (master预设 or "").strip())
        subdir = "chinese" if ref.startswith("chinese/") else "fullscale"
        return run_enhance(
            handle=ps模型,
            text=想法文本,
            mode_display=输出模式,
            subdir=subdir,
            system_preset=master预设,
            mode_instructions=(MODE_INSTRUCTION_ZH if subdir == "chinese"
                               else MODE_INSTRUCTION_EN),
            node_label=_NODE_LABEL,
            tier_key=tier,
            tier_texts={"SFW": SFW指令,
                        "Suggestive": Suggestive指令,
                        "NSFW": NSFW指令},
            custom_preset=master覆盖,
        )


NODE_CLASS_MAPPINGS = {"PSEnhancer": PSEnhancer}
NODE_DISPLAY_NAME_MAPPINGS = {"PSEnhancer": "PromptScale 扩写器"}
