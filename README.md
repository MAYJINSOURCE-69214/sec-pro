# SEC Pro Beta · 0.2

**让一个人积累的开发经验，成为整个团队下一次工作的起点。**

SEC Pro 是面向 AI 软件开发团队的本地协作工具，尤其适合用 Codex 开发大型 Agent 和长期项目的团队。一个项目做完，有价值的排错方法、验收标准和协作经验，往往散落在聊天里；换一个人、开一个新任务，又要重新解释。SEC Pro 把这些经验整理成可按任务取用、审核分享和更新的团队资产，并将 GSD 开发流程与可配置的模型分工接在一起：负责人沉淀方法，员工在自己的电脑上使用和补充经验，主模型根据任务与证据协调 GPT、Kimi、千问等工人。它的目标是让团队少重复交代要求、少重复踩坑，也让“为什么派给这个模型、实际完成了什么”有据可查。你可以从随包经验开始，再逐步加入自己团队的方法、角色和公司 API。

GSD 安排开发步骤；SEC Pro 提供团队经验；当前主模型（例如 Astra）结合证据派活、审核结果。工人可以是 GPT，也可以是公司提供的 Kimi、千问或兼容 API，不固定哪家必须做哪类任务。

这是供团队试用的 Beta 版本。包内没有个人档案、原始聊天或密钥。真实公司 API、员工全新电脑的完整安装和页面交互仍需目标环境验收；程序测试通过不代表这些项目已经通过。

## 员工从这里开始

