# -*- coding: utf-8 -*-
"""
PromptScale LLM — 共享核心。

两个节点共用本模块:
  - 全尺度三档节点(英文 master,UI 选 SFW/Suggestive/NSFW 硬覆盖)
  - 中文扩写节点(中文 master,自带尺度逻辑,无档位)

master 文件不需要任何 frontmatter / 前缀 —— 放进对应目录、随便命名即可:
  prompts/fullscale/  → 英文全尺度 master(节点1 的下拉列表)
  prompts/chinese/    → 中文 master(节点2 的下拉列表)

若文件头部碰巧带 --- ... --- 块,加载时会自动剥离,不参与任何逻辑。
零第三方依赖:仅 Python 标准库 urllib,Ollama / LM Studio / vLLM 通吃。
"""

import os
import json
import time
import glob
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------

NODE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(NODE_DIR, "prompts")
FULLSCALE_DIR = os.path.join(PROMPTS_DIR, "fullscale")   # 英文全尺度 master
CHINESE_DIR = os.path.join(PROMPTS_DIR, "chinese")       # 中文 master

MODE_CHOICES = [
    "expand — 想法扩写成完整提示词",
    "upgrade — 旧提示词升级改写",
]
MODE_KEY = {
    "expand — 想法扩写成完整提示词": "expand",
    "upgrade — 旧提示词升级改写": "upgrade",
}

# 仅全尺度节点使用(中文 master 自带尺度,无档位 UI)
TIER_CHOICES = [
    "SFW (保守)",
    "Suggestive (擦边/性感氛围)",
    "NSFW (直接描写)",
    "Auto (按输入词自动判定)",
]
TIER_KEY = {
    "SFW (保守)": "SFW",
    "Suggestive (擦边/性感氛围)": "Suggestive",
    "NSFW (直接描写)": "NSFW",
    "Auto (按输入词自动判定)": "Auto",
}

# 档位覆盖指令(英文,追加在全尺度 master 之后;UI 开关优先级最高)
TIER_OVERRIDE_EN = {
    "SFW": (
        "[OUTPUT SCALE OVERRIDE — UI switch, highest priority]\n"
        "The user selected the SFW tier explicitly. Output a fully-clothed, "
        "everyday/fashion/mood portrait at the conservative end of the scale. "
        "Keep the subject's identity and concrete details from the input, but "
        "dress them modestly and keep all sensuality implied at most. "
        "Do not escalate to Suggestive or NSFW regardless of input wording."
    ),
    "Suggestive": (
        "[OUTPUT SCALE OVERRIDE — UI switch, highest priority]\n"
        "The user selected the Suggestive tier explicitly. Output implied "
        "sensuality only: clinging fabric, exposed shoulders, wet look, short "
        "hem, smoldering gaze. NO explicit anatomy, NO nudity, NO sex acts. "
        "Do not downgrade to plain SFW either — keep the charged, teasing "
        "register the corpus is known for."
    ),
    "NSFW": (
        "[OUTPUT SCALE OVERRIDE — UI switch, highest priority]\n"
        "The user selected the NSFW tier explicitly. If the input was SFW or "
        "Suggestive, escalate the scene into the corpus's direct descriptive "
        "register (explicit anatomy / implied acts written plainly, matching "
        "the corpus's raw, factual style). Keep every concrete subject detail "
        "that was in the input; rewrite the rest up to NSFW. Never moralize."
    ),
}

# 全尺度节点(英文 master)的模式指令
MODE_INSTRUCTION_EN = {
    "expand": (
        "The user message below is a one-line idea. Expand it into the single "
        "full prompt paragraph per the framework above. Output the prompt only."
    ),
    "upgrade": (
        "The user message below is an EXISTING prompt to be upgraded. Fully "
        "rewrite it into a new full prompt per the framework above: keep the "
        "subject's identity, outfit, scene and all concrete details that are "
        "still wanted, restructure the prose (sentence flow, front-loaded "
        "lighting, atmosphere ending), and obey the selected output scale. "
        "Do not just lightly edit — deliver a complete, better replacement. "
        "Output the prompt only."
    ),
}

# 中文节点的模式指令
MODE_INSTRUCTION_ZH = {
    "expand": (
        "下面的用户消息是一行想法。请按上面框架把它扩写成唯一一段完整提示词,"
        "只输出提示词本身。"
    ),
    "upgrade": (
        "下面的用户消息是一段待升级的旧提示词。请按上面框架整体重写为新的完整"
        "提示词:保留仍需要的主体身份、服装、场景与全部具体细节,重构行文"
        "(句子节奏、光线前置、氛围收尾)。不要小修小补,要交付完整且更好的"
        "替代版本。只输出提示词本身。"
    ),
}

