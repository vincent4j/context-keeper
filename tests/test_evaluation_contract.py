"""Regress actual evidence provenance and materialized strict/current budgets."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EVAL = Path(__file__).parent/'evaluations'
sys.path.insert(0, str(EVAL))
from evaluation_contract import assess_commands, BUDGETS
from evaluation_support import prepare_matrix


class EvaluationContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        log = self.root/'docs/context-keeper/worklogs/log.md'
        log.parent.mkdir(parents=True)
        log.write_text('needle old\n'*3+'needle late counterevidence\n')
        self.probe = Path(__file__).parents[1]/'scripts/context_keeper_probe.py'
        self.argv = [sys.executable, str(self.probe), 'search', '--root', str(self.root), '--query', 'needle', '--user-evolution-dir', str(self.root/'empty')]
        self.result = subprocess.run(self.argv, capture_output=True, text=True, check=True)

    def item(self, command, output=None, rc=0):
        return {'command': command, 'aggregated_output': self.result.stdout if output is None else output, 'exit_code': rc}

    def test_real_search_notice_and_failed_command(self):
        import shlex
        command = shlex.join(self.argv)
        self.assertTrue(assess_commands([self.item(command)])['runtime_notice_exposed'])
        self.assertTrue(assess_commands([self.item(shlex.join([self.argv[0], '-B', *self.argv[1:]]))])['runtime_notice_exposed'])
        failed = assess_commands([self.item(command, rc=2)])
        self.assertFalse(failed['runtime_notice_exposed'])
        self.assertEqual(failed['actual_probe_entries'], ['search'])
        self.assertIn('attempts', failed['probe_entry_semantics'])
        self.assertFalse(assess_commands([self.item(command, output='文件内匹配展示受限')])['runtime_notice_exposed'])

    def test_document_help_and_echo_cannot_confirm_exposure(self):
        for command in [f'cat references/search.md; python3 {self.probe} search --help',
                        f'echo "python3 {self.probe} search"',
                        f'rg -n "context_keeper_probe.py search" references/search.md']:
            with self.subTest(command=command):
                row=assess_commands([self.item(command)])
                self.assertFalse(row['runtime_notice_exposed'])
                self.assertEqual(row['actual_probe_entries'], [])

    def test_wrapper_compound_keeps_entry_but_output_is_unknown(self):
        import shlex
        inner=f'cat references/search.md; {shlex.join(self.argv)}'
        command=shlex.join(['/bin/zsh','-lc',inner])
        help_then_search=f'python3 {self.probe} search --help; {shlex.join(self.argv)}'
        self.assertEqual(assess_commands([self.item(help_then_search)])['actual_probe_entries'], ['search'])
        self.assertIsNone(assess_commands([self.item(help_then_search)])['runtime_notice_exposed'])
        row=assess_commands([self.item(command)])
        self.assertIsNone(row['runtime_notice_exposed'])
        self.assertTrue(row['runtime_notice_needs_manual'])
        self.assertEqual(row['actual_probe_entries'], ['search'])
        # A confirmed isolated execution can coexist with an ambiguous execution.
        self.assertTrue(assess_commands([self.item(command), self.item(shlex.join(self.argv))])['runtime_notice_exposed'])

    def test_multiline_shell_output_cannot_confirm_provenance(self):
        import shlex
        inner=shlex.join(self.argv)+'\ncat references/search.md'
        row=assess_commands([self.item(shlex.join(['/bin/zsh','-lc',inner]))])
        self.assertIsNone(row['runtime_notice_exposed'])
        self.assertTrue(row['runtime_notice_needs_manual'])
        self.assertEqual(row['actual_probe_entries'], ['search'])

    def test_multiline_document_before_search_is_manual(self):
        import shlex
        inner='cat references/search.md\n'+shlex.join(self.argv)
        row=assess_commands([self.item(shlex.join(['/bin/zsh','-lc',inner]))])
        self.assertEqual(row['actual_probe_entries'], ['search'])
        self.assertIsNone(row['runtime_notice_exposed'])
        self.assertTrue(row['runtime_notice_needs_manual'])

    def test_multiline_help_after_search_does_not_erase_entry(self):
        import shlex
        inner=shlex.join(self.argv)+'\n'+shlex.join([*self.argv, '--help'])
        row=assess_commands([self.item(shlex.join(['/bin/zsh','-lc',inner]))])
        self.assertEqual(row['actual_probe_entries'], ['search'])
        self.assertIsNone(row['runtime_notice_exposed'])
        self.assertTrue(row['runtime_notice_needs_manual'])

    def test_prepared_strict_and_current_have_one_budget_source(self):
        assignments={1:'strict',2:'current',3:'strict',4:'current'}
        schedule=[('middle','resume',rep) for rep in assignments]
        budgets={f'middle-resume-{rep}':BUDGETS[name] for rep,name in assignments.items()}
        out=self.root/'prepared'
        prepare_matrix(out,repo=Path(__file__).parents[1],schedule=schedule,
                       header='# Synthetic project rules\n',prompts={'resume':'continue'},
                       model='synthetic-test',effort='medium',cli_version='not invoked',effective_budgets=budgets)
        protocol=json.loads((out/'protocol.json').read_text())
        scoring=json.loads((out/'scoring.json').read_text())
        self.assertNotIn('project_agents',protocol)
        self.assertEqual(protocol['session_budgets'],scoring['session_budgets'])
        for rep, condition in assignments.items():
            key=f'middle-resume-{rep}'
            material=protocol['session_budgets'][key]
            self.assertEqual(material['effective_budget'],BUDGETS[condition].as_dict())
            self.assertEqual((out/key/'project/AGENTS.md').read_text(),material['project_agents'])
            self.assertEqual(material['budget_instructions'],BUDGETS[condition].instructions())
            self.assertEqual(protocol['scoring']['session_budgets'][key],material)
        self.assertNotIn('1-2 factual sources',protocol['scoring']['axes']['budget'])