1. 打开 [Beta 下载页](https://github.com/fangzhengfelix9461/sec-pro/releases/tag/v0.2.0-beta.2)，下载 **SEC-Pro-Beta-0.2.0-beta.2.zip**。这是包含固定 GSD 依赖的安装包；无需另找仓库安装 GSD。
2. 将 ZIP 完整解压到一个以后不随便移动的目录，例如用户文档目录下的 `SEC-Pro`。不要直接在压缩包中运行脚本。
3. 在已登录的 Codex 中打开解压目录，把下一节的安装说明粘贴给 Codex。需要 Python 3.11+；完整安装还需要 Node.js 24+。缺少运行时时按下面的依赖安装方式处理。
4. 安装完成后，在该目录执行 `python launch.py`，或 Windows 双击 `start.cmd`。浏览器打开 `http://127.0.0.1:8765`。结束后可关闭启动窗口停止工作台。
5. 在“版本更新”填写 `fangzhengfelix9461/sec-pro`，选择 `beta`。确认信任后，可以启用自动更新。在“分工设置”填写公司分配的接口与型号；密钥只在本机环境变量中设置。没有公司 API 也可先查看经验和配置原生模型。

安装检查：执行 `python secpro.py doctor`；重新打开 Codex 会话，给它一个小开发任务，要求先检查相关团队经验和实际工人模型。`doctor`只检查配置，不会调用付费 API，也不能证明真实分工成功。

源码仓库：[fangzhengfelix9461/sec-pro](https://github.com/fangzhengfelix9461/sec-pro)。自动更新频道只在维护者发布并校验发行包后更新，不能把源码分支的新提交当作已安装版本。

## 交给 Codex 安装

将目录和下面这段话交给 Codex：

> 请读本目录 README，检查 Python 3.11+ 和 Node 24+，安装本目录中的 SEC Pro 与固定版 GSD。保留我原有模型、安全配置、个人经验与公司 API 设置。将经验同步的 official_repo 和 team_repo 配为 fangzhengfelix9461/sec-pro，合并到 ~/.sec-pro/settings.json，保留其他设置，首次安装保持 allow_upload:false。版本更新使用同一仓库和 beta 频道，只有我确认信任后才开启自动安装。第三方模型用公司给我的接口、模型 ID 和密钥环境变量，不猜型号或跑分；先告知缺什么，不擅自调用付费 API。完成后执行 doctor、启动工作台，并分别说明实际测试和未验证部分。

Windows：`python install.py`，或 `install.ps1`。明确允许安装缺失依赖时才用 `install.ps1 -InstallDeps`；它通过 winget 安装 Python / Node，不代登录账号。PowerShell 执行策略拦截时直接运行 Python。macOS/Linux 已有运行时可用 `sh install.sh`，本版未做这两类系统的实机安装验证。

手动安装的完整 Windows 顺序（先在终端进入解压后的目录）：

```powershell
python --version
node --version
python install.py
python secpro.py doctor
python launch.py
```

如果提示找不到 Python，请先安装 Python 3.11+ 并重新打开终端；如果只有 Node 版本不满足，安装 Node 24+ 后重试。仅体验页面、不安装 GSD 可直接使用下面的隔离预览。完整安装失败时先读错误提示，不把 `--skip-gsd` 当作已安装 GSD。启动端口被占用时可运行 `python launch.py --port 8766`，随后访问对应端口。

需要 Python 3.11+；完整 GSD 需要 Node.js 24+。随包固定 GSD Core 1.19.0 官方归档、SHA-512 与 MIT 许可证，不临时拉取不确定版本。第三方账号登录、公司凭据和模型权限由员工自己的账号提供，不会随包配置好。

安装写入：`~/.agents/skills/sec-pro-*`、`~/.codex/agents/sec-pro-*.toml`、`~/.codex/AGENTS.md` 中短托管块，以及 `~/.sec-pro`。完整 GSD 安装还写官方目录。已有受管理文件先备份，不删除无关文件。请保留最初解压目录，它也是初始回退版本。

安装后运行 `python launch.py`，Windows 可双击 `start.cmd`。启动器读取当前安装位置，升级后会启动新版。预览则双击 `start-preview.cmd`，或：

```powershell
python secpro.py serve --preview --port 8765 --data-dir .\preview-data
```

## 公司发布新版，员工怎么跟上

1. 维护者只制作可公开内容，执行 `python build_release.py --repository 公司/仓库`。只生成本地 ZIP、校验值和频道清单，不发布。
2. 经维护者授权后，将 ZIP 放到该 GitHub 仓库对应 `v版本号` 的 Release，把生成的 `dist/beta.json` 或 `stable.json` 放到仓库 `main` 分支的 `releases/` 目录。先测试发行包，再更新频道清单；同一版本不可悄悄换内容。
3. 员工在「版本更新」填同一个公司仓库、选择频道，确认信任，可启用自动更新。
4. 打开工作台或开始 Codex 开发任务时检查更新，默认24小时内复用结果。只有有新版、已信任、已启用自动安装且本机没有未结束工单时才安装。不会在员工改代码中途强行切换。
5. 下载包校验 SHA-256、检查解压路径与包内版本；存到个人数据目录的 `releases/版本号`，再更新受管理的入口与技能。个人经验、API环境变量、自定义角色、workers.json和其他个人配置保留。不会把员工的配置上传给公司。
6. 安装失败尝试恢复上一版，失败状态明确报告；也可点「回退上一版」。更新后重启工作台，并在 Codex 新会话使用新版。旧版本目录保留，个人数据不随回退倒退。

自动更新是按使用触发，不是电脑关机时仍然推送，也不安装后台常驻服务。首次信任仓库意味着允许安装该维护者发布的程序；校验值检查完整性，不是独立数字签名。需要新Python/Node或升级上游GSD时转为Codex辅助完整安装，不强行在后台修改运行环境。预览模式不执行安装/回退。

```powershell
python secpro.py update --action check
python secpro.py update --action auto
python secpro.py update --action apply --confirm
python secpro.py update --action rollback --confirm
```

以上命令默认使用 `~/.sec-pro`，隔离目录须统一加 `--data-dir 路径`。初始0.1包没有更新入口，首次升至本版需重新安装一次。若更新进程被强制结束，核实它确已停止后，用 `update --action recover --confirm` 清除遗留占位，再核对版本或执行回退；清除标记本身不会结束进程，也不代表安装完整。

## 自定义模型和角色，GPT与第三方怎么共同工作

「分工设置」的「配置公司 API / 自定义角色」可以编辑并保存配置，也可以让 Codex 代填。配置文件是个人数据目录的 `workers.json`：

- `providers`：接口类型、是否启用、HTTPS地址、密钥的**环境变量名**。目前支持Codex原生工人与OpenAI兼容Chat Completions API。Kimi、千问模板默认关闭，必须填公司实际模型ID；地区和公司网关不同，接口地址按公司提供的填写。
- `models`：精确模型ID、供应商、能力、思考强度、输出上限、价格。`price:null`表示未知，不代表免费。第三方思考参数放在该模型支持的`parameters`中，不把GPT参数强塞给所有接口。
- `roles`：任意自定义角色，例如阅读、编码、测试、审查；每个角色有能力要求与工作说明，不绑定某个品牌。
- `max_parallel`：**GPT和第三方合计**的并发名额，默认2，可设1至8。所有入口要使用同一数据目录。
- `evidence`：有出处的公开评测或公司实测，初始为空。每条包括 `id, model_key, model_id, capability, benchmark, harness, date, score, source, kind`；kind为published/local。score须归一化到0至1、越高越好，并在source说明原始分数和转换依据。当前候选采用90天内证据，过期需复核。

密钥由公司交付员工，在本机设置对应环境变量后重启服务/终端；这里不提供密钥输入框，不把密钥写入GitHub或经验库。新增模型的配置不等于已验证账号可用。

Astra/当前主模型拿到任务后：先看任务需要什么，再看精确模型版本、同一种测试和运行条件、公司实际通过情况、同币种价格与可用性，最后记录为什么选它。不同跑分榜不直接混排，没有资料就注明未知。没有可靠证据时只能明确做小规模试评；不能仅凭品牌名或虚构分数声称千问优于Sol，也不会自动另起Astra API来判断。

例如“给上传功能补测试”：主模型可把代码定位交给一个阅读工人，把测试方案交给公司API工人；两个工人共用两个名额。前者负责读指定文件，后者输出测试代码建议，主模型应用和执行测试。如果它们都要修改同一个文件，第二个工单不会同时领取成功。

## Codex实际派活的入口

先取候选资料：

```powershell
python secpro.py worker-candidates --role coder
```

主模型在被Git忽略的 .local-work 目录写一份小工单JSON，避免将业务上下文误提交：

```json
{
  "task_key":"project-a/upload-test-001",
  "role":"coder",
  "model_key":"company-qwen",
  "task":"此处仅放允许发给该供应商的具体任务与必要代码",
  "reason":"这里填写任务匹配、真实选型依据、预计代价与验收方式",
  "evidence_ids":[],
  "evaluation":true,
  "resources":[]
}
```

这是待填写示例，空证据+evaluation:true表示试评，不是已验证的正式最佳模型。resources填工人可能修改的文件/目录绝对路径，用于防止同时写入。正式有依据的调用使用有效evidence_ids。

```powershell
python secpro.py worker-reserve --file .local-work/order.json
```

系统先在共用账本占位，拒绝重复工单、写同一文件和超过并发总额：

- 返回codex：Codex实际调用原生子代理工具，使用返回的明确模型与强度。结束后用 `worker-finish --job 编号 --status completed --note 实际产物与验收 --confirm-stopped` 释放名额。
- 返回chat-completions：确认任务内容可以给该供应商后，执行 `worker-run --job 编号 --allow-api`。独立调用可以在同一名额限制内并行，返回产物写入本机runs目录，由Codex审核、应用修改和测试。

API工人当前是一次有界的文本/代码产物调用，没有本机Shell、文件系统或自主工具循环，不等于完整的Kimi Code/千问Agent。不会执行它返回的命令。试评输出最多2048 tokens；普通输出按配置上限。失败/超时不自动重试或切最贵模型；结果不明保留占位，核查后明确结束。释放占位不会终止真实模型进程。

GSD继续管理计划与进度，不另造一套开发调度。通过此入口的工人才受共用名额管理；绕过入口直接启动的其他程序无法强制拦截，也没有公司所有电脑的统一限流或累计Token硬熔断。原生模型的账单与第三方API的reported usage不是统一费用口径，不能虚报节省比例。

0.1的`models.json`、GSD代理TOML作为兼容启动配置保留；初次安装会保留不同的旧模型选择。0.2每次动态分工读取workers.json；旧`worker-request`只返回不可直接派发的草稿。GSD已有显式冲突继续保留，不能静默覆盖用户选择。原生工具若无法传入所选模型/强度，不得假装分流成功。

## 经验同步和贡献

随包有11条抽象开发经验、1个可加装的交付检查技能。个人记录先留本机候选，不自动成为团队规则。

「同步下载经验」读取维护者的`library/catalog.json`；「同步团队经验」读取`library/team.json`。在数据目录settings.json配置official_repo/team_repo，格式owner/repo。预览模式只读本地演示目录。

「上传自己的经验」支持选择1至30条个人经验或技能，一次查看每条全文与检查结果；本人复核确认后生成一个本地批量提案。内容在预览后变化时必须重新检查；单条旧提案仍可使用。生成后可在网页明确确认目标公开仓库和内容，再点击提交到 GitHub 审核；相同内容已有提案时直接显示已有请求，避免重复。本次确认只授权该次提交，不打开持久上传开关。上传使用已登录的 GitHub CLI 或 Git Credential Manager；命令行 `github-propose 提案编号 --confirm-public` 仍要求 settings.json 中 allow_upload:true。批量提案只提交一个贡献文件和一个审核请求。维护者需核对后把条目加入team.json并设active；只合并贡献文件不会自动推广。当前只支持公开仓库读取，真实远程验收依GitHub登录和权限另核。

技能目前只支持单文件Markdown指令，阅读后确认启用。带脚本和依赖的多文件技能包不在当前范围。程序更新和经验目录同步是两个入口，不能用“同步经验”冒充程序已升级。

## 验证、恢复与边界

```powershell
python install.py --codex-home .\sandbox\codex --skills-home .\sandbox\skills --data-dir .\sandbox\data --skip-gsd
python -m unittest discover -s tests -v
python secpro.py doctor --data-dir .\sandbox\data
```

自定义安装目录必须--skip-gsd，避免上游全局安装器触及真实用户目录。测试覆盖配置、共用并发、重试/冲突、升级/回退和保留个人配置，模型HTTP与GitHub下载使用模拟，不是公司API或真实远程验收。GSD固定包转换函数已单独验证；员工新电脑完整安装、账号模型支持、视觉交互仍需目标环境验收。

移除AGENTS中的SEC_PRO_BETA托管块可关闭自动任务入口。更新前的托管文件有.secpro-backup备份；不删除员工个人数据。许可证和参考来源见THIRD_PARTY_NOTICES.md及vendor/GSD-LICENSE。
