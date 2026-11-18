# 评分结果关联

在工作目录修复 `solution.py`，并用 `python3 solution.py runs.jsonl reports.jsonl result.json` 生成实际提交的 `result.json`。脚本须支持任意符合下列规则的输入与输出路径。

1. 两个输入都是 UTF-8 JSONL，忽略空白行。运行记录恰有 `task_id`、`run_id`、`scorer_versions`。前两个字段都是非空字符串，`scorer_versions` 是非空数组，包含互异的非空字符串。相同 `(task_id, run_id)` 可以重复提交同一组版本，数组顺序不影响相等。版本集合不同的重复运行是错误。
2. 报告恰有 `task_id`、`run_id`、`scorer_version`、`status`。前三个字段是非空字符串，`status` 只能是 `pass`、`fail` 或 `error`。相同 `(task_id, run_id, scorer_version)` 且状态相同的重复报告只计一次。同键状态冲突是错误，即使该报告没有对应的运行。
3. 为每个去重后运行的每个请求版本输出一行记录，恰有 `task_id`、`run_id`、`scorer_version`、`status`。仅当三个键完全相同才采用报告状态。无对应报告时写 `unknown`。报告存在且标为 `error` 时保留 `error`。单独统计没有匹配请求的唯一报告数，包括未请求的评分版本。
4. 输出一个 JSON 对象，顶层恰有 `results` 和 `ignored_reports`。`results` 按 `(task_id, run_id, scorer_version)` 的 Unicode 字符顺序升序排列，两个输入的行顺序不影响结果。输出为 UTF-8，所有对象键按 Unicode 字符顺序排序，冒号和逗号旁无空格，非 ASCII 字符直接写出，末尾恰有一个换行。成功退出 0。
5. 缺少输入文件、JSON 语法错误、对象内重复键、UTF-8 解码错误或违反第 1、2 条，均须退出 2，在 stderr 写出错误，并保持输出路径原状。

实现全部放在 `solution.py` 中，使用 Python 3.12 标准库。所有标识符和版本字符串必须能直接编码为 UTF-8，含未配对代理码位的记录按第 5 条处理。预置输入用于生成提交产物，验收还会使用独立输入。