# 目录为空时下拉里的兜底名(执行时会报错并列出实际可用文件)
DEFAULT_FULLSCALE = "English_Master_v2.md"
DEFAULT_CHINESE = "Chinese_Master_Refined.md"

# ---------------------------------------------------------------------------
# 服务预设(加载器节点用)
# ---------------------------------------------------------------------------

# 服务来源 → 默认 base_url / api_key。None = 自定义,必须手填 base_url。
SERVICES = {
    "本地 (Ollama/LM Studio/vLLM)": {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",   # Ollama 不校验,占位即可
    },
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1"},
    "硅基流动 SiliconFlow": {"base_url": "https://api.siliconflow.cn/v1"},
    "通义千问 DashScope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    "Kimi (Moonshot)": {"base_url": "https://api.moonshot.cn/v1"},
    "智谱 GLM": {"base_url": "https://open.bigmodel.cn/api/paas/v4"},
    "OpenAI": {"base_url": "https://api.openai.com/v1"},
    "自定义 OpenAI 兼容": None,
}
SERVICE_CHOICES = list(SERVICES.keys())

PROXY_CHOICES = ["直连", "走系统代理"]

LOCAL_DEFAULT_BASE_URL = SERVICES["本地 (Ollama/LM Studio/vLLM)"]["base_url"]

# 智谱 GLM 没有公开的模型列表接口 —— 读不到时用内置清单兜底
# (做法同 comfyui_prompt_assistant;列表会过时,可用「模型覆盖」手填最新名)
MODEL_FALLBACKS = {
    "智谱 GLM": [
        "glm-4-flash", "glm-4-air", "glm-4-plus",
        "glm-4-long", "glm-4v-plus",
    ],
}


def sanitize_key(key):
    """API Key 清洗(comfyui_prompt_assistant 同款容错):
    复制粘贴常见事故 —— 首尾引号、省略号截断(…/...)、夹带空格换行制表符
    —— 全部救回来,避免“明明填了 Key 却 401”。
    """
    k = (key or "").strip()
    k = k.strip('"').strip("'").strip("`")
    k = k.replace("…", "")          # 省略号(单字符)
    k = k.replace("...", "")        # 三个英文句点
    k = "".join(ch for ch in k if not ch.isspace())
    return k


def clean_base_url(url):
    """base_url 智能解析(comfyui_prompt_assistant 同款规则):
    - 去首尾空白/引号;
    - 以 # 结尾    → # 前的部分强制作为最终地址,不再做任何推断;
    - 已含 /chat/completions → 视为粘贴了完整端点,剥掉后缀得到 base
      (本模块之后统一在 base 后追加 /chat/completions,避免拼重)。
    """
    u = (url or "").strip().strip('"').strip("'")
    if u.endswith("#"):
        return u[:-1].rstrip("/")
    if u.rstrip("/").endswith("/chat/completions"):
        return u.rstrip("/")[: -len("/chat/completions")]
    return u.rstrip("/")


def is_ollama_native(base_url):
    """是否按 Ollama 原生 API 路由(comfyui_prompt_assistant 的智能路由规则):
    本地地址(127.0.0.1 / localhost / :11434 / ollama 主机名)且 未带 /v1
    后缀 → 原生 /api/chat、/api/tags;带 /v1 → OpenAI 兼容。
    LM Studio / vLLM 请使用带 /v1 的地址(工具提示里已说明);
    云端服务均为远程地址,永远不会误判为原生。
    """
    u = (base_url or "").lower()
    local = (("//127.0.0.1" in u) or ("//localhost" in u)
             or (":11434" in u) or ("//ollama" in u))
    no_v1 = not u.rstrip("/").endswith("/v1")
    return local and no_v1


