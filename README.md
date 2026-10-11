# CSV Translation Handoff Checker

[中文说明](README.zh-CN.md) · [Two-minute demo](DEMO.md)

Lightweight CSV checker for detecting stale translation risks during game localization handoff.
**Did the source text change while the translation was away?** Compare the sent snapshot, the current file, and the returned translation before manually importing anything.

This is a limited feedback prototype, not a localization platform. **The CLI messages and HTML report are currently in Chinese.** The English demo explains the labels; an English UI is not included.

## Try the synthetic example

Requires Python 3.10+. No third-party packages, account, network service, or API key.

From the extracted project directory:

~~~shell
python checker.py examples/old_source.csv examples/new_source.csv examples/returned_translation.csv -o my_report.html
~~~

Open `my_report.html` in your browser. Its parent directory must exist; use a **new output filename** each time.
Exit code **1 is expected for this example**: the report contains findings. It is not a crash.

You can also open [the pre-generated report](demo_report.html) without running Python.
The example files are entirely synthetic, not extracted from a customer or game project.

## Inputs and output

Use three snapshots from **the same project, target language, and handoff**:

| Input | Required columns | Optional column |
|---|---|---|
| `old_source.csv`: snapshot when sent | `id,source` | `translation`: target text at that time |
| `new_source.csv`: current project | `id,source` | `translation`: current target text |
| `returned_translation.csv`: returned work | `id,source,translation` | Other columns are ignored |

UTF-8 (BOM accepted), comma-separated CSV, exact lowercase column names. Quoted commas, Chinese text, multiline text, and leading-zero IDs are supported.
IDs are compared exactly. Empty IDs or IDs with leading/trailing whitespace are rejected.
Limits per file: 10 MiB, 50,000 records; per field: 262,144 characters.

**Include `translation` in both source snapshots to detect concurrent edits to existing translations.**
Otherwise the report explicitly marks that part of the check as incomplete.

Output: one self-contained HTML report. **Inputs are not modified. No merged CSV is produced.**

## What the report checks

| Chinese report label | Meaning |
|---|---|
| 新增ID | IDs present in the new source but not the old |
| 删除ID | IDs removed from the source |
| 修改文本 | Exact source-text changes, including whitespace |
| 缺失翻译 | Current IDs missing from this return, or blank returned translations |
| 重复ID | Duplicate IDs and their record-ending line numbers |
| 潜在错误覆盖 | Stale source, altered returned source, deleted/unknown IDs, missing baseline, ambiguous duplicates, blank returns, or conflicting concurrent target edits |

One ID can appear in several sections; counts are not additive.
Missing **returned** text does not mean the project has never had a translation. Partial returns naturally show missing entries.
Duplicate IDs are not resolved by choosing the first or last record.
“No detected risk” is **not** approval to import.

## What it does not do

No translation, AI generation, quality scoring, automatic merge/import, Unity integration, cloud service, GUI, payment, or telemetry.
No arbitrary Excel format, plural/ICU/placeholder validation, context comparison, or automatic column mapping.
It cannot detect the wrong target language/project, reused IDs, or a source that changed and later reverted between snapshots.
Already using a satisfactory translation-management workflow? You may not need this tool.

## Privacy and safe use

Run locally on copies of authorized files; do not edit inputs during the run. The tool does not lock files.
Reports include text, IDs, filenames and input hashes. **Do not post a real project CSV or unredacted report in a public Issue.**
Reproduce problems with invented text instead.
CSV/HTML input text is not executed; HTML is escaped. Spreadsheet applications may interpret CSV formulas if you open the CSV there.
Existing output files are refused, including aliases/hard links. Choose a new output path.

Exit codes: 0 = report with no detected findings/limitations; 1 = report with changes, risks, or coverage limits; 2 = invalid input or output failure.
Invalid input reports say the checks were not completed; path/write failures may produce no report.

## Feedback wanted

After using it on a real task, please describe:
1. Your role and how you currently exchange translations.
2. Whether you ran only the demo or also a real workflow.
3. What worked or failed, and the exact command/exit code if relevant.
4. One concrete useful finding, false alarm, missing check, or an existing alternative that already does this better.
5. Whether you would use it for the next return batch, and why.

Downloads alone are not treated as usage. No private project data is needed.
Use the repository feedback Issue template. There is no hosted endpoint or support mailbox.

## Tests and existing alternatives

~~~shell
python -m unittest -v test_checker
~~~

The local Windows/Python 3.11.9 build passed 19 tests covering malformed CSV, concurrent edits, encoding, escaping, unchanged inputs, and overwrite protection.
Other systems are not claimed as tested.

BabelEdit supports CSV import/export, and Weblate has offline return and conflict-handling workflows.
This prototype tests the convenience of **three standalone files to one local report**, not a claim that those products lack these capabilities.
No comparative timing or real-user benefit has been established.

## Limited public test

This is a limited, free feedback test. No customers, testimonials, orders or paid plans are claimed.
Licensed under the MIT License; see LICENSE. Real-world usefulness is not yet established.

