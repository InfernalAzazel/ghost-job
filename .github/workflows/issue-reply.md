---
on:
  issues:
    types: [opened]
  roles: all
permissions:
  contents: read
  issues: read
imports:
  - pydantic/pydantic-ai/src/pydantic_ai_harness/gh-aw/pydantic.md@main
engine:
  id: pydantic-ai
  model: openai/deepseek-flash
  env:
    PAI_AGENT: issue_reply_agent:agent
    # proxy 持有 key，上游从默认的 api.openai.com 换成 DeepSeek。
    OPENAI_API_TARGET: api.deepseek.com
network:
  allowed:
    - api.deepseek.com
safe-outputs:
  add-comment:
  close-issue:
  threat-detection: false
---

# 回复新 issue

<issue>
${{ steps.sanitized.outputs.text }}
</issue>

按 issue_reply_agent.py 里的规则处理。