def resolve_service(service, base_url="", api_key=""):
    """把服务来源选择解析为 (base_url, api_key)。

    base_url 留空 → 用所选服务默认;填了 → 用户覆盖(先过智能清洗)。
    api_key 先过清洗(去引号/省略号/空白)。本地服务无密钥时自动填
    "ollama" 占位;自定义服务密钥允许为空。
    """
    preset = SERVICES.get(service)
    key = sanitize_key(api_key)
    if preset is None:  # 自定义
        url = clean_base_url(base_url)
        if not url:
            raise RuntimeError(
                "服务来源选择了「自定义 OpenAI 兼容」,请填写连接地址"
                "(如 http://127.0.0.1:11434/v1 或任意 OpenAI 兼容端点)。")
        return url, key
    url = clean_base_url(base_url) or preset["base_url"]
    return url, (key or preset.get("api_key", ""))


def _http_get_json(url, api_key="", timeout=4.0, use_system_proxy=False):
    """GET 并解析 JSON;返回 (body, status)。失败返回 (None, None/err_code)。"""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    if use_system_proxy:
        opener = urllib.request.build_opener()
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=float(timeout)) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, None


def fetch_remote_models(base_url, api_key="", timeout=4.0, use_system_proxy=False):
    """读取上游服务的模型列表,返回模型 id 列表;读不到返回 None。

    双通道(comfyui_prompt_assistant 同款策略):
      1. OpenAI 兼容   GET {base}/models          → data[].id
      2. Ollama 原生   GET {ollama}/api/tags       → models[].name
         (先剥掉 /v1 后缀;Ollama 部分版本的 /v1/models 兼容性不如原生 tags)
    加载器节点的「模型」下拉即来自这里 —— 服务启动/新增模型后,
    在 ComfyUI 里按 R(刷新)或重开页面即可重新读取。
    """
    base = clean_base_url(base_url)
    if not base:
        return None
    # 通道1:OpenAI 兼容 /models
    body, status = _http_get_json(base + "/models", api_key, timeout,
                                  use_system_proxy)
    ids = []
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            for item in data:
                mid = item.get("id") if isinstance(item, dict) else None
                if isinstance(mid, str) and mid:
                    ids.append(mid)
    if ids:
        return sorted(set(ids))
    if status == 401:
        return None   # Key 无效,不 fallback,让加载器明确提示
    # 通道2:Ollama 原生 /api/tags(剥掉 /v1 后缀再试)
    root = base[:-3] if base.endswith("/v1") else base
    if is_ollama_native(root) or root != base:
        body, _ = _http_get_json(root + "/api/tags", "", timeout,
                                 use_system_proxy)
        names = []
        if isinstance(body, dict):
            models = body.get("models")
            if isinstance(models, list):
                for item in models:
                    mid = item.get("name") if isinstance(item, dict) else None
                    if isinstance(mid, str) and mid:
                        names.append(mid)
        if names:
            return sorted(set(names))
    return None


class PSModelHandle:
    """加载器输出给下游的模型句柄(自定义类型 PSLLM)。

    只携带配置,不持有真实连接 —— 每次执行时由工作节点按需发起请求,
    与 llama.cpp 类加载器的"句柄在下,配置跟句柄走"范式一致。
    """

    def __init__(self, settings):
        self.settings = dict(settings)

    def __repr__(self):
        s = self.settings
        return (f"<PSModelHandle {s.get('service')} | {s.get('base_url')} "
                f"| model={s.get('model')}>")


# ---------------------------------------------------------------------------
# 预设扫描与加载
# ---------------------------------------------------------------------------

def _preset_dir(subdir):
    """subdir: 'fullscale' | 'chinese' → 对应目录绝对路径。"""
    return FULLSCALE_DIR if subdir == "fullscale" else CHINESE_DIR


def list_system_presets(subdir):
    """扫描对应目录下的 *.md,作为下拉选项,按修改时间倒序(新的在前)。

    ComfyUI 只在节点/工作流加载时调用一次,中途新增的文件不会自动出现
    在下拉里——此时在 custom_preset 里填文件名即可(运行时解析,免重载)。
    """
    d = _preset_dir(subdir)
    files = []
    for p in glob.glob(os.path.join(d, "*.md")):
        files.append((os.path.basename(p), os.path.getmtime(p)))
    files.sort(key=lambda x: -x[1])
    names = [name for name, _ in files]
    if not names:
        names = [DEFAULT_FULLSCALE if subdir == "fullscale" else DEFAULT_CHINESE]
    return names


