from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from audit_common import QUICK_AUDIT_PROFILE, concern_sort_key
from audit_documents import run as run_completeness
from audit_normative import run as run_normative

SKILL_VERSION = "1.0.2"  # 1.0.2: 位置显示改为章条坐标（第X章第X条），不再显示 para:N；关注项/偏差按文档顺序排列。1.0.1: 编号缺失防误报——章/节/条识别接入 numbering.xml 自动编号模板核实；F4/F5 覆盖自动编号章标题并渲染编号前缀


def safe_name(value: str) -> str:
    return re.sub(r'[\/:*?"<>|]', '_', value)


def escape_markdown(value) -> str:
    return str(value or '').replace('|', '\\|').replace('\n', ' ')


def evidence_locations(item: dict) -> str:
    locations = [evidence.get('location', '') for evidence in item.get('evidence', []) if evidence.get('location')]
    return '、'.join(locations[:8]) or '未发现'


def make_report(completeness: list[dict], normative: list[dict], elapsed: float) -> str:
    normative_by_file = {item['document']['source_file']: item for item in normative}
    lines = [
        '# 制度快速审核报告', '',
        f'> 技能版本：{SKILL_VERSION}；审核模式：{QUICK_AUDIT_PROFILE["name"]}；耗时：{elapsed:.2f}秒。',
        '> 默认不审核：' + '、'.join(QUICK_AUDIT_PROFILE['excluded_by_default']) + '。', ''
    ]
    for complete in completeness:
        norm = normative_by_file.get(complete['document']['source_file'])
        classification = complete['classification']
        matched = '、'.join(item['canonical_name'] for item in classification.get('matched_organizations', [])) or '未识别特定组织'
        concerns = [item for item in complete['mandatory_clause_checks'] + complete['chapter_checks'] if item['status'] not in {'存在', '不适用'}]
        concerns.sort(key=concern_sort_key)
        naming = norm['naming']['deviations'] if norm else []
        formatting = norm['format']['deviations'] if norm else []
        lines += [
            f"## {complete['document']['file_name']}", '',
            f"- 正文正式标题：{complete['document']['title']}",
            f"- 制度类型：{classification['primary_type']}；名称层级：{classification['declared_level']}",
            f"- 组织范围：{classification.get('organization_scope', 'unresolved')}；命中组织：{matched}",
            f"- 完整性关注项：{len(concerns)}项；命名偏差：{len(naming)}项；格式偏差：{len(formatting)}项",
            f"- 规则覆盖率：{complete['coverage']['coverage_rate']:.0%}", ''
        ]
        lines += ['### 完整性关注项', '', '| 编号 | 审核项 | 状态 | 严重程度 | 位置 | 建议 |', '|---|---|---|---|---|---|']
        if concerns:
            for item in concerns:
                lines.append(f"| {item['rule_id']} | {escape_markdown(item['item'])} | {item['status']} | {item['severity']} | {evidence_locations(item)} | {escape_markdown(item['suggestion'])} |")
        else:
            lines.append('| - | 未发现缺失或部分项 | - | - | - | - |')
        lines += ['', '### 规范性偏差', '', '| 编号 | 类别 | 实际 | 要求/建议 |', '|---|---|---|---|']
        for item in naming:
            lines.append(f"| {item['id']} | 命名 | {escape_markdown(item['actual'])} | {escape_markdown(item['required'])} |")
        for item in formatting:
            lines.append(f"| {item['id']} | 格式 | {escape_markdown(item['actual'])} | {escape_markdown(item['required'])} |")
        if not naming and not formatting:
            lines.append('| - | - | 未发现偏差 | - |')
        lines.append('')
    return '\n'.join(lines)


