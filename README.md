# ComfyUI-PromptScale-LLM

LLM 提示词扩写/升级节点(**双加载器 + 双工作节点**架构)。
把一行想法扩写成完整人像摄影提示词,或把旧提示词整体升级改写。

- **本地GGUF 加载器**:llama.cpp 进程内推理(与 llama-TE 同款),
  直读 `models/LLM/`,不用起任何服务;
- **API 加载器**:OpenAI 兼容接口,本地服务(Ollama / LM Studio / vLLM)
  或云端 API(DeepSeek / 硅基流动 / 通义 / Kimi / 智谱 / OpenAI / 自定义)。

两个加载器输出**同一种 `ps模型` 句柄**,下游工作节点和连线完全通用,
随时换加载器不用重搭工作流。零第三方依赖(GGUF 后端复用 ComfyUI 环境
里已装的 llama-cpp-python)。适配 ComfyUI 0.34.0。

## 四个节点

```
┌─ PromptScale 本地GGUF 加载器 ─┐   ┌─ PromptScale API 加载器 ─┐
│ 模型/温度/top_p/top_k/重复惩罚 │   │ 服务来源/地址/密钥/模型     │
│ /seed/上下文长度/GPU层数       │   │ /温度/top_p/seed/超时/代理 │
└──────────────┬───────────────┘   └────────────┬─────────────┘
               │        都输出 ps模型 句柄        │
               ╞════════════════╤═══════════════╡
     ┌─ PromptScale 全尺度三档 ─┐  └─ PromptScale 中文扩写 ─┘
     │ 想法文本/输出模式/尺度档位  │    (无档位,自带尺度)
     │ → prompt + info          │
     └─────────────────────────┘
```

| 节点 | 职责 |
|---|---|
| **PromptScale 本地GGUF 加载器** | 扫 `models/LLM` 出模型下拉;温度/最大token/**top_p/top_k/重复惩罚/seed**/**上下文长度(n_ctx)/GPU层数**全在这;进程内推理,不用起服务 |
| **PromptScale API 加载器** | 选服务(本地HTTP/DeepSeek/硅基流动/通义/Kimi/智谱/OpenAI/自定义);「模型」下拉从 `GET /models` 实时读取;温度/最大token/**top_p/seed**/超时/代理 |
| **PromptScale 全尺度三档** | 接 `ps模型` 连线。选 SFW/Suggestive/NSFW 时在 master 后追加最高优先级英文覆盖指令硬锁尺度;Auto 不追加,由 master 按输入判定 |
| **PromptScale 中文扩写** | 接 `ps模型` 连线。中文 master 自带尺度逻辑(默认 SFW、点名 NSFW 才升级),无档位开关 |

两个加载器面板上**只有自己后端有意义的字段**——本地版没有地址/密钥,
API 版没有 GPU 层数。换模型、换供应商、本地↔API 互换,只动加载器,
下游一根线都不用动。

### 参数说明

- **采样参数(两个加载器都有)**:温度 / top_p / seed 是 OpenAI 标准字段,
  GGUF 与 API 行为一致。seed=0 表示每次随机;填非 0 固定种子可复现。
- **GGUF 专属**:
  - `top_k`(0=关闭)、`重复惩罚`(1.0=不惩罚):llama.cpp 采样参数,
    API 端无此概念;
  - `上下文长度`(n_ctx,默认 8192):本节点任务输出较短,8192 足够;
    改动后首次执行会重载模型(缓存键 = 模型 + n_ctx + GPU层数);
  - `GPU层数`(-1=全部上 GPU,0=纯 CPU):显存不够时降级用。
- **API 专属**:超时秒、代理(直连/走系统代理)。
- **模型覆盖**(两个都有):下拉过期时手填模型名,免按 R 刷新。

### 加载器要点