def list_all_system_presets():
    """合并扫描 fullscale/ 与 chinese/ 两个目录,返回带目录前缀的下拉列表。

    选项形如 "fullscale/English_Master_v2.md" / "chinese/Chinese_Master_Refined.md",
    按修改时间倒序混排(新的在前)。供合并后的单一扩写节点使用。
    """
    files = []
    for subdir in ("fullscale", "chinese"):
        for p in glob.glob(os.path.join(_preset_dir(subdir), "*.md")):
            files.append((subdir + "/" + os.path.basename(p),
                          os.path.getmtime(p)))
    files.sort(key=lambda x: -x[1])
    names = [name for name, _ in files]
    if not names:
        names = ["fullscale/" + DEFAULT_FULLSCALE]
    return names


def resolve_preset_path(name_or_path, subdir):
    """把预设名解析为真实文件路径。

    规则(custom_preset 与下拉值统一走这里):
      - "fullscale/xxx" 或 "chinese/xxx" 前缀 → 去对应子目录找(合并下拉用)
      - 纯文件名        → 先去对应子目录找,找不到再试另一个子目录(漏 .md 自动补)
      - 含 / \\ : 的路径 → 直接当作文件路径读取(支持目录外任意位置)
    找不到时抛错并列出全部可用预设。
    """
    raw = (name_or_path or "").strip().strip('"').strip("'")
    if not raw:
        raise RuntimeError("预设名为空。")
    # 合并下拉的目录前缀形式
    for _pre in ("fullscale/", "chinese/"):
        if raw.startswith(_pre):
            subdir = _pre[:-1]
            raw = raw[len(_pre):]
            break
    has_sep = ("/" in raw) or ("\\" in raw) or (":" in raw)
    if has_sep:
        path = os.path.abspath(raw)
    else:
        cand = raw if raw.lower().endswith(".md") else raw + ".md"
        path = os.path.join(_preset_dir(subdir), cand)
        if not os.path.exists(path):
            path = os.path.join(_preset_dir(subdir), raw)
        if not os.path.exists(path):
            # 跨目录兜底:另一边有同名/同名.md 就用它
            other = "chinese" if subdir == "fullscale" else "fullscale"
            for c in (cand, raw):
                p2 = os.path.join(_preset_dir(other), c)
                if os.path.exists(p2):
                    path = p2
                    break
    if not os.path.exists(path) or not os.path.isfile(path):
        avail = "\n  ".join(list_system_presets(subdir)) or "(空)"
        raise RuntimeError(
            f"找不到系统提示词文件: {raw!r}\n"
            f"已尝试路径: {path}\n"
            f"当前可用预设:\n  {avail}\n"
            f"提示:纯文件名 → 去对应子目录找;含 / 或 \\\\ 或 : → 当作路径直接读取。"
        )
    return path


