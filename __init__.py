# -*- coding: utf-8 -*-
"""ComfyUI-PromptScale-LLM

双加载器 + 单工作节点架构:
  PSGGUFLoader  本地GGUF加载器:扫 models/LLM,进程内推理(同 llama-TE)→ PSLLM 句柄
  PSAPILoader   API加载器:Ollama/LM Studio/云端 OpenAI 兼容服务 → PSLLM 句柄
  PSEnhancer    扩写器(合并节点):master 中英文任选(输出语言随 master),
                尺度档位 SFW/Suggestive/NSFW/Auto 对任意 master 生效,
                三档指令可在属性面板/右键菜单自定义(web/tier_editor.js)

两个加载器输出同一种句柄,下游工作节点和连线完全通用。
"""

from .node_gguf_loader import PSGGUFLoader
from .node_api_loader import PSAPILoader
from .node_enhancer import PSEnhancer

NODE_CLASS_MAPPINGS = {
    "PSGGUFLoader": PSGGUFLoader,
    "PSAPILoader": PSAPILoader,
    "PSEnhancer": PSEnhancer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PSGGUFLoader": "PromptScale 本地GGUF 加载器",
    "PSAPILoader": "PromptScale API 加载器",
    "PSEnhancer": "PromptScale 扩写器",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS",
           "WEB_DIRECTORY"]