def make_detailed_report(completeness: list[dict], normative: list[dict], elapsed: float) -> str:
    normative_by_file = {item['document']['source_file']: item for item in normative}
    lines = [
        '# 制度完整性和规范性审核报告', '',
        f'> 技能版本：{SKILL_VERSION}；审核耗时：{elapsed:.2f}秒。',
        '> 审核边界：检查制度名称、格式属性、必备条款和章节主题是否存在；不判断条款合法性、法规时点有效性或跨制度冲突。', ''
    ]
    for complete in completeness:
        norm = normative_by_file.get(complete['document']['source_file'])
        all_checks = complete['mandatory_clause_checks'] + complete['chapter_checks']
        concerns = [item for item in all_checks if item['status'] not in {'存在', '不适用'}]
        lines += [
            f"## {complete['document']['file_name']}", '',
            f"- 源文件：{complete['document']['source_file']}",
            f"- 正文正式标题：{complete['document']['title']}",
            f"- 制度类型：{complete['classification']['primary_type']}；名称层级：{complete['classification']['declared_level']}",
            f"- 完整性规则：{complete['coverage']['selected_rules']}项；执行覆盖率：{complete['coverage']['coverage_rate']:.0%}",
            f"- 完整性关注项：{len(concerns)}项；命名偏差：{len(norm['naming']['deviations']) if norm else 0}项；格式偏差：{len(norm['format']['deviations']) if norm else 0}项", ''
        ]
        lines += ['### 必备条款', '', '| 编号 | 审核项 | 状态 | 严重程度 | 证据位置 | 建议 |', '|---|---|---|---|---|---|']
        for item in complete['mandatory_clause_checks']:
            lines.append(f"| {item['rule_id']} | {escape_markdown(item['item'])} | {item['status']} | {item['severity']} | {evidence_locations(item)} | {escape_markdown(item['suggestion']) or '-'} |")
        lines += ['', '### 章节主题', '', '| 编号 | 章节或主题 | 状态 | 严重程度 | 证据位置 | 建议 |', '|---|---|---|---|---|---|']
        for item in complete['chapter_checks']:
            lines.append(f"| {item['rule_id']} | {escape_markdown(item['item'])} | {item['status']} | {item['severity']} | {evidence_locations(item)} | {escape_markdown(item['suggestion']) or '-'} |")
        if norm:
            lines += ['', '### 命名审核', '', '| 编号 | 检查项 | 状态 | 实际 | 要求 |', '|---|---|---|---|---|']
            for item in norm['naming']['checks']:
                lines.append(f"| {item['id']} | {escape_markdown(item['item'])} | {'通过' if item['passed'] else '不通过'} | {escape_markdown(item['actual'])} | {escape_markdown(item['required'])} |")
            lines += ['', '### 格式审核', '', '| 编号 | 检查项 | 状态 | 实际 | 要求 |', '|---|---|---|---|---|']
            for item in norm['format']['checks']:
                status = '通过' if item['passed'] else '不通过' if item.get('readable', True) else '未识别'
                lines.append(f"| {item['id']} | {escape_markdown(item['item'])} | {status} | {escape_markdown(item['actual'])} | {escape_markdown(item['required'])} |")
        lines += ['', '### 审核说明', '',
                  '- 命名审核以DOCX正文正式标题为准；文件名只用于名称载体一致性检查。',
                  '- 正文两端对齐和首行缩进默认不审核。',
                  '- 章标题按黑体16pt、加粗、居中审核；节标题不套用章标题标准。',
                  '- 可见编号和OOXML自动编号均可识别。',
                  '- 位置一律使用章条坐标（如“第一章第三条”）；完整性关注项与格式偏差按文档顺序排列。',
                  '- 源文件不作修改。', '']
    return '\n'.join(lines)


def run(documents: list[Path], output_dir: Path) -> dict:
    missing = [str(path) for path in documents if not path.is_file()]
    if missing:
        raise FileNotFoundError('未找到输入文件：' + '；'.join(missing))
    start = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    completeness = run_completeness(documents, output_dir / 'completeness')
    normative = run_normative(documents, output_dir / 'normative')
    elapsed = time.perf_counter() - start
    result = {
        'audit_info': {
            'skill': 'policy-full-audit',
            'skill_version': SKILL_VERSION,
            'parsed_at': datetime.now().isoformat(timespec='seconds'),
            'elapsed_seconds': round(elapsed, 3),
            'profile': QUICK_AUDIT_PROFILE,
        },
        'documents': len(documents),
        'completeness': completeness,
        'normative': normative,
    }
    (output_dir / '制度快速审核报告.md').write_text(make_report(completeness, normative, elapsed), encoding='utf-8')
    (output_dir / '制度完整性和规范性审核报告.md').write_text(make_detailed_report(completeness, normative, elapsed), encoding='utf-8')
    (output_dir / '制度快速审核汇总.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'documents': len(documents), 'elapsed_seconds': round(elapsed, 3), 'output_dir': str(output_dir.resolve())}, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='一键执行制度完整性、规范性和组织架构识别')
    parser.add_argument('documents', nargs='+', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    default_name = safe_name(args.documents[0].stem) if len(args.documents) == 1 else '批量制度'
    run(args.documents, args.output_dir or Path.cwd() / '审核输出' / '快速审核' / default_name)


if __name__ == '__main__':
    main()