- **模型下拉实时读取(API 加载器,双通道)**:先走 OpenAI 兼容
  `GET /models`,失败时自动转 **Ollama 原生 `/api/tags`**(自动剥掉
  /v1 后缀);智谱 GLM 没有公开列表接口,内置模型清单兜底。本地服务
  启动(或云端填好 Key)后,在 ComfyUI 里按 **R(刷新)** 重新拉取。
- **连接地址智能解析**:粘贴完整 `/chat/completions` 端点会自动剥掉后缀;
  以 `#` 结尾则强制原样使用;本地地址(127.0.0.1/localhost/:11434)不带
  `/v1` 时自动走 **Ollama 原生 `/api/chat`**(用完即卸载,不常驻显存);
  带 `/v1` 走 OpenAI 兼容。LM Studio / vLLM 请使用带 `/v1` 的地址。
- **API密钥自动清洗**:复制粘贴带引号/省略号(…/...)/空格换行都能识别,
  不会因此 401;真正 401 时会明确提示"API Key 无效"。
- 服务来源选「自定义 OpenAI 兼容」时连接地址必填;本地服务密钥留空即可。

## 输出(两个工作节点相同)

- `prompt`:模型输出的完整提示词(STRING)
- `info`:本次执行的元信息 JSON(服务、模型、档位、采样参数、预设路径、耗时、usage 等)

## 示例工作流

三个完整文生图工作流(已同时复制到 `ComfyUI/user/default/workflows/`,
在 ComfyUI 侧栏工作流菜单里也能直接打开):

- `examples/example_workflow_fullscale_txt2img.json` —— **全尺度三档 · 本地GGUF**
  (默认 Qwen3.5-4B-Q4_K_M.gguf)
- `examples/example_workflow_chinese_txt2img.json` —— **中文扩写 · 本地GGUF**
- `examples/example_workflow_fullscale_api_txt2img.json` —— **全尺度三档 · API**
  (默认 DeepSeek,填 Key 按 R 刷新即可)

加载后只需:换掉 Checkpoint 模型文件名 → Queue。

## master 文件放置规则(随便命名,不需要任何前缀/frontmatter)

```
prompts/
├── fullscale/            ← 英文全尺度 master 丢这里(全尺度节点下拉)
│   ├── English_Master_v2.md
│   └── LLM-Prompt-Expert-English.md   (v1)
└── chinese/              ← 中文 master 丢这里(中文节点下拉)
    └── Chinese_Master_Refined.md
```

- 文件名随意,下拉按修改时间倒序(新炼的排最前)。
- **不需要** frontmatter / `scale:` / `lang:` 头 —— 节点类型本身就决定了
  行为。就算文件带了 `--- ... ---` 头也会被自动剥离,不影响使用。
- 下拉列表只在节点/工作流加载时生成一次。中途新丢的文件不会自动出现:
  在 **master覆盖** 里填文件名即可立即使用(运行时解析,免重载),
  或重开工作流/重启 ComfyUI。

## 安装

把整个 `ComfyUI-PromptScale-LLM` 文件夹放进
`ComfyUI/custom_nodes/`,重启 ComfyUI,在 `PromptScale/LLM增强` 分类下找节点。

## 注意

- 节点为同步阻塞式:LLM 跑多久转多久。GGUF 后端首次执行要先加载模型
  到 GPU(4B 约几秒,27B 视显存而定);同模型同加载参数不重复加载。
- 本地 Qwen3 自带安全对齐,云端 API(DeepSeek/通义/智谱等)还有平台侧内容
  审查,NSFW 档可能被模型或平台压回/拒绝,这是服务侧行为,节点无法干预。
- API 密钥存在工作流 JSON 的加载器节点里,分享工作流前注意脱敏。
- 旧单加载器版(`PSLLMLoader`)与更早的四节点版(`LuoriFullScaleLLM` 等)
  均已移除:旧工作流只需删掉旧加载器、拖一个新加载器重连一根线,
  下游工作节点原样保留。
