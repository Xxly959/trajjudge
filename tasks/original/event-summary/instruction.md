# 轨迹事件汇总

在工作目录修复 `solution.py`，并用 `python3 solution.py input.jsonl result.json` 生成实际提交的 `result.json`。脚本须支持任意符合以下规则的输入与输出路径。仅提交文字说明不满足交付要求。

1. 输入是 UTF-8 JSONL。忽略空白行。每条记录是一个 JSON 对象，恰有五个字段。 `event_id`、`run_id` 是非空字符串，`attempt` 是大于等于 1 的整数，`seq` 是非负整数。布尔值不是整数。 `status` 必须是 `started`、`timeout`、`succeeded` 或 `failed`。
2. `event_id` 在整个文件中唯一。内容完全相同的重复投递只计一次，JSON 键顺序和空白不影响相等。相同 ID 内容不同，或同一 `(run_id, attempt, seq)` 被不同事件占用，视为错误。
3. 对每个运行，选 `(attempt, seq)` 最大的事件作为最终状态。新 attempt 优先于旧 attempt，同 attempt 内按 seq 排序。输入顺序无关。旧 attempt 的迟到事件仍计数。
4. 输出一个 JSON 对象，顶层恰有 `runs` 和 `unique_events`。 `runs` 按 `run_id` 的 Unicode 字符顺序升序排列，每项恰有 `run_id`、最终 `attempt`、最终 `status` 和该运行的 `unique_events`。顶层的 `unique_events` 为全文件唯一事件数。空输入输出 `{"runs":[],"unique_events":0}`。输出为 UTF-8，所有对象键按 Unicode 字符顺序排序，冒号和逗号旁无空格，非 ASCII 字符直接写出，末尾恰有一个换行。成功退出 0。
5. JSON 语法错误、同一 JSON 对象内重复键、UTF-8 解码错误和违反第 1、2 条的记录，均须退出 2，在 stderr 写出错误，并保持输出路径原状。输入不存在时采用相同处理。

实现全部放在 `solution.py` 中，使用 Python 3.12 标准库。所有标识符必须能直接编码为 UTF-8，含未配对代理码位的记录按第 5 条处理。预置的 `input.jsonl` 用于生成提交产物，验收还会使用独立输入。
