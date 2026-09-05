# -*- coding: utf-8 -*-
"""PromptScale API 加载器(PSAPILoader)。

OpenAI 兼容 HTTP 后端:Ollama/LM Studio/vLLM 本地服务或 DeepSeek 等
云端 API。选服务自动填官方端点,模型下拉实时读取(GET /models,失败转
Ollama /api/tags)。面板上只有 HTTP 调用有意义的字段。

输出与 PSGGUFLoader 相同的 ps模型(PSLLM)句柄,下游工作节点通用。
"""

from .llm_enhancer_core import (
    SERVICE_CHOICES,
    PROXY_CHOICES,
    LOCAL_DEFAULT_BASE_URL,
    MODEL_FALLBACKS,
    resolve_service,
    fetch_remote_models,
    sanitize_key,
    PSModelHandle,
)

MODEL_FALLBACK = "(无法读取模型列表 — 启动服务/填好密钥后按 R 刷新)"


def _loader_models(base_url, api_key, service):
    """尽力读取 HTTP 服务模型列表:上游双通道 → 服务内置清单 → 兜底占位项。"""
    models = fetch_remote_models(base_url, sanitize_key(api_key))
    if not models:
        models = MODEL_FALLBACKS.get(service, [])
    return list(models) or [MODEL_FALLBACK]


class PSAPILoader:
    @classmethod
    def INPUT_TYPES(cls):
        # 模型下拉按默认服务(本地 Ollama/LM Studio)尽力读取一次;
        # 换服务或填好 Key 后按 R 刷新重新生成,或在「模型覆盖」手填。
        models = _loader_models(LOCAL_DEFAULT_BASE_URL, "",
                                "本地 (Ollama/LM Studio/vLLM)")
        return {
            "required": {
                "服务来源": (SERVICE_CHOICES,
                             {"default": "本地 (Ollama/LM Studio/vLLM)",
                              "tooltip": "本地服务留空地址即默认端点;云端选对应服务自动填官方端点;「自定义 OpenAI 兼容」必须手填地址。想用 models/LLM 里的 GGUF 请改用「PromptScale 本地GGUF 加载器」。"}),
                "连接地址": ("STRING", {"default": "",
                             "tooltip": "留空=用所选服务的默认端点;本地一般是 http://127.0.0.1:11434/v1(Ollama)。智能解析:粘贴完整 /chat/completions 端点会自动剥掉后缀;以 # 结尾则强制原样使用。"}),
                "API密钥": ("STRING", {"default": "",
                             "tooltip": "云端服务必填;本地留空。会自动清洗:复制粘贴带引号/省略号/空格换行也能正常识别。会存进工作流 JSON,分享前注意删除。"}),
                "模型": (models,
                          {"tooltip": "实时读取所选服务的模型列表(按 R 刷新更新)。下拉过期时用「模型覆盖」手填。"}),
                "模型覆盖": ("STRING", {"default": "",
                              "tooltip": "填写后优先于上方「模型」下拉,填模型名;下拉列表过期时在这里手填即可,免刷新。"}),
                "温度": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0,
                                    "step": 0.01,
                                    "tooltip": "扩写创作类任务 0.7~0.9 合适;想要更稳的改写可降到 0.5。"}),
                "最大token": ("INT", {"default": 2048, "min": 64,
                                       "max": 65536, "step": 64,
                                       "tooltip": "单次生成的长度上限。master 提示词较长时建议 ≥2048。"}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0,
                                     "step": 0.01,
                                     "tooltip": "OpenAI 标准核采样参数。1.0=不截断;想更稳可试 0.9。"}),
                "随机种子": ("INT", {"default": 0, "min": 0,
                                  "max": 0xFFFFFFFF,
                                  "tooltip": "OpenAI 标准参数。0=不指定(每次随机);填非 0 固定随机种子(可复现,服务端支持时生效)。"}),
                "超时秒": ("INT", {"default": 600, "min": 10, "max": 3600,
                                    "step": 10,
                                    "tooltip": "HTTP 请求超时。大模型/长输出适当调大。"}),
                "代理": (PROXY_CHOICES,
                          {"default": "直连",
                           "tooltip": "本地服务/国内 API 选「直连」;访问 OpenAI 等需代理的服务选「走系统代理」。"}),
                "频率惩罚": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0,
                                        "step": 0.01,
                                        "tooltip": "OpenAI 标准参数:按出现次数惩罚重复。0=关闭;输出车轱辘话时试 0.3~0.6。服务端不支持时会被忽略。"}),
                "存在惩罚": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0,
                                        "step": 0.01,
                                        "tooltip": "OpenAI 标准参数:出现过就惩罚。0=关闭;与频率惩罚二选一微调。服务端不支持时会被忽略。"}),
                "思考": ("BOOLEAN", {"default": False,
                              "tooltip": "开=保留模型思考过程(含 <think> 标记原样输出,排查用);关=Ollama 本地模型发 think:false、云端推理模型返回自动剥离思维链,只留干净正文 —— 扩写任务保持关。"}),
            }
        }

    RETURN_TYPES = ("PSLLM",)
    RETURN_NAMES = ("ps模型",)
    FUNCTION = "load"
    CATEGORY = "PromptScale/LLM增强"

    def load(self, 服务来源, 连接地址, API密钥, 模型, 模型覆盖,
             温度, 最大token, top_p, 随机种子, 超时秒, 代理,
             频率惩罚=0.0, 存在惩罚=0.0, 思考=False):
        override = (模型覆盖 or "").strip()
        model = override or (模型 or "").strip()

        base_url, api_key = resolve_service(服务来源, 连接地址, API密钥)
        if not model or model.startswith("(无法读取"):
            raise RuntimeError(
                "没有可用的模型名。可能原因:\n"
                "1. 本地服务未启动 —— 先启动 Ollama(`ollama serve`)或 LM Studio Local Server;\n"
                "2. 云端服务密钥未填/填错 —— 填好后按 R 刷新重新读取模型列表;\n"
                "3. 下拉列表过期 —— 按 R 刷新,或在「模型覆盖」里手填模型名;\n"
                "4. 想直接用 models/LLM 里的 GGUF —— 改用「PromptScale 本地GGUF 加载器」。")
        settings = {
            "service": 服务来源,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "use_system_proxy": (代理 == "走系统代理"),
            "temperature": float(温度),
            "max_tokens": int(最大token),
            "timeout": int(超时秒),
            "top_p": float(top_p),
            "top_k": 0,
            "repeat_penalty": 1.0,
            "frequency_penalty": float(频率惩罚),
            "presence_penalty": float(存在惩罚),
            "disable_thinking": not bool(思考),   # 思考开=不禁用;思考关=后台锁定剥离
            "seed": int(随机种子),
        }
        return (PSModelHandle(settings),)


NODE_CLASS_MAPPINGS = {"PSAPILoader": PSAPILoader}
NODE_DISPLAY_NAME_MAPPINGS = {"PSAPILoader": "PromptScale API 加载器"}
