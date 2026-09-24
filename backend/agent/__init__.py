"""backend/agent：自研 agent 封装层（D6.1）。

本包内部允许 import deepagents/langgraph；业务代码只允许经由本包的自研接口，
保留框架可替换性、隔离上游 v0.x 破坏性变更。
"""
