"""Synthetic failure controls retained independently of historical CLI orchestration."""
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent/'evaluations'))
from evaluation_support import prepare_reference_projects,activate_nodes,cleanup_owned,metadata

SLOTS=[('middle','resume',rep) for rep in [1,2,3,4]]
VARIANTS={1:'old',2:'new',3:'old',4:'new'}


class ReferenceGuidanceWrapperTests(unittest.TestCase):
    def preparation(self,root,different=False):
        for name,text in [('old','old search'),('new','new search')]:
            folder=root/name;folder.mkdir();(folder/'search.md').write_text(text);(folder/'resume.md').write_text('same resume')
        out=root/'run'
        def prepare(target):
            target.mkdir()
            for c,m,r in SLOTS:
                p=target/f'{c}-{m}-{r}'/'project'
                refs=p/'.agents/skills/context-keeper/references';refs.mkdir(parents=True)
                (refs/'search.md').write_text('placeholder')
                (p/'AGENTS.md').write_text('same budget')
                (p/'fact.txt').write_text('different' if different and r==4 else 'same fact')
        return out,prepare

    def test_symlink_roots_and_members_rejected_before_digest(self):
        for mode in ['root','member']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);out,prepare=self.preparation(root)
                target=root/'synthetic-private';target.mkdir();(target/'private.md').write_text('SYNTHETIC PRIVATE')
                if mode=='root':
                    shutil.rmtree(root/'old');(root/'old').symlink_to(target,target_is_directory=True)
                else:(root/'old/link.md').symlink_to(target/'private.md')
                with patch('evaluation_support.digest',side_effect=AssertionError('Must not read content before symlink rejection')) as read:
                    with self.assertRaisesRegex(RuntimeError,'snapshot is symlinked'):
                        prepare_reference_projects(out,old_refs=root/'old',new_refs=root/'new',slots=SLOTS,variants=VARIANTS,
                                                   expected_model=('expected','medium'),actual_model=('expected','medium'),prepare_public=prepare)
                    read.assert_not_called()
                self.assertFalse(out.exists())
                self.assertFalse(any(root.rglob('auth.json')))

    def test_model_drift_fails_before_any_auth_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,prepare=self.preparation(root)
            with self.assertRaisesRegex(RuntimeError,'model/effort drift'):
                prepare_reference_projects(out,old_refs=root/'old',new_refs=root/'new',slots=SLOTS,variants=VARIANTS,
                                           expected_model=('expected','medium'),actual_model=('drift','medium'),prepare_public=prepare)
            self.assertFalse(out.exists())
            self.assertFalse(any(root.rglob('auth.json')))

    def test_nonreference_mismatch_fails_before_any_auth_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out,prepare=self.preparation(root,different=True)
            with self.assertRaisesRegex(RuntimeError,'Non-reference project bytes differ'):
                prepare_reference_projects(out,old_refs=root/'old',new_refs=root/'new',slots=SLOTS,variants=VARIANTS,
                                           expected_model=('expected','medium'),actual_model=('expected','medium'),prepare_public=prepare)
            self.assertFalse(any(root.rglob('auth.json')))

    def test_partial_activation_rolls_back_only_new_link_and_keeps_preexisting(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'run';out.mkdir()
            original=root/'synthetic-auth';original.write_text('SYNTHETIC ONLY');original.chmod(0o600)
            foreign=root/'foreign';foreign.write_text('SYNTHETIC FOREIGN')
            folders=[out/f'{c}-{m}-{r}' for c,m,r in SLOTS]
            existing=folders[1]/'codex-home/auth.json';existing.parent.mkdir(parents=True);existing.symlink_to(foreign)
            existing_before=metadata(existing);original_before=metadata(original)
            def create(folder,created):
                if folder.name.endswith('-2'):raise RuntimeError('injected second-node failure')
                link=folder/'codex-home/auth.json';link.parent.mkdir(parents=True);link.symlink_to(original);created.append(str(link))
            with self.assertRaisesRegex(RuntimeError,'injected second-node failure'):activate_nodes(out,original,folders,create)
            self.assertFalse((folders[0]/'codex-home/auth.json').is_symlink())
            self.assertTrue(existing.is_symlink());self.assertEqual(metadata(existing),existing_before)
            self.assertEqual(os.readlink(existing),str(foreign));self.assertEqual(metadata(original),original_before)
            self.assertEqual(json.loads((out/'auth-link-cleanup.json').read_text())['removed'],1)

    def test_cleanup_refuses_owned_path_with_changed_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'run';out.mkdir()
            original=root/'original';original.write_text('SYNTHETIC ORIGINAL')
            foreign=root/'foreign';foreign.write_text('SYNTHETIC FOREIGN')
            folders=[out/f'{c}-{m}-{r}' for c,m,r in SLOTS]
            link=folders[0]/'codex-home/auth.json';link.parent.mkdir(parents=True);link.symlink_to(foreign)
            before=metadata(link)
            cleanup_owned(out,original,[str(link)],folders=folders)
            self.assertTrue(link.is_symlink());self.assertEqual(metadata(link),before)
            self.assertEqual(json.loads((out/'auth-link-cleanup.json').read_text())['removed'],0)
