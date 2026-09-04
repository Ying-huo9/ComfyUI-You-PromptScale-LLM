# -*- coding: utf-8 -*-
"""ComfyUI-PromptScale-LLM

双加载器 + 双工作节点架构:
  PSGGUFLoader  本地GGUF加载器:扫 models/LLM,进程内推理(同 llama-TE)→ PSLLM 句柄
  PSAPILoader   API加载器:Ollama/LM Studio/云端 OpenAI 兼容服务 → PSLLM 句柄
  PSFullScale   全尺度三档:SFW/Suggestive/NSFW/Auto,接 ps模型 连线
  PSChinese     中文扩写:无档位,自带尺度,接 ps模型 连线

两个加载器输出同一种句柄,下游工作节点和连线完全通用。
"""

from .node_gguf_loader import PSGGUFLoader
from .node_api_loader import PSAPILoader
from .node_fullscale import PSFullScale
from .node_chinese import PSChinese

NODE_CLASS_MAPPINGS = {
    "PSGGUFLoader": PSGGUFLoader,
    "PSAPILoader": PSAPILoader,
    "PSFullScale": PSFullScale,
    "PSChinese": PSChinese,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PSGGUFLoader": "PromptScale 本地GGUF 加载器",
    "PSAPILoader": "PromptScale API 加载器",
    "PSFullScale": "PromptScale 全尺度三档",
    "PSChinese": "PromptScale 中文扩写",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
