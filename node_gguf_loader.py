# -*- coding: utf-8 -*-
"""PromptScale 本地 GGUF 加载器(PSGGUFLoader)。

与 llama-TE 同款方式:直接扫 ComfyUI/models/LLM/ 下的 .gguf,
用 llama-cpp-python 进程内推理,不用起任何服务。
面板上只有本地推理有意义的字段——地址/密钥/代理在别处,不在这里。

输出与 PSAPILoader 相同的 ps模型(PSLLM)句柄,下游工作节点通用。
"""

import os
import re

from .llm_enhancer_core import PSModelHandle

# 上游读不到模型列表时的兜底项(执行时会被明确报错拦下)
GGUF_EMPTY = "(models/LLM 里没有 GGUF 模型 — 放入后按 R 刷新)"

# 分片 GGUF 只显示第一片: xxx-00001-of-000NN.gguf
_SPLIT_FIRST_RE = re.compile(r"-00001-of-\d+\.gguf$", re.IGNORECASE)


def gguf_models():
    """列出 ComfyUI/models/LLM 下的主模型 GGUF(排除 mmproj 与分片后续片)。"""
    try:
        import folder_paths
        names = folder_paths.get_filename_list("LLM") or []
    except Exception:
        return []
    out = []
    for n in names:
        low = n.lower()
        if not low.endswith(".gguf"):
            continue
        if "mmproj" in low:
            continue
        if "-of-" in low and not _SPLIT_FIRST_RE.search(low):
            continue
        out.append(n)
    return sorted(out)


def resolve_gguf(model_or_override):
    """把下拉值/覆盖输入解析成 GGUF 绝对路径;找不到返回 None。"""
    if not model_or_override:
        return None
    try:
        import folder_paths
        path = folder_paths.get_full_path("LLM", model_or_override)
        if path and os.path.isfile(path):
            return path
        # 覆盖里可能只填了纯文件名(不带子目录)——按 basename 兜底找
        base = os.path.basename(model_or_override)
        for n in folder_paths.get_filename_list("LLM") or []:
            if os.path.basename(n) == base:
                p = folder_paths.get_full_path("LLM", n)
                if p and os.path.isfile(p):
                    return p
    except Exception:
        pass
    return None


class PSGGUFLoader:
    @classmethod
    def INPUT_TYPES(cls):
        models = gguf_models() or [GGUF_EMPTY]
        return {
            "required": {
                "模型": (models,
                          {"tooltip": "models/LLM 里的 GGUF 文件(排除 mmproj,分片只显示第一片)。放了新模型后按 R 刷新。"}),
                "模型覆盖": ("STRING", {"default": "",
                              "tooltip": "填写后优先于上方下拉。填文件名(含子目录路径也可以),下拉过期时在这里手填,免刷新。"}),
                "温度": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0,
                                    "step": 0.01,
                                    "tooltip": "扩写创作类任务 0.7~0.9 合适;想要更稳的改写可降到 0.5。"}),
                "最大token": ("INT", {"default": 2048, "min": 64,
                                       "max": 65536, "step": 64,
                                       "tooltip": "单次生成的长度上限。master 提示词较长时建议 ≥2048。"}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0,
                                     "step": 0.01,
                                     "tooltip": "核采样截断。1.0=不截断;想更稳可试 0.9。"}),
                "top_k": ("INT", {"default": 0, "min": 0, "max": 200,
                                   "step": 1,
                                   "tooltip": "每步只从概率前 K 个候选里采。0=关闭;常用 20~64。"}),
                "重复惩罚": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0,
                                        "step": 0.01,
                                        "tooltip": "1.0=不惩罚;输出复读时可升到 1.1~1.2。"}),
                "随机种子": ("INT", {"default": 0, "min": 0,
                                  "max": 0xFFFFFFFF,
                                  "tooltip": "0=每次随机;填非 0 固定随机种子(可复现)。"}),
                "上下文长度": ("INT", {"default": 8192, "min": 1024,
                                        "max": 131072, "step": 1024,
                                        "tooltip": "对应 llama.cpp 的 n_ctx。本节点任务输出较短,8192 足够;改小可省一点显存。改动后首次执行会重载模型。"}),
                "GPU层数": ("INT", {"default": -1, "min": -1, "max": 999,
                                     "step": 1,
                                     "tooltip": "对应 n_gpu_layers:-1=全部层上 GPU(推荐);0=纯 CPU(显存不够时保命)。改动后首次执行会重载模型。"}),
                "min_p": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0,
                                     "step": 0.01,
                                     "tooltip": "概率下限过滤(比 top_p 更适合高温创作)。0=关闭;Qwen3/3.5 官方推荐 0.0~0.1, temples 建议 0.05 起调。"}),
                "频率惩罚": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0,
                                        "step": 0.01,
                                        "tooltip": "按出现次数惩罚重复词。0=关闭;输出车轱辘话时试 0.3~0.6。"}),
                "存在惩罚": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0,
                                        "step": 0.01,
                                        "tooltip": "只要出现过就惩罚。0=关闭;与频率惩罚二选一微调,别同时开大。"}),
                "思考": ("BOOLEAN", {"default": False,
                              "tooltip": "开=保留模型思考过程(含 <think> 标记原样输出,排查用);关=请求级关闭思考(Qwen3/3.5 等推理模型)并自动剔除思维链,只留干净正文 —— 扩写任务保持关。"}),
            }
        }

    RETURN_TYPES = ("PSLLM",)
    RETURN_NAMES = ("ps模型",)
    FUNCTION = "load"
    CATEGORY = "PromptScale/LLM增强"

    def load(self, 模型, 模型覆盖, 温度, 最大token, top_p, top_k,
             重复惩罚, 随机种子, 上下文长度, GPU层数,
             min_p=0.0, 频率惩罚=0.0, 存在惩罚=0.0, 思考=False):
        override = (模型覆盖 or "").strip()
        model = override or (模型 or "").strip()
        if not model or model.startswith("("):
            raise RuntimeError(
                "没有可用的 GGUF 模型。请把 .gguf 模型放到 ComfyUI/models/LLM/ "
                "后按 R 刷新;或在「模型覆盖」里手填文件名"
                "(如 Qwen3.5-4B-Q4_K_M.gguf)。")
        path = resolve_gguf(model)
        if not path:
            raise RuntimeError(
                f"在 models/LLM 里找不到 GGUF 模型:{model}\n"
                "「模型覆盖」请填文件名(含子目录路径也可以),填好后重新执行。")
        settings = {
            "service": "本地 GGUF (llama.cpp)",
            "base_url": "",
            "api_key": "",
            "model": os.path.basename(model),
            "gguf_path": path,
            "use_system_proxy": False,
            "temperature": float(温度),
            "max_tokens": int(最大token),
            "timeout": 0,
            "top_p": float(top_p),
            "top_k": int(top_k),
            "repeat_penalty": float(重复惩罚),
            "min_p": float(min_p),
            "frequency_penalty": float(频率惩罚),
            "presence_penalty": float(存在惩罚),
            "disable_thinking": not bool(思考),   # 思考开=不禁用;思考关=后台锁定剥离
            "seed": int(随机种子),
            "n_ctx": int(上下文长度),
            "n_gpu_layers": int(GPU层数),
        }
        return (PSModelHandle(settings),)


NODE_CLASS_MAPPINGS = {"PSGGUFLoader": PSGGUFLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"PSGGUFLoader": "PromptScale 本地GGUF 加载器"}
