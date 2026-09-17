"""Regression cases derived from the agreed behavior and the second audit."""
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_context_keeper_probe import PROBE, _call, _experience, _write_valid_context, _save


class AcceptanceTests(unittest.TestCase):
    def test_invalid_config_never_creates_a_second_store(self):
        for content in ('{broken', '[]', '{}', '{"directory": 42}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                config = root / 'context-keeper.json'
                config.write_text(content)
                rc, out = _call('init', '--root', d, '--approved')
                self.assertEqual(rc, 2, out)
                self.assertFalse((root / 'docs' / 'context-keeper').exists())
                self.assertEqual(config.read_text(), content)

    def test_migration_preserves_non_markdown_and_absolute_evidence(self):
        for link in ('../../evidence.json', '../../photo.png', '<../../evidence file.json>', 'ABSOLUTE'):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                _call('init', '--root', d, '--approved')
                store = root / 'docs' / 'context-keeper'
                evidence = store / 'evolution/evidence.json'
                evidence.write_text('{}')
                destination = str(evidence) if link == 'ABSOLUTE' else link
                log = store / 'worklogs/2026-09-16-证据.md'
                original = f'# 证据\n[来源]({destination})\n'
                log.write_text(original)
                rc, out = _call('init', '--root', d, '--store-dir', 'notes/deeper/records', '--migrate', '--approved')
                self.assertEqual(rc, 2, out)
                self.assertEqual(log.read_text(), original)
                self.assertFalse((root / 'notes/deeper/records').exists())
                self.assertFalse((root / 'context-keeper.json').exists())

    def test_history_keeps_valid_messages_before_partial_json_line(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            codex = root / 'codex.jsonl'
            codex.write_text(json.dumps({'type':'session_meta','payload':{'cwd':str(root)}})+'\n'+json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':'已核验事实'}})+'\n{"partial":')
            claude = root / 'claude.jsonl'
            claude.write_text(json.dumps({'cwd':str(root),'type':'user','message':{'content':'已核验事实'}})+'\n{"partial":')
            for reader, path in ((PROBE._codex_messages,codex),(PROBE._claude_messages,claude)):
                messages = reader(path, root)
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0][1], '已核验事实')

    def test_promote_cannot_overwrite_user_index(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as u:
            root = Path(d)
            _call('init', '--root', d, '--approved')
            source = root / 'docs/context-keeper/evolution/经验.md'
            source.write_text(_experience())
            index = Path(u) / 'index.md'
            index.write_text('# 已有用户索引\n')
            for name in ('index.md', 'Index.md', 'no-extension', '../escape.md'):
                rc, out = _call('promote-evolution', '--root', d, '--source', str(source), '--approved', '--replace', '--target-name', name, '--user-evolution-dir', u)
                self.assertEqual(rc, 2, out)
                self.assertEqual(index.read_text(), '# 已有用户索引\n')

    def test_old_plan_edit_and_deletion_block_delivery_without_git(self):
        for remove in (False, True):
            with self.subTest(remove=remove), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                _call('init', '--root', d, '--approved')
                _, name = _call('record-path', '--root', d, '--kind', 'plan', '--title', '旧计划', '--session-id', 'old')
                old = root / name.strip()
                # Begin the new session before editing anything.
                _, name = _call('record-path', '--root', d, '--kind', 'worklog', '--title', '本轮', '--session-id', 'new')
                if remove:
                    old.unlink()
                else:
                    old.write_text('<!-- context-keeper: session-id=new -->\n# overwritten')
                rc, out = _call('save-report', '--root', d, '--worklog', name.strip(), '--session-id', 'new')
                self.assertEqual(rc, 2)
                self.assertIn('历史记录被改写或删除', out)
                self.assertNotIn('已保存上下文', out)

    def test_plan_quality_and_invalid_date(self):
        with tempfile.TemporaryDirectory() as d:
            _call('init', '--root', d, '--approved')
            rc, _ = _call('record-path', '--root', d, '--kind', 'plan', '--title', '需求', '--session-id', 's', '--date', 'not-a-date')
            self.assertEqual(rc, 2)
            _, name = _call('record-path', '--root', d, '--kind', 'plan', '--title', '需求', '--session-id', 's')
            path = Path(d) / name.strip()
            self.assertTrue(PROBE._validate_plan(path))
            path.write_text(path.read_text() + '\n' + '\n'.join(f'## {h}\n{v}\n' for h, v in [('用户需求','用户要求保存记录'),('范围','仅记录'),('实施计划','实现并检查'),('验证方式','检查原文链接'),('待确认','无')]))
            self.assertFalse(PROBE._validate_plan(path))

    def test_verified_rank_dedup_index_trigger_and_resume(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as u:
            root = Path(d); _call('init', '--root', d, '--approved')
            evo = root / 'docs/context-keeper/evolution'
            (evo/'a.md').write_text(_experience('待验证','CK-A','待验证'))
            valid = _experience('核对计时','CK-Z')
            (evo/'z.md').write_text(valid)
            (Path(u)/'copy.md').write_text(valid)
            rc, out = _call('search','--root',d,'--query','生成耗时','--entries','1','--user-evolution-dir',u)
            self.assertEqual(rc,0); self.assertIn('核对计时',out); self.assertNotIn('待验证；',out)
            _, out = _call('search','--root',d,'--query','生成耗时','--user-evolution-dir',u)
            self.assertIn('命中 2 条',out)
            (evo/'index.md').write_text('# 索引\n- [核对计时](z.md)；触发词：特殊别名\n')
            _, out = _call('search','--root',d,'--query','特殊别名','--user-evolution-dir',u)
            self.assertIn('核对计时',out)
            _, out = _call('resume','--root',d,'--query','生成耗时')
            self.assertIn('核对计时',out)

    def test_replacement_requires_real_current_target(self):
        with tempfile.TemporaryDirectory() as d:
            old = Path(d)/'old.md'; new = Path(d)/'new.md'
            old.write_text(_experience('旧','CK-1','已替代'))
            self.assertTrue(PROBE._validate_evolution(old))
            new.write_text(_experience('新','CK-2'))
            old.write_text(old.read_text() + '- **替代为：** [新](new.md)\n')
            self.assertFalse(PROBE._validate_evolution(old))
            new.write_text(_experience('新','CK-2','已替代')+'- **替代为：** [旧](old.md)\n')
            self.assertTrue(PROBE._validate_evolution(old))

    def test_coverage_real_links_and_evolution_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _call('init','--root',d,'--approved')
            store=root/'docs'/'context-keeper'; memory=store/'memory-keeper.md'
            plan=store/'plans/2026-09-16-需求.md'; plan.write_text('<!-- context-keeper: session-id=s -->\n# 需求\n[断链](missing.md)')
            memory.write_text('# memory\n'+plan.name)
            rc,out=_call('coverage','--root',d)
            self.assertEqual(rc,1)
            for expected in ('evolution_entry_missing=1','plans_unindexed=1','broken_links=1','plans_invalid=1'):
                self.assertIn(expected,out)

    def test_pending_state_and_completed_filter(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _call('init','--root',d,'--approved')
            memory=root/'docs/context-keeper/memory-keeper.md'
            memory.write_text('# 记忆\n## 未完成事项\n- 已交付；状态：已完成；触发：验收；完成：报告；证据：输出\n- 整体核账；状态：进行中；触发：验收；完成：报告；证据：输出\n')
            _,out=_call('resume','--root',d,'--query','验收')
            self.assertNotIn('已交付',out); self.assertIn('整体核账',out)
            self.assertFalse(PROBE._invalid_pending(memory))

    def test_claude_unknown_project_is_excluded(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as h:
            (Path(h)/'other.jsonl').write_text(json.dumps({'type':'user','message':{'content':'隔离关键词'}}))
            _,out=_call('history-search','--root',d,'--agent','claude','--claude-history',h,'--query','隔离关键词')
            self.assertIn('未找到证据',out)

    def test_database_lag_and_include_current(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as h:
            root=Path(d).resolve(); home=Path(h); codex=home/'.codex'; sessions=codex/'sessions'; sessions.mkdir(parents=True)
            raw=sessions/'active.jsonl'
            raw.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in [
                {'type':'session_meta','payload':{'cwd':str(root)}},
                {'type':'response_item','payload':{'type':'message','role':'user','content':[{'text':'真实原文关键词'}]}}
            ]))
            with closing(sqlite3.connect(codex/'state_5.sqlite')) as conn:
                conn.execute('create table threads (id text, rollout_path text, cwd text)')
                conn.execute('insert into threads values (?,?,?)',('active',str(raw),str(root)))
                conn.commit()
            with closing(sqlite3.connect(codex/'thread_history_1.sqlite')) as conn:
                conn.execute('create table thread_items (thread_id text, rollout_ordinal integer, item_json text, created_at_ms integer)')
            with patch.object(Path,'home',return_value=home), patch.dict(PROBE.os.environ,{'CODEX_THREAD_ID':'active','CODEX_SESSION_ID':'active'}):
                _,out=_call('history-search','--root',str(root),'--agent','codex','--query','真实原文关键词')
                self.assertIn('未找到证据',out)
                _,out=_call('history-search','--root',str(root),'--agent','codex','--query','真实原文关键词','--include-current')
                self.assertIn('真实原文关键词',out)
                with closing(sqlite3.connect(codex/'thread_history_1.sqlite')) as conn:
                    conn.execute('insert into thread_items values (?,?,?,?)',('active',2,json.dumps({'type':'userMessage','content':[{'text':'数据库原文关键词'}]},ensure_ascii=False),1))
                    conn.commit()
                _,out=_call('history-search','--root',str(root),'--agent','codex','--query','数据库原文关键词','--include-current')
                self.assertIn('数据库原文关键词',out)

    def test_same_theme_duplicates_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_call('init','--root',d,'--approved');evo=root/'docs/context-keeper/evolution'
            (evo/'one.md').write_text(_experience('相同主题','CK-1'))
            (evo/'two.md').write_text(_experience('相同主题','CK-2'))
            _,out=_call('coverage','--root',d)
            self.assertIn('duplicate_themes=1',out)

    def test_save_rejects_missing_index_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); worklog=_write_valid_context(root)
            memory=root/'docs/context-keeper/memory-keeper.md'
            memory.write_text(memory.read_text().replace('- [进化经验索引](evolution/index.md)',''))
            rc,out=_save(root,worklog)
            self.assertEqual(rc,2); self.assertIn('缺少进化经验索引入口',out)

    def test_two_session_experience_and_delivery_loop(self):
        # Behavioral fixtures represent the two real failures, not product state.
        for title, fact, action in (
            ('耗时误归因', '历史记录包含生成后 11 分 59 秒和 9 分 16 秒，不能据此断言 manifest 是主因。', '引用已有计时；没有子阶段数据则保留未知。'),
            ('整组复盘遗漏', '单品归档完成不代表五套整体复盘已经交付。', '整组验收后检查整体核账与复盘证据。'),
        ):
            with self.subTest(title=title), tempfile.TemporaryDirectory() as d:
                root=Path(d);_call('init','--root',d,'--approved')
                store=root/'docs'/'context-keeper'; evo=store/'evolution'/f'{title}.md'
                _,name=_call('record-path','--root',d,'--kind','worklog','--title',title,'--session-id','first')
                log=root/name.strip()
                evo.write_text(_experience(title).replace('生成后整体处理较慢',fact).replace('先检查已有计时',action).replace('再次分析生成耗时',title))
                (store/'evolution/index.md').write_text(f'# 经验索引\n- [{title}]({title}.md)；触发词：{title}\n')
                log.write_text(log.read_text()+f'\n## 给用户看的增量认知\n本轮未发现需要额外提醒的盲点或隐患。\n\n## 自我进化\n- **已沉淀：** {action}[证据](../evolution/{title}.md)\n\n## 快速摘要（用于下次对话）\n**类型：** bugfix\n**完成：** 根据原文记录经验\n**下一步：** 下次核对适用范围\n**文件：** {title}.md\n')
                mem=store/'memory-keeper.md'
                mem.write_text(mem.read_text()+f'\n## 2026-09-16 - {title} `bugfix`\n- **任务：** {title}\n- **详见：** [日志](worklogs/{log.name})\n')
                rc,out=_call('save-report','--root',d,'--worklog',str(log),'--session-id','first')
                self.assertEqual(rc,0,out); self.assertIn('已沉淀',out)
                original=log.read_bytes()
                _,found=_call('resume','--root',d,'--query',title)
                self.assertIn(action,found)
                _,name2=_call('record-path','--root',d,'--kind','worklog','--title',title,'--session-id','second')
                log2=root/name2.strip(); self.assertNotEqual(log2,log)
                text=log.read_text().replace('session-id=first','session-id=second').replace('**已沉淀：**','**本次复用：**')
                log2.write_text(text);mem.write_text(mem.read_text()+f'\n- [后续日志](worklogs/{log2.name})\n')
                rc,out=_call('save-report','--root',d,'--worklog',str(log2),'--session-id','second')
                self.assertEqual(rc,0,out);self.assertIn('本次复用',out)
                self.assertEqual(log.read_bytes(),original)
                rc,out=_call('coverage','--root',d)
                self.assertEqual(rc,0,out)

    def test_promote_preserves_relative_evidence_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as u:
            root=Path(d);_call('init','--root',d,'--approved');store=root/'docs'/'context-keeper'
            source=store/'evolution/经验.md'; evidence=store/'plans/原文.md';evidence.write_text('用户原话')
            source.write_text(_experience().replace('worklogs/2026-08-17-test.md','[原文](../plans/原文.md)'))
            args=('promote-evolution','--root',d,'--source',str(source),'--approved','--user-evolution-dir',u)
            self.assertEqual(_call(*args)[0],0)
            self.assertEqual(_call(*args)[0],0)
            self.assertIn(evidence.resolve(),PROBE._markdown_links(Path(u)/'经验.md'))
            _,out=_call('search','--root',d,'--query','生成耗时','--user-evolution-dir',u)
            self.assertIn('命中 1 条',out)

    def test_kind_budget_includes_evolution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_call('init','--root',d,'--approved');store=root/'docs'/'context-keeper'
            (store/'evolution/经验.md').write_text(_experience().replace('再次分析生成耗时','公共关键词'))
            memory=store/'memory-keeper.md'
            memory.write_text(memory.read_text()+'\n'+'\n'.join(f'## 2026-09-16 - 公共关键词{i} `research`\n- **任务：** 公共关键词{i}' for i in range(5)))
            _,out=_call('resume','--root',d,'--query','公共关键词','--kind','research')
            self.assertEqual(out.count('- 2026-09-16'),3)
            self.assertIn('耗时分析',out)

    def test_migration_does_not_redirect_historical_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_call('init','--root',d,'--approved')
            (root/'evidence.md').write_text('原始事实')
            old=root/'docs/context-keeper/worklogs/2026-09-16-历史.md'
            old.write_text('[证据](../../evidence.md)')
            original=old.read_bytes()
            rc,out=_call('init','--root',d,'--store-dir','notes/deeper/context','--migrate','--approved')
            self.assertEqual(rc,2)
            self.assertIn('证据链接',out)
            self.assertEqual(old.read_bytes(),original)
            self.assertFalse((root/'notes/deeper/context').exists())
