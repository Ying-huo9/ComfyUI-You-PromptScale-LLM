# ComfyUI-PromptScale-LLM

LLM 提示词扩写/升级节点(**双加载器 + 单扩写器**架构)。
把一行想法扩写成完整人像摄影提示词,或把旧提示词整体升级改写。

- **本地GGUF 加载器**:llama.cpp 进程内推理(与 llama-TE 同款),
  直读 `models/LLM/`,不用起任何服务;
- **API 加载器**:OpenAI 兼容接口,本地服务(Ollama / LM Studio / vLLM)
  或云端 API(DeepSeek / 硅基流动 / 通义 / Kimi / 智谱 / OpenAI / 自定义)。

两个加载器输出**同一种 `ps模型` 句柄**,下游工作节点和连线完全通用,
随时换加载器不用重搭工作流。零第三方依赖(GGUF 后端复用 ComfyUI 环境
里已装的 llama-cpp-python)。适配 ComfyUI 0.34.0。

## 三个节点

```
┌─ PromptScale 本地GGUF 加载器 ─┐   ┌─ PromptScale API 加载器 ─┐
│ 模型/温度/top_p/top_k/重复惩罚 │   │ 服务来源/地址/密钥/模型     │
│ /seed/上下文长度/GPU层数       │   │ /温度/top_p/seed/超时/代理 │
└──────────────┬───────────────┘   └────────────┬─────────────┘
               │          都输出 ps模型 句柄      │
               ╞════════════════╤═══════════════╡
               └─ PromptScale 扩写器 ─┘
                 想法文本/输出模式/尺度档位
                 master预设(中英文全列)/master覆盖
                 → prompt + info
```

| 节点 | 职责 |
|---|---|
| **PromptScale 本地GGUF 加载器** | 扫 `models/LLM` 出模型下拉;温度/最大token/**top_p/top_k/重复惩罚/seed**/**上下文长度(n_ctx)/GPU层数**全在这;进程内推理,不用起服务 |
| **PromptScale API 加载器** | 选服务(本地HTTP/DeepSeek/硅基流动/通义/Kimi/智谱/OpenAI/自定义);「模型」下拉从 `GET /models` 实时读取;温度/最大token/**top_p/seed**/超时/代理 |
| **PromptScale 扩写器** | 接 `ps模型` 连线。**master 中英文任选——输出语言随 master 走**,不再分节点;尺度档位 SFW/Suggestive/NSFW/Auto **对任意 master 生效** |

两个加载器面板上**只有自己后端有意义的字段**——本地版没有地址/密钥,
API 版没有 GPU 层数。换模型、换供应商、本地↔API 互换,只动加载器,
下游一根线都不用动。

### 扩写器要点

- **master预设**:合并列出 `prompts/fullscale/`(英文)与 `prompts/chinese/`(中文)
  下全部文件,带目录前缀。选中文 master → 输出中文提示词;选英文 → 英文。
  中英文之间切换 = 换一个下拉选项,节点不用换。
- **尺度档位(任意 master 通用)**:
  - `SFW / Suggestive / NSFW` = 硬覆盖:在 master 之后追加**最高优先级**
    指令段,无视输入词与 master 默认强制该尺度;
  - `Auto` = 不追加任何覆盖段,由 master 按输入词自判(默认保守)。
- **三档指令可自定义**:`SFW指令 / Suggestive指令 / NSFW指令` 三个 widget
  在节点上隐藏,两种编辑入口(值同步,存进工作流 JSON):
  - 右键节点 → **Properties 属性面板**,对应条目直接改(单行);
  - 右键节点 → **「编辑档位指令」**,弹出多行大编辑框。
  - **留空 = 回退插件内置指令**(内置文本即 widget 默认值)。
- **master覆盖**:支持 `fullscale/xxx`、`chinese/xxx`、纯文件名(两目录都找)
  或任意完整路径,运行时解析、免刷新。
- 模式指令(expand/upgrade)语言自动跟随 master 目录:中文 master 配中文指令。

### 加载器参数说明

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

## 输出

- `prompt`:模型输出的完整提示词(STRING)
- `info`:本次执行的元信息 JSON(服务、模型、档位、采样参数、预设路径、耗时、usage 等)

## 示例工作流

三个完整文生图工作流(已同时复制到 `ComfyUI/user/default/workflows/`,
在 ComfyUI 侧栏工作流菜单里也能直接打开):

- `examples/example_workflow_fullscale_txt2img.json` —— **英文输出 · 本地GGUF**
  (默认 Qwen3.5-4B-Q4_K_M.gguf,英文 master)
- `examples/example_workflow_chinese_txt2img.json` —— **中文输出 · 本地GGUF**
  (同一节点,选了 chinese/ 目录 master)
- `examples/example_workflow_fullscale_api_txt2img.json` —— **英文输出 · API**
  (默认 DeepSeek,填 Key 按 R 刷新即可)

加载后只需:换掉 Checkpoint 模型文件名 → Queue。

## master 文件放置规则(随便命名,不需要任何前缀/frontmatter)

```
prompts/
├── fullscale/            ← 英文 master 丢这里(下拉显示 fullscale/xxx)
│   ├── English_Master_v2.md
│   └── LLM-Prompt-Expert-English.md   (v1)
└── chinese/              ← 中文 master 丢这里(下拉显示 chinese/xxx)
    └── Chinese_Master_Refined.md
```

- 文件名随意,合并下拉按修改时间倒序(新炼的排最前)。
- **不需要** frontmatter / `scale:` / `lang:` 头 —— 行为由"选的 master +
  档位"决定。就算文件带了 `--- ... ---` 头也会被自动剥离。
- 下拉列表只在节点/工作流加载时生成一次。中途新丢的文件不会自动出现:
  在 **master覆盖** 里填 `目录名/文件名` 即可立即使用(运行时解析,免重载),
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
- 节点合并历史:旧 `PSFullScale`(全尺度三档)与 `PSChinese`(中文扩写)
  已合并为 `PSEnhancer`(扩写器)并移除——旧工作流把工作节点换成
  「PromptScale 扩写器」重连一根线即可(加载器不用动);原中文节点行为
  = 扩写器选中文 master + Auto 档。更早的 `PSLLMLoader`/`Luori*` 亦已移除。