def strip_frontmatter(text):
    """宽容剥离文件头部的 --- ... --- 块(如果有的话)。

    master 文件不要求任何 frontmatter;这里剥离只是防止用户从旧版
    拷来的文件带着 YAML 头污染 system prompt,不做任何语义解析。
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].strip()
    return text


def load_system_prompt(name_or_path, subdir):
    """读取 master → {body, path}。custom_preset 与下拉值都先过 resolve_preset_path。"""
    path = resolve_preset_path(name_or_path, subdir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except Exception as e:
        raise RuntimeError(f"系统提示词文件读取失败: {path}({e})")
    if not text:
        raise RuntimeError(f"系统提示词文件为空: {path}")
    body = strip_frontmatter(text)
    if not body:
        raise RuntimeError(f"系统提示词文件去掉头部 --- 块后为空: {path}")
    return {"body": body, "path": path}


def preset_info(preset_path, source):
    """info JSON 里通用的预设元信息。"""
    return {
        "system_preset": os.path.basename(preset_path),
        "preset_path": preset_path,
        "preset_size": os.path.getsize(preset_path),
        "preset_mtime": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(os.path.getmtime(preset_path))),
        "source": source,
    }


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------

def strip_think(text):
    """剥离思考模型的思维链输出(comfyUI-llama-TE 同款清洗规则):
    - 成对 <think>...</think>(含属性变体)整块删除;
    - 只有 </think> 结尾的(思考被 max_tokens 截断后仍关闭了)把开头整段删掉;
    - 残留的裸 <think>/</think> 标记一并清掉。
    适用于 Qwen3/3.5、DeepSeek-R1、GLM-Thou、nemotron 等一切 thinking 模型。
    """
    import re
    if not isinstance(text, str) or not text:
        return text or ""
    cleaned = re.sub(r"<think\b[^>]*>.*?</think>", "", text,
                     flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"</think>", cleaned, flags=re.IGNORECASE):
        cleaned = re.sub(r"^.*?</think>\s*", "", cleaned, count=1,
                         flags=re.DOTALL | re.IGNORECASE)
    # 开头就是 <think> 且全文没有闭合 → 思考被 max_tokens 截断,整段视为思维链
    if re.match(r"^\s*<think\b", cleaned, flags=re.IGNORECASE) \
            and not re.search(r"</think>", cleaned, flags=re.IGNORECASE):
        return ""
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def _ollama_native_chat(base_url, api_key, model, temperature, max_tokens,
                        messages, timeout, use_system_proxy,
                        top_p=1.0, seed=0,
                        frequency_penalty=0.0, presence_penalty=0.0,
                        disable_thinking=True):
    """Ollama 原生 /api/chat(base_url 不带 /v1 时的智能路由)。

    请求/响应结构与 OpenAI 兼容端点不同,此处做双向转换:
    messages 通用;参数进 options{temperature, num_predict, top_p, seed}。
    """
    url = base_url.rstrip("/") + "/api/chat"
    options = {
        "temperature": float(temperature),
        "num_predict": int(max_tokens),
    }
    if top_p is not None and float(top_p) != 1.0:
        options["top_p"] = float(top_p)
    if float(frequency_penalty or 0.0) != 0.0:
        options["frequency_penalty"] = float(frequency_penalty)
    if float(presence_penalty or 0.0) != 0.0:
        options["presence_penalty"] = float(presence_penalty)
    if seed and int(seed) != 0:
        options["seed"] = int(seed)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
        "keep_alive": 0,   # 用完即卸载,不常驻显存(prompt_assistant 同款)
    }
    if disable_thinking:
        payload["think"] = False   # Ollama 0.9+ 思考模型开关;老版本/非思考模型可能报错,下面兜底重试
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    if use_system_proxy:
        opener = urllib.request.build_opener()
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    try:
        with opener.open(req, timeout=float(timeout)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        # 老版 Ollama / 非思考模型不认识 think 字段 → 去掉重试一次
        if disable_thinking and "think" in payload and e.code in (400, 500):
            payload.pop("think", None)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")
            try:
                with opener.open(req, timeout=float(timeout)) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e2:
                detail2 = ""
                try:
                    detail2 = e2.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                raise RuntimeError(f"HTTP {e2.code} — {detail2}")
            except urllib.error.URLError as e2:
                raise RuntimeError(
                    f"无法连接 {base_url}({getattr(e2, 'reason', e2)})。"
                    f"请确认 Ollama 已运行 `ollama serve` 并已 `ollama pull {model}`。")
        else:
            raise RuntimeError(f"HTTP {e.code} — {detail}")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(
            f"无法连接 {base_url}({reason})。请确认 Ollama 已运行 `ollama serve`"
            f" 并已 `ollama pull {model}`。")
    latency = time.time() - t0
    try:
        content = body["message"]["content"]
    except (KeyError, TypeError):
        raise RuntimeError(f"Ollama 原生返回格式异常: {str(body)[:300]}")
    if disable_thinking:
        content = strip_think(content or "")
    usage = {
        "prompt_eval_count": body.get("prompt_eval_count"),
        "eval_count": body.get("eval_count"),
    }
    return (content or "").strip(), usage, latency


def chat_completion(base_url, api_key, model, temperature, max_tokens,
                    messages, timeout, use_system_proxy=False,
                    top_p=1.0, seed=0,
                    frequency_penalty=0.0, presence_penalty=0.0,
                    disable_thinking=True):
    """OpenAI 兼容 chat/completions 请求(标准库实现)。

    智能路由(base_url 不带 /v1 且指向 Ollama → 原生 /api/chat);
    默认绕过系统代理(本地服务/国内直连 API 都更稳);需要代理才能访问的
    服务(如 OpenAI)传 use_system_proxy=True 走系统代理。
    top_p / seed / frequency_penalty / presence_penalty 为 OpenAI 标准字段;
    seed=0 表示不指定(随机);惩罚类 0 表示不启用。
    disable_thinking=True 时:Ollama 原生路由发 think:false,
    并对所有返回统一剥离 <think> 思维链(thinking 模型输出混链兜底)。
    """
    base = clean_base_url(base_url)
    if is_ollama_native(base):
        return _ollama_native_chat(base, api_key, model, temperature,
                                   max_tokens, messages, timeout,
                                   use_system_proxy, top_p=top_p, seed=seed,
                                   frequency_penalty=frequency_penalty,
                                   presence_penalty=presence_penalty,
                                   disable_thinking=disable_thinking)

    url = base + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    if top_p is not None and float(top_p) != 1.0:
        payload["top_p"] = float(top_p)
    if float(frequency_penalty or 0.0) != 0.0:
        payload["frequency_penalty"] = float(frequency_penalty)
    if float(presence_penalty or 0.0) != 0.0:
        payload["presence_penalty"] = float(presence_penalty)
    if seed and int(seed) != 0:
        payload["seed"] = int(seed)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)

    if use_system_proxy:
        opener = urllib.request.build_opener()
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    try:
        with opener.open(req, timeout=float(timeout)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        if e.code == 401:
            raise RuntimeError(
                "HTTP 401 — API Key 无效或未填。请检查加载器里的「API密钥」"
                f"(注意别混入引号/空格)。服务端信息: {detail}")
        raise RuntimeError(f"HTTP {e.code} — {detail}")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(
            f"无法连接 {base}({reason})。请确认本地模型服务已启动:"
            f"Ollama 需运行 `ollama serve` 并 `ollama pull {model}`;"
            f"LM Studio 需在设置中开启 Local Server。"
        )
    latency = time.time() - t0

    try:
        message = body["choices"][0]["message"]
        content = message.get("content")
        usage = body.get("usage", {})
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"返回格式异常(非 OpenAI 兼容结构): {str(body)[:300]}"
        )
    if disable_thinking:
        # 兜底剥离:部分服务(尤其本地 vLLM/LM Studio 跑 thinking GGUF)
        # 会把 <think> 思维链直接混进 content,而不是放到 reasoning_content
        content = strip_think(content or "")
    return (content or "").strip(), usage, latency


# ---------------------------------------------------------------------------
# 本地 GGUF 后端(llama.cpp 进程内推理,无需任何外部服务)
# ---------------------------------------------------------------------------

GGUF_SERVICE = "本地 GGUF (llama.cpp)"

# 单槽缓存:只保留最近一次加载的模型;换模型时释放旧实例归还显存/内存
_GGUF_CACHE = {"key": None, "llm": None}


def chat_gguf(gguf_path, temperature, max_tokens, messages,
              top_p=1.0, top_k=0, repeat_penalty=1.0, seed=0,
              n_ctx=8192, n_gpu_layers=-1,
              min_p=0.0, frequency_penalty=0.0, presence_penalty=0.0,
              disable_thinking=True):
    """用 llama-cpp-python 在 ComfyUI 进程内直接跑 GGUF 模型。

    缓存键 = (路径, n_ctx, n_gpu_layers):同模型同参数连续执行不重复加载;
    换模型或改加载参数自动释放旧实例归还显存/内存。
    采样参数全量对齐 llama.cpp:top_p / top_k(0=显式关闭)/ min_p / repeat_penalty
    / frequency_penalty / presence_penalty;seed=0 表示不指定(每次随机)。
    disable_thinking=True:
      - 通过 chat_template_kwargs(enable_thinking=False)请求关闭思考
        (参数按 llama-cpp-python 版本兼容过滤,老版本自动跳过,TypeError 自动去参重试);
      - 输出统一剥离 <think>...</think> 思维链(截断兜底)。
    返回 (content, usage, latency),与 chat_completion 同构。
    """
    import inspect
    try:
        from llama_cpp import Llama
    except ImportError as e:
        raise RuntimeError(
            "本机未安装 llama-cpp-python,无法使用「本地 GGUF」后端。\n"
            "请在 ComfyUI 的 python 环境里执行:\n"
            "  python -m pip install llama-cpp-python") from e

    cache_key = (gguf_path, int(n_ctx), int(n_gpu_layers))
    llm = _GGUF_CACHE["llm"] if _GGUF_CACHE["key"] == cache_key else None
    if llm is None:
        old = _GGUF_CACHE["llm"]
        _GGUF_CACHE["key"] = None
        _GGUF_CACHE["llm"] = None
        if old is not None:
            try:
                if hasattr(old, "close"):
                    old.close()
            except Exception:
                pass
            del old
        import gc
        gc.collect()
        try:
            llm = Llama(model_path=gguf_path, n_ctx=int(n_ctx),
                        n_gpu_layers=int(n_gpu_layers), verbose=False)
        except Exception as e:
            raise RuntimeError(
                f"GGUF 模型加载失败:{gguf_path}\n{e}") from e
        _GGUF_CACHE["key"] = cache_key
        _GGUF_CACHE["llm"] = llm

    # 按当前 llama-cpp-python 版本过滤参数(comfyUI-llama-TE 同款兼容策略):
    # presence_penalty / present_penalty 新旧版本名不同,自动换名;
    # 版本不支持的键(如 min_p / chat_template_kwargs)直接丢弃,不报错。
    params = {
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "top_p": float(top_p),
        "top_k": int(top_k),
        "repeat_penalty": float(repeat_penalty),
        "min_p": float(min_p),
        "frequency_penalty": float(frequency_penalty),
        "presence_penalty": float(presence_penalty),
    }
    if disable_thinking:
        params["chat_template_kwargs"] = {"enable_thinking": False}
    if int(seed or 0) != 0:
        params["seed"] = int(seed)
    # 0/中性值不传(0=关闭该过滤器);top_k 例外:必须显式传 0 才是"关闭",
    # 不传会用 llama-cpp-python 默认的 40
    keep_zero = ("max_tokens", "temperature", "seed", "top_k")
    params = {k: v for k, v in params.items()
              if k in keep_zero
              or (v is not None and not (isinstance(v, (int, float)) and v == 0))}

    try:
        sig = inspect.signature(llm.create_chat_completion)
        allowed = sig.parameters
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                         for p in allowed.values())
    except (TypeError, ValueError):
        allowed, has_var_kw = None, True

    if allowed is not None:
        if "presence_penalty" in params and "presence_penalty" not in allowed \
                and "present_penalty" in allowed:
            params["present_penalty"] = params.pop("presence_penalty")
        if "present_penalty" in params and "present_penalty" not in allowed \
                and "presence_penalty" in allowed:
            params["presence_penalty"] = params.pop("present_penalty")
        if not has_var_kw:
            params = {k: v for k, v in params.items() if k in allowed}

    t0 = time.time()
    try:
        resp = llm.create_chat_completion(**params)
    except TypeError as e:
        # 老版本不认 chat_template_kwargs → 去掉重试一次(仅剥离层兜底思考)
        if "chat_template_kwargs" in params and "chat_template_kwargs" in str(e):
            params.pop("chat_template_kwargs", None)
            try:
                resp = llm.create_chat_completion(**params)
            except Exception as e2:
                raise RuntimeError(f"本地 GGUF 推理失败:{e2}") from e2
        else:
            raise RuntimeError(f"本地 GGUF 推理失败:{e}") from e
    except Exception as e:
        raise RuntimeError(f"本地 GGUF 推理失败:{e}") from e
    latency = time.time() - t0

    try:
        content = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage") or {}
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"本地 GGUF 返回结构异常:{str(resp)[:300]}")
    if disable_thinking:
        content = strip_think(content or "")
        if not content:
            raise RuntimeError(
                "模型只输出了思考过程就被 max_tokens 截断,剥离后没有正文。"
                "解决办法(任选其一):① 调大「最大token」(思考模型建议 ≥4096);"
                "② 打开「思考」开关保留思考输出,看看模型卡在哪;"
                "③ 换非 thinking 版本的模型(如 Qwen3.5 instruct 非 reasoning 量化)。")
    return (content or "").strip(), usage, latency


# ---------------------------------------------------------------------------
# 共享执行逻辑(两个节点类各自薄封装)
# ---------------------------------------------------------------------------

def run_enhance(handle, text, mode_display, subdir, system_preset,
                mode_instructions, node_label, tier_key=None,
                tier_texts=None, custom_preset=""):
    """工作节点的公共执行路径(模型/参数全部来自加载器句柄)。

    handle: PSModelHandle,由加载器节点输出。
    system_preset: 下拉选择的文件名(可带 fullscale/ 或 chinese/ 前缀)。
    tier_key: 'SFW'|'Suggestive'|'NSFW'|'Auto';Auto 或 None 都不追加覆盖段。
    tier_texts: {'SFW':..,'Suggestive':..,'NSFW':..} 节点面板上的自定义档位
                指令;某档为空时回退内置 TIER_OVERRIDE_EN。
    """
    if handle is None or not getattr(handle, "settings", None):
        raise RuntimeError(
            "未接收到模型句柄:请先添加「PromptScale LLM 模型加载器」, "
            "并把它的 ps模型 输出口连到本节点的 ps模型 输入口。")

    s = handle.settings
    model = s["model"]
    gguf_path = s.get("gguf_path", "")
    base_url = s.get("base_url", "")
    api_key = s.get("api_key", "")
    temperature = s.get("temperature", 0.8)
    max_tokens = s.get("max_tokens", 2048)
    timeout = s.get("timeout", 600)
    use_system_proxy = s.get("use_system_proxy", False)
    top_p = s.get("top_p", 1.0)
    top_k = s.get("top_k", 0)
    repeat_penalty = s.get("repeat_penalty", 1.0)
    min_p = s.get("min_p", 0.0)
    frequency_penalty = s.get("frequency_penalty", 0.0)
    presence_penalty = s.get("presence_penalty", 0.0)
    disable_thinking = s.get("disable_thinking", True)
    seed = s.get("seed", 0)
    n_ctx = s.get("n_ctx", 8192)
    n_gpu_layers = s.get("n_gpu_layers", -1)
    service = s.get("service", "本地")

    t0 = time.time()
    text = (text or "").strip()
    if not text:
        raise RuntimeError("输入为空:请给一行想法,或粘贴一段待升级的旧提示词。")

    mode_key = MODE_KEY.get(mode_display, "expand")

    # custom_preset 运行时优先级最高(免重载);其次下拉值;最后默认文件
    preset_ref = ((custom_preset or "").strip()
                  or (system_preset or "").strip()
                  or "")
    if not preset_ref:
        preset_ref = (DEFAULT_FULLSCALE if subdir == "fullscale"
                      else DEFAULT_CHINESE)
    loaded = load_system_prompt(preset_ref, subdir)
    master_body, master_path = loaded["body"], loaded["path"]

    system_parts = [master_body, mode_instructions[mode_key]]
    if tier_key and tier_key != "Auto":
        tier_text = ((tier_texts or {}).get(tier_key) or "").strip() \
            or TIER_OVERRIDE_EN.get(tier_key, "")
        if tier_text:
            system_parts.append(tier_text)
    system = "\n\n".join(system_parts)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]

    if gguf_path:
        content, usage, api_latency = chat_gguf(
            gguf_path, temperature, max_tokens, messages,
            top_p=top_p, top_k=top_k, repeat_penalty=repeat_penalty,
            seed=seed, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
            min_p=min_p, frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            disable_thinking=disable_thinking)
    else:
        content, usage, api_latency = chat_completion(
            base_url, api_key, model, temperature, max_tokens, messages,
            timeout, use_system_proxy=use_system_proxy,
            top_p=top_p, seed=seed,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            disable_thinking=disable_thinking)
    if not content:
        raise RuntimeError("模型返回了空内容(可能被 max_tokens 截断或模型拒绝输出)。")

    info = {
        "node": node_label,
        "service": service,
        "mode": mode_key,
        "tier": (tier_key if tier_key and tier_key != "Auto"
                 else "Auto → 由模型判定") if tier_key else "无档位",
        "model": model,
        "input_chars": len(text),
        "output_chars": len(content),
        "total_latency_s": round(time.time() - t0, 1),
        "api_latency_s": round(api_latency, 1),
        "usage": usage,
    }
    if gguf_path:
        info["gguf_path"] = gguf_path
        info["n_ctx"] = int(n_ctx)
        info["n_gpu_layers"] = int(n_gpu_layers)
    else:
        info["base_url"] = base_url
    sampling = {"top_p": float(top_p)}
    if int(top_k or 0) > 0:
        sampling["top_k"] = int(top_k)
    if float(repeat_penalty or 1.0) != 1.0:
        sampling["repeat_penalty"] = float(repeat_penalty)
    if float(min_p or 0.0) > 0.0:
        sampling["min_p"] = float(min_p)
    if float(frequency_penalty or 0.0) != 0.0:
        sampling["frequency_penalty"] = float(frequency_penalty)
    if float(presence_penalty or 0.0) != 0.0:
        sampling["presence_penalty"] = float(presence_penalty)
    sampling["thinking"] = "关闭(已剥离)" if disable_thinking else "保留原始输出"
    if int(seed or 0) != 0:
        sampling["seed"] = int(seed)
    info["sampling"] = sampling
    info.update(preset_info(master_path,
                            "custom_preset" if (custom_preset or "").strip()
                            else "system_preset 下拉"))
    info_json = json.dumps(info, ensure_ascii=False, indent=2)
    return (content, info_json)
