# Third-party components

- GSD Core 1.19.0, by Open GSD. Official unmodified npm archive is bundled in `vendor/`; MIT copyright and license are in `vendor/GSD-LICENSE`. Package integrity and upstream location are recorded in `vendor/gsd-lock.json`. SEC Pro is an independent integration, not an official Open GSD or OpenAI product.
- The local preview uses original HTML/CSS/JavaScript. Its workspace layout was informed by the public shadcn/ui sidebar and theming documentation; it does not bundle shadcn code or require React.

References checked for this beta:
- https://github.com/open-gsd/gsd-core/releases/tag/v1.19.0
- https://learn.chatgpt.com/docs/build-skills
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://ui.shadcn.com/docs/components/radix/sidebar

Model defaults are configurable examples based on the configured environment. Account availability and relative cost must be verified for the installing account; no fixed savings are promised.

Beta 0.2 provider integration references (2026-10-27):
- https://platform.kimi.com/docs/api/chat — Kimi HTTPS Chat Completions interface.
- https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions — Qwen compatible interface; company workspace/region endpoints can differ.
- https://learn.chatgpt.com/docs/agent-configuration/subagents — a custom native agent's model_provider does not override its parent session. Third-party workers therefore use a separate bounded HTTP adapter, not a fabricated native provider override.

No benchmark scores or prices were copied or invented. Supply exact company model IDs and sourced evaluation records before evidence-based selection. All provider calls in development tests were mocked, not real billed calls.
