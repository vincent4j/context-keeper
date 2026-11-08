"""Small shared contracts for new evaluations; never rewrites historical evidence."""
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import shlex


@dataclass(frozen=True)
class EffectiveBudget:
    name: str
    index_counts_as_source: bool
    cumulative_lines: bool
    sources: int = 2
    lines: int = 80
    completed_commands: int = 10

    def as_dict(self):
        return asdict(self)

    def instructions(self):
        index = ('memory-keeper.md索引正文计入来源份数及展示行数。' if self.index_counts_as_source
                 else '用于定位的memory-keeper.md索引不计事实来源份数及事实展示行数；引用摘要不能替代核对原始依据。')
        line_rule = (f'来源正文累计最多{self.lines}行，不按单次读取重置。' if self.cumulative_lines
                     else f'事实来源正文单次通常不超过{self.lines}行，不设累计行数硬上限。')
        return (f'统一读取预算：最相关事实来源至多{self.sources}份。' + index + line_rule + '\n'
                '仅按实际展示正文的不同文件计来源；同文件多次定点读取只计1份，重复展示的正文行仍计行。'
                'probe可见片段按实际文件归属计源计行，内部未展示读取、纯路径定位不计。\n'
                'Skill、reference、脚本源码及--help共同豁免事实来源与行数，但执行命令仍计数。\n'
                f'本次实验执行命令合计至多{self.completed_commands}条，以completed command_execution事件计；'
                'started/completed不重复计，shell多步同次执行仍为一条。此命令上限是实验约定，不是产品合同。'
                '预算不足如实报告未确定范围，不为补全全库扫描或修改文件。\n')


CURRENT_BUDGET = EffectiveBudget('current', False, False)
STRICT_BUDGET = EffectiveBudget('strict', True, True)
BUDGETS = {'current': CURRENT_BUDGET, 'strict': STRICT_BUDGET}


def budget_materials(header, budget):
    """The same value generates project instructions and both scoring documents."""
    return {'effective_budget': budget.as_dict(),
            'project_agents': header + budget.instructions(),
            'budget_instructions': budget.instructions()}


_NOTICE = re.compile(r'^- 文件内匹配展示受限：仅展示前\d+条，仍有匹配行未展示；本片段不代表完整结论。$')
_CANDIDATE = re.compile(r'^\d+[.] \[[^\]]+\] ')
_OPERATORS = {';', '&&', '||', '|', '&', '>', '>>', '<', '<<', '(', ')', '\n'}


def _probe_calls(command):
    """Recognize literal probe argv only. Shell composition is deliberately not attributed."""
    try:
        words = shlex.split(command)
        if len(words) >= 3 and Path(words[0]).name in {'sh', 'bash', 'zsh'} and words[1] in {'-c', '-lc'}:
            command = words[2]
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()\n')
        lexer.whitespace_split = True
        # Retain newlines as statement boundaries so a preceding cat or later
        # --help cannot swallow a separate literal search invocation.
        lexer.whitespace = lexer.whitespace.replace('\n', '')
        words = ['\n' if '\n' in word and set(word) <= set(';&|<>()\n') else word
                 for word in lexer]
    except ValueError:
        return [], True
    compound = ('\n' in command or any(w in _OPERATORS for w in words)
                or '$(' in command or '`' in command)
    calls = []
    for index, word in enumerate(words[:-1]):
        if Path(word).name != 'context_keeper_probe.py':
            continue
        # Require an executable Python invocation, not cat/echo/rg of code or text.
        start = max((n+1 for n in range(index) if words[n] in _OPERATORS), default=0)
        prefix = words[start:index]
        if prefix and not (re.fullmatch(r'python(?:3(?:[.]\d+)?)?', Path(prefix[0]).name)
                           and all(flag in {'-B', '-u', '-I', '-E', '-s', '-S', '-O', '-OO'} for flag in prefix[1:])):
            continue
        mode = words[index+1]
        end = next((n for n in range(index+1, len(words)) if words[n] in _OPERATORS), len(words))
        args = words[index+1:end]
        if mode in {'resume', 'search'} and not any(a in {'--help', '-h'} for a in args):
            calls.append(mode)
    return calls, compound


def assess_commands(commands):
    """Commands must already be item.completed command_execution items (not starts).

    A compound command's output has no per-subcommand provenance. It can require
    manual review, but can never confirm notice exposure merely by matching text.
    """
    entries, confirmed, ambiguous = [], False, False
    for item in commands:
        calls, compound = _probe_calls(item.get('command', ''))
        entries.extend(calls)
        if 'search' not in calls:
            continue
        in_candidate, notice = False, False
        for line in item.get('aggregated_output', '').splitlines():
            if _CANDIDATE.match(line):
                in_candidate = True
            if in_candidate and _NOTICE.fullmatch(line):
                notice = True
        if not notice:
            continue
        if compound:
            ambiguous = True
        elif item.get('exit_code') == 0:
            confirmed = True
    exposed = True if confirmed else None if ambiguous else False
    return {'actual_probe_entries': entries,
            'probe_entry_semantics': 'literal invocation attempts, including failed commands; help excluded',
            'runtime_notice_exposed': exposed,
            'runtime_notice_assessment': 'confirmed' if confirmed else 'needs_manual' if ambiguous else 'absent',
            'runtime_notice_needs_manual': ambiguous}
