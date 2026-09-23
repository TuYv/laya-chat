# 训练数据流水线

目标：给 `laya_chat/questions_send.py` 里的两套题目（好感度 3 题、发送后果 6 题）造带概率的标签，微调 Laya。
运行时不用大模型；大模型只在这里当老师，默认用本机的 `claude -p`（`--tool codex` 可换）。

## 一键跑

```bash
.venv/bin/python data/import_lccc.py --n-tension 200 --n-random 100   # 公开数据集 LCCC 里挑 300 段（只需一次）
zsh data/run_all.sh                                                   # 其余全部，日志 data/run.log
```

`run_all.sh` 依次做：合成 100 段有张力的对话 → 每段 4 条草稿 → 好感度标签 → 发送后果标签 → 合并切分。
老师默认全部用 `claude -p --model sonnet`，每次 16 条。每一步可重复运行，已处理的 id 会跳过，中断了重跑同一条命令即可。
`USE_CODEX=1 zsh data/run_all.sh` 让 codex 分担一半；实测本机 codex 走的自定义服务商很慢，默认关。

## 分步命令

```bash
P=.venv/bin/python
$P data/gen_conversations.py --n 100 --seed 1 --focus --model sonnet   # 种子 → 对话  data/raw/conversations.jsonl
$P data/gen_drafts.py --model sonnet --per-call 6                      # 每段 4 条草稿  data/raw/drafts.jsonl
$P data/label.py --what affinity --model sonnet --per-call 16          # 好感度标签    data/labeled/affinity.jsonl
$P data/label.py --what send --model sonnet --per-call 16              # 发送后果标签  data/labeled/send.jsonl
$P data/build_dataset.py                                               # 合并切分      data/dataset/{train,dev,test}.jsonl
$P data/agreement.py --what send --n 24                                # 老师自一致性（可选）
$P eval/run_eval_send.py --split dev                                   # 微调前基线
```

所有生成 / 打标脚本都有 `--tool`、`--model`、`--per-call`、`--workers`、`--shard i/n`、`--limit N`。

## 对话从哪来

- **LCCC**（清华，微博对话，`silver/lccc`）：`import_lccc.py` 流式读 370 MB 训练集，筛 7 到 14 轮、每轮 2 到 60 字、不含 @ 和网址的；前 T-2 轮做对话，第 T-1 轮是我实际发的下一句（`real_next`，直接当一条草稿），第 T 轮是对方实际回复（`real_reply`，先存着）。张力关键词命中的优先。关键词里"冷""烦"这种太宽，会把"今天好冷"也算进来，只影响抽样比例，不影响标签。
- **合成**：`gen_conversations.py --focus` 只用有张力的情境（试探、道歉后、催促、冷战、最后通牒……），补 LCCC 缺的那部分。
- **草稿**：LCCC 段 = 真实下一句 + 1 条合成的还行的 + 2 条坏写法；合成段 = 2 条还行的 + 2 条坏写法。坏写法从 5 种里按 id 随机挑。

## 输出格式

`data/dataset/*.jsonl` 每行：`case_id`、`conv_id`、`kind`（affinity / send）、`state`、`questions`、`gold`。
后三个是 JSON 字符串，和 Laya 微调笔记本读的 `LocalLLaMA/typed-decisions` 字段一样：
`gold[题号]["probabilities"]` 是老师给的每个选项的概率，score 题的键是等级序号 `"0"`、`"1"`…

切分按对话 id 做，同一段对话的 5 条草稿在同一个集合里。

## 实测耗时（claude -p，每次调用带约 2 万 token 的固定上下文）

| 步骤 | 一次调用 | 单次产出 |
|---|---|---|
| 生成对话 | 约 50 秒 | 3 段 |
| 生成草稿 | 约 40 秒 | 3 段 × 5 条 |
| 好感度标签 | 约 45 秒 | 6 段 |
| 发送后果标签 | 约 60 秒 | 6 条草稿 |

## 已知的偏差

- 草稿按 5 种类型生成，其中 4 种是"不好的写法"，比真实使用里的比例高。扩大规模前应调整 `gen_drafts.py` 的类型配比，加入更多"合适但平淡"的草稿。
- 语气题的标签和生成草稿时的类型几乎一一对应，模型可能学到的是"识别写法类型"。用真实草稿抽查过再下结论。
- 对话全部是合成的。把 `~/.laya-chat/history/` 里自己的真实聊天（脱敏后）加进去做 dev 集，评测才有说服力。

## 微调

`notebooks/laya_finetune_laya_chat_kaggle.ipynb`，改自 Laya 官方笔记本，训练脚本原样，只换数据和评测。
把 `data/dataset/` 三个文件传成 Kaggle Dataset `laya-chat-data`，选 T4 x2，从头跑到尾。底座用多语言权重（中文分词正常），`head_max_len=512 / max_len=1024`，和运行时一致；本地用试跑数据演练过预处理，198 条序列没有一条超预算，中位长度 460。
训练完下载 `laya_chat_finetuned.tgz`，解开后把目录路径填进 `~/.laya-chat/config.json` 的 `model`，`subfolder` 留空。
