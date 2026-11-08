"""Output-boundary regressions: incomplete evidence must be visible, not inferred complete."""
import tempfile
from pathlib import Path
from test_context_keeper_probe import IsolatedProbeTestCase, PROBE, _call, _experience

NOTICE = '文件内匹配展示受限'


class MatchTruncationTests(IsolatedProbeTestCase):
    def test_late_counterevidence_and_exact_limit(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d)/'docs/context-keeper/worklogs/log.md'
            log.parent.mkdir(parents=True)
            for count, limit, truncated in [(4, 3, True), (3, 3, False), (0, 3, False), (4, 10, False), (4, 0, False)]:
                with self.subTest(count=count, limit=limit):
                    log.write_text('上传：已解决\n' * max(0, count-1) + ('上传：25 MB失败\n' if count else '无关\n'))
                    rc, out = _call('search', '--root', d, '--query', '上传', '--hit-lines', str(limit))
                    self.assertEqual(rc, 0)
                    self.assertEqual(NOTICE in out, truncated)
                    if count == 4 and limit == 3:
                        self.assertNotIn('25 MB失败', out)
                    if count == 4 and limit == 10:
                        self.assertIn('25 MB失败', out)

    def test_notice_belongs_only_to_truncated_file_and_is_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'docs/context-keeper/worklogs'
            folder.mkdir(parents=True)
            (folder/'a.md').write_text('上传旧结论\n'*4)
            (folder/'b.md').write_text('上传新结论\n')
            before = {p: p.read_bytes() for p in folder.iterdir()}
            rc, out = _call('search', '--root', d, '--query', '上传')
            self.assertEqual(rc, 0)
            self.assertEqual(out.count(NOTICE), 1)
            self.assertLess(out.index('a.md'), out.index(NOTICE))
            self.assertEqual(before, {p: p.read_bytes() for p in folder.iterdir()})

    def test_pending_experience_and_for_write_remain_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'docs/context-keeper/evolution'
            folder.mkdir(parents=True)
            (folder/'exp.md').write_text(_experience(status='待验证'))
            rc, out = _call('search', '--root', d, '--query', '.', '--hit-lines', '1')
            self.assertEqual(rc, 0)
            self.assertIn('待验证，暂停采用，仅供核查', out)
            self.assertIn(NOTICE, out)
            self.assertNotIn(NOTICE, _call('search', '--root', d, '--query', '.', '--hit-lines', '1', '--for-write')[1])
            self.assertNotIn(NOTICE, _call('resume', '--root', d, '--query', '.')[1])

    def test_index_fallback_uses_actual_index_matches(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'docs/context-keeper/evolution'
            folder.mkdir(parents=True)
            (folder/'exp.md').write_text(_experience())
            for count in [3, 4]:
                (folder/'index.md').write_text('needle [经验](exp.md)\n'*count)
                rc, out = _call('search', '--root', d, '--query', 'needle')
                self.assertEqual(rc, 0)
                self.assertEqual(NOTICE in out, count > 3)

    def test_legacy_negative_slice_interface(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'sample.md'
            p.write_text('match1\nmatch2\nmatch3\n')
            self.assertEqual(PROBE._file_hits(p, PROBE._compile_pattern('match'), -1), ['match1', 'match2'])
