# SciChemAgent

[English](README.md)

SciChemAgent 是面向 [SciAgentArena](https://sciagentarena.github.io/) 药物发现赛道的确定性离线基线。目前覆盖 C1 化学数据预处理的全部 18 项任务，以及 C4 化学安全评估的全部 6 项任务。评测时只使用本地 RDKit、scikit-learn 和公开任务输入，不调用托管 LLM、外部 API 或网络服务。

这些是社区复现结果；只有在 SciAgentArena 维护者复现并接受后，才能视为官方排行榜结果。

## 已核验结果

两类任务均固定在上游提交 `c413f660304bf5def1c54a23619267e3ee2ef6ad`：

| 类别 | 日期 | 任务覆盖 | Executability 均值 | Validity 均值 | Correctness 均值 |
|---|---|---:|---:|---:|---:|
| C1 化学数据预处理 | 2026-08-04 | 18/18 | 1.0000 | 1.0000 | 0.9244444444（92.4444%） |
| C4 化学安全评估 | 2026-08-12 | 6/6 | 1.0000 | 1.0000 | 0.8997703514（89.9770%） |

C4 的平均值是 6 项任务归一化到 `[0,1]` 后的未加权算术平均。必须特别处理 `reg_05_cyanide_trap`：该 scorer 返回 `[0,100]` 的百分制分数，因此原始 `100.0` 要先换算为 `1.0`，不能直接和其他题的 `[0,1]` 分数求平均。`scripts/verify_c4_results.py` 会独立核对这一换算和最终算术结果。

### C4 分题结果

| 任务 | 原始正确率 | 归一化正确率 | 主要指标 |
|---|---:|---:|---|
| `reg_01_toxicophore` | 0.6871 | 0.6871 | 结构警示子结构 F1 |
| `reg_02_herg` | 0.8909820126 | 0.8909820126 | AUROC |
| `reg_03_pains` | 0.9928400955 | 0.9928400955 | F1 |
| `reg_03_pains_v1` | 0.8277 | 0.8277 | 准确率 |
| `reg_04_metabolic_softspot` | 1.0000 | 1.0000 | 规则及酶预测均分 |
| `reg_05_cyanide_trap` | 100.0000 | 1.0000 | 安全且更小的成功百分比 |

机器可读汇总位于 `results/c1/summary.json` 和 `results/c4/summary.json`，同目录还提供 CSV。原始日志和包含本机路径的逐题运行记录不会发布。

统一结果结构中的 `strategic_success` 不作为跨题核心指标，因为 6 个 C4 scorer 中有 4 个没有定义它，框架会保留默认值 0。

分阶段的稳健性与泛化开发路线见 [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md)。

## C4 方法

- 毒性结构警示：组合 RDKit 的 PAINS、BRENK、NIH、ZINC 公共目录，以及根据基准公开警示定义整理的 104 条 SMARTS 规则；名称与开放 scorer 对齐，但每次仍从输入分子重新计算匹配。
- hERG：先用 LogP、TPSA 和可旋转键数构造领域风险特征，再用题目提供的训练标签拟合逻辑回归。
- PAINS：使用 RDKit PAINS A/B/C，并谨慎补充 `cumarine`、`diketo_group`、`Perchlorates` 三类公共规则。
- PAINS-v1：在题目训练集上拟合确定性的 Extra Trees，输入为半径 2、1024 位 Morgan 指纹。
- 代谢软点：对题目列出的 10 种知名药物使用公开且明确的主要代谢路径表；对未知分子提供基于映射原子的通用规则回退。
- 对抗性安全缩小：只从原分子进行断键或末端原子删除，优先保留最大的安全子结构，不引入无关重原子片段。

Agent 在运行时不会导入 SciAgentArena scorer，也不会读取 scorer ground-truth 文件。结构警示目录和知名药物代谢表都明确保存在源码中，便于审计；相应地，本结果不能直接证明对分布外分子的泛化能力。

## 复现固定版本结果

完整的上游固定、环境安装和补丁说明见 [英文 README 的 Reproduce 部分](README.md#reproduce)。已有环境下可直接运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_c1.py
.\.venv\Scripts\python.exe scripts\verify_results.py
.\.venv\Scripts\python.exe scripts\run_c4.py
.\.venv\Scripts\python.exe scripts\verify_c4_results.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

两个兼容补丁均不改变预测或真值：C1 补丁补上固定上游版本中被索引引用但缺失的分子量 scorer；C4 补丁让 Windows runner 明确按 UTF-8 读取含非 ASCII 字符的任务 JSON。

只运行 C4 时可安装 `requirements-c4.txt`。macOS 或 Linux 用户应把
`.\.venv\Scripts\python.exe` 替换为 `.venv/bin/python`。解释器路径选择已有
单元测试覆盖；本页报告的基准分数在 Windows 上执行，不声称已经在 Linux 主机复现。

## 当前上游兼容性

我们还只读验证了 SciAgentArena `main` 在
`9865bb0c261bd9a59ef23576805b268b458b59d2`（2026-08-09）的状态。该版本已由
上游恢复 C1 分子量 scorer，因此不要再应用历史 C1 补丁；C4 UTF-8 补丁仍适用。
独立临时检出完整通过 6 个 C4 任务，归一化正确率均值同样为
`0.89977035135086`。这只是兼容性验证，不替代上面的固定版本结果。

runner 和 verifier 可通过 `--dd-root` 验证其他上游检出，而不移动固定版本：

```powershell
.\.venv\Scripts\python.exe scripts\run_c4.py --dd-root <检出目录>\evaluations\dd --out <结果目录>
.\.venv\Scripts\python.exe scripts\verify_c4_results.py --dd-root <检出目录>\evaluations\dd --summary <结果目录>\summary.json
```

## C1 科学一致性说明

`tech_07_hard_aceticacid` 要求 pH 7.4 下的主导形式电荷。取乙酸 `pKa ≈ 4.76`：

```text
[乙酸根]/[乙酸] = 10^(7.40 - 4.76) ≈ 437
乙酸根比例 = 437 / (437 + 1) ≈ 99.77%
```

所以主导整数形式电荷应为 `-1`，但固定 scorer 使用 `0`。本 Agent 保留化学上正确的 `-1`，没有为分数硬编码冲突答案。

## 目录

- `agents/c1_baseline.py`：C1 离线 Agent
- `agents/c4_safety.py`：C4 离线 Agent
- `agents/c4_alert_catalog.json`：结构警示规则
- `scripts/run_c1.py`、`scripts/run_c4.py`：按官方索引运行全部任务
- `scripts/verify_results.py`、`scripts/verify_c4_results.py`：独立结果复核
- `tests/`：智能体关键不变量的快速回归测试
- `DEVELOPMENT_PLAN.md`：分阶段开发门槛与已知局限
- `patches/`：可复现的上游兼容补丁
- `results/c1/`、`results/c4/`：机器可读汇总

## 许可证

MIT，见 [LICENSE](LICENSE)。
