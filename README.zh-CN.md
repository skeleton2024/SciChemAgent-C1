# SciChemAgent-C1

SciChemAgent-C1 是面向
[SciAgentArena](https://sciagentarena.github.io/) 药物发现基准 C1（化学数据预处理）
18 项任务的确定性离线 Agent。评测时只使用 RDKit 和公开任务输入，不调用托管 LLM、
外部 API 或网络服务。

本仓库是社区提交候选；在维护者复现并接收前，结果不是官方排行榜成绩。

## 已核验结果

固定上游提交 `c413f660304bf5def1c54a23619267e3ee2ef6ad`，评测日期
2026-08-04：

- 任务覆盖：18/18
- Executability 均值：1.0000
- Validity 均值：1.0000
- Correctness 未加权算术平均：`0.9244444444`，即 **92.4444%**
- 满分任务：15/18

详细汇总见 `results/c1/summary.json` 和 `results/c1/summary.csv`。运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_c1.py
.\.venv\Scripts\python.exe scripts\verify_results.py
```

完整环境安装和固定版本复现命令见 [英文 README](README.md#reproduce)。

## 科学一致性说明

`tech_07_hard_aceticacid` 要求 pH 7.4 的主导形式电荷。取乙酸
`pKa ≈ 4.76`，乙酸根/乙酸比例为 `10^(7.40-4.76) ≈ 437`，乙酸根比例约
`99.77%`，因此主导整数形式电荷应为 `-1`。固定上游 scorer 的真值为 `0`。
本 Agent 保留科学上正确的 `-1`，没有为分数硬编码冲突答案。

## 隐私与边界

公开仓库不包含虚拟环境、官方数据克隆、内部运行状态、API 密钥、逐题绝对路径记录
或日志。Agent 也不导入 scorer 或 ground-truth 文件。
