# CSV译文回收检查器 · 有限公开测试

[English](README.md) · [两分钟演示](DEMO.md)

帮助使用CSV交接游戏译文的开发者，在回填之前看到版本变化和潜在覆盖风险。
**仅生成HTML报告，不翻译、不修改CSV、不合并、不导入游戏。**

## 快速运行

Python 3.10或以上，无第三方依赖。在本目录打开终端：

~~~powershell
python checker.py examples/old_source.csv examples/new_source.csv examples/returned_translation.csv -o my_report.html
~~~

用浏览器打开生成的HTML。输出文件必须不存在，父目录必须已存在。
请使用本人已安装的Python；无需安装第三方依赖。

现成演示：打开 demo_report.html。测试数据在 examples/，都是合成内容。
报告可点击六个摘要卡跳转到相应清单。demo_screenshot.png 为本机浏览器实测截图。

## 输入约定

三个文件必须来自同一项目、同一目标语言、同一次送译基线。
工具无法鉴别你是否拿错了项目或目标语言。

| 文件 | 必需列 | 可选列 |
|---|---|---|
| old_source.csv：送译时冻结的副本 | id,source | translation：当时的译文 |
| new_source.csv：现在的项目内容 | id,source | translation：当前的译文 |
| returned_translation.csv：译者返回内容 | id,source,translation | 其他列忽略 |

列名大小写固定；UTF-8或UTF-8 BOM，英文逗号分隔。支持CSV标准引号、中文、多行内容。
每个文件最多10 MiB、50000条记录；单字段最多262144字符。
不支持Excel工作簿、自动列映射、多语言列、ICU/复数/占位符校验。
ID按文本精确比较，保留001之类的前导零。空ID或首尾空格报输入错误；不会自动修正。
额外列不会参加比较；尤其不验证context、语言、说话人或引擎元数据。

**建议旧、新源文件都保留translation列。**
缺少任一列仍可检查原文版本，但不能识别“送译期间别人改了现有译文”，报告会明确提示检查不完整。

## 六项检查如何解释

1. 新增ID：new中有、old中没有。不是错误。
2. 删除ID：old中有、new中没有。不是错误。
3. 修改文本：同ID的source逐字不同，包括空格和换行；不推断语义是否相同。
4. 缺失翻译：new中的ID在返回文件缺失，或返回translation为空/全空白。
   这是**本次返回缺失**，不等于项目从未翻译；部分回收会自然出现此项。
5. 重复ID：列出每份文件中的重复ID及记录结束物理行号。多行CSV的行号是该记录结束行。
   不取第一条或最后一条；受影响ID跳过文本/缺译判定。
6. 潜在错误覆盖：旧原文已改、返回原文不匹配送译原文、已删除或未知ID、
   没有旧基线的新ID、重复ID、空译文及当前译文并发修改。

如果当前译文与返回译文完全相同，不报并发覆盖冲突。
如果source曾变化又恢复、ID被删除后复用、语言拿错、语义变化但文本未改，三份快照不能发现。
原文已改时即使返回文本看似正确，也保守要求人工复核，不做AI判断。

报告计数按各类别的记录计算。同ID可能出现在多类中，不能相加成错误总数。
“未检出上述风险”只针对已提供的字段和规则，**不等于安全导入或翻译质量通过**。
新增、删除、缺译并不全部是故障；只供工作流复核。

## 安全和隐私

- 只读输入，独占新建HTML；拒绝已有输出（包括硬链接），不覆盖原文件。
- 不执行CSV内容，不调用网络或模型，无遥测。
- HTML中的输入文本被转义，报告不包含脚本、外链资源、表单。
- 报告会包含原文、译文、ID及文件名；没有自动脱敏，分享前自行检查。
- SHA-256标识读取时的文件内容。读取期间不要编辑输入；工具不锁文件，也不保证三份文件由同一时刻导出。
- Excel等软件可能执行CSV公式；本工具不打开Excel，不改变原始正文。请不要随意双击未知来源CSV。

## 退出码

- 0：报告生成，本轮未检出变化/风险/检查限制；不是语义质量保证。
- 1：报告生成，有变化、风险或检查范围限制。这是正常检查结果，不是程序崩溃。
- 2：输入无效或输出写入失败。输入无效时可生成“检查未完成”HTML；输出路径错误时不能生成。
- 输入格式错误时不展示部分成功结论，修复后用新输出文件名重跑。

## Demo预期

样例涵盖新增1、删除1、修改2、缺译3、重复ID记录1、潜在覆盖7。
例如 quest 从“Collect 5 apples”变为“Collect 10 apples”，返回译文仍对应旧文本。
concurrent 的当前译文已被其他人改动，报告同时列出送译、当前和返回值。
unicode 展示中文、多行、引号正常解析。HTML标签样例只显示文字，不执行。

## 测试

~~~powershell
python -m unittest -v test_checker
~~~

包括格式错误、BOM、空值、中文多行、并发修改、重复ID、HTML转义、原始文件哈希、
已有输出/硬链接拒绝覆盖、错误报告、输入大小限制。临时测试目录只在本项目中创建并清理。

## 与现成工具的关系

BabelEdit已支持CSV导出/导入；Weblate已有离线回收、导入选择和冲突处理。
本工具的候选差异是：无需迁移TMS，直接提供三份本地CSV得到一份只读报告。
**不宣称现成产品缺少上述功能，也尚未证明本工具更省时。** 已使用成熟TMS的人通常不应额外使用它。
未安装或购买竞品，未做竞品计时实测；不宣称功能独占。

## 有限公开测试

值得进行一次有限免费试用，尚不值得收费或扩功能。
目标：使用稳定ID并通过CSV往返译文的游戏开发者；不面向任意Excel需求。
本轮采用MIT许可证，仅征集真实使用反馈，不收费，也不承诺新功能。请通过仓库Issue模板反馈，勿上传真实项目文件。

成功：至少一名真实目标用户实际使用、提供具体反馈，并描述真实工作流，三项同时满足。
停止：现成工具同样简单、用户需要模板定制/翻译服务、安装门槛阻止使用、
每人支持超过15分钟，或发布后7–14天没有有效反馈，则停止主动投入。第7天复盘，最迟第14天停止；没有曝光不代表没有需求。

## Quick English note

Read-only local CSV translation handoff check. Three UTF-8 CSV files in, one HTML report out.
Required columns: id/source in old and new; id/source/translation in returned.
Include translation in both source snapshots to detect concurrent target edits.
No translation, merge, upload, telemetry or engine integration. Python 3.10+, standard library.
The report text is Chinese in this MVP. Do not advertise it as an English-localized product.

