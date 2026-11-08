"""Reusable evaluation preparation and safety checks with explicit synthetic inputs.

This module has no model client, personal HOME/config lookup, authentication default,
bootstrap default, or historical evidence directory. It never reads auth contents.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

from evaluation_contract import CURRENT_BUDGET, budget_materials
from memory_baseline import build, digest


def metadata(path):
    s=path.lstat()
    return {'inode':s.st_ino,'uid':s.st_uid,'mode':s.st_mode,'size':s.st_size,'mtime_ns':s.st_mtime_ns}


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def prepare_matrix(out, *, repo, schedule, header, prompts, model, effort, cli_version,
                   effective_budgets=None):
    """Materialize fixtures, instructions and scoring; never discovers a live client."""
    if not isinstance(model,str) or not model.strip():raise ValueError('Explicit model label required')
    out.mkdir(parents=True,exist_ok=False)
    budgets=effective_budgets or {}
    materials={f'{case}-{mode}-{rep}':budget_materials(header,budgets.get(f'{case}-{mode}-{rep}',CURRENT_BUDGET))
               for case,mode,rep in schedule}
    scoring={'axes':{'budget':'Apply session_budgets effective_budget and budget_instructions'},'session_budgets':materials}
    protocol={'schedule':schedule,'prompts':prompts,'requested_model':model,'requested_effort':effort,
              'cli':cli_version,'session_budgets':materials,'scoring':scoring,
              'scope':'synthetic preparation only; no auth or model execution'}
    fixtures={}
    for case,mode,rep in schedule:
        key=f'{case}-{mode}-{rep}';root=out/key/'project';build(root,case)
        (root/'docs/context-keeper/plans').mkdir(exist_ok=True)
        skill=root/'.agents/skills/context-keeper';skill.mkdir(parents=True)
        shutil.copy2(repo/'SKILL.md',skill/'SKILL.md')
        shutil.copytree(repo/'references',skill/'references')
        shutil.copytree(repo/'scripts',skill/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        (root/'AGENTS.md').write_text(materials[key]['project_agents'])
        (root/'empty-user-evolution').mkdir()
        fixtures[key]=digest(root)
    for case in {row[0] for row in schedule}:
        variants=[{p:h for p,h in v.items() if p!='AGENTS.md'} for k,v in fixtures.items() if k.startswith(case+'-')]
        if any(v!=variants[0] for v in variants):raise RuntimeError('Non-budget fixture mismatch: '+case)
    dump(out/'protocol.json',protocol);dump(out/'scoring.json',scoring);dump(out/'fixtures-before.json',fixtures)
    return protocol


def protect_default_user_experience(profile, *, user_home):
    root=Path(user_home)/'.context-keeper/evolution'
    added=sorted({str(root.absolute()),str(root.resolve())})
    profile+='\n'+''.join('(deny file-read* (subpath '+json.dumps(p)+'))\n' for p in added)
    roots=[]
    for line in profile.splitlines():
        match=re.fullmatch(r'\(deny file-read\* \(subpath (".*")\)\)',line)
        if match:roots.append(json.loads(match.group(1)))
    return profile,{'protected_roots':sorted(set(roots)),
                    'additional_default_user_experience_roots':added,
                    'profile_sha256':hashlib.sha256(profile.encode()).hexdigest(),
                    'scope':'explicit named roots, not all private paths','template_unchanged':True}


def planned_runtime_profile(folder, *, template, template_root, user_home):
    profile=Path(template).read_text().replace(str(template_root),str(folder))
    return protect_default_user_experience(profile,user_home=user_home)


def prepare_runtime_node(folder,created, *, bootstrap, original, template, template_root, user_home):
    """Prepare an explicitly supplied node; callers must supply a synthetic auth target in tests."""
    home=folder/'codex-home';home.mkdir(mode=0o700)
    for name in ['installation_id','.sandbox_migration']:shutil.copy2(bootstrap/name,home/name)
    shutil.copytree(bootstrap/'skills',home/'skills',symlinks=True)
    for path in [home/'tmp',home/'.tmp',folder/'runtime/sqlite',folder/'runtime/logs',folder/'runtime/tmp',folder/'output']:
        path.mkdir(parents=True,exist_ok=True)
    link=home/'auth.json'
    if link.exists() or link.is_symlink():raise RuntimeError('Refuse pre-existing auth entry')
    link.symlink_to(original);created.append(str(link))
    profile,protection=planned_runtime_profile(folder,template=template,template_root=template_root,user_home=user_home)
    (folder/'readonly-auth.sb').write_text(profile)
    dump(folder/'runtime-before.json',{'auth_link_meta':metadata(link),'auth_readlink':os.readlink(link),
                                     'profile_sha256':hashlib.sha256(profile.encode()).hexdigest(),'memory_protection':protection})
    return protection


def prepare_reference_projects(out, *, old_refs, new_refs, slots, variants,
                               expected_model, actual_model, prepare_public):
    """Public validation stage has no auth argument or live-runtime dependency."""
    if expected_model!=actual_model:raise RuntimeError('Configured model/effort drift; auth preparation has not started')
    # Keep lexical roots: resolving first would hide a root symlink.
    for root in [old_refs,new_refs]:
        if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
            raise RuntimeError('Reference snapshot is symlinked')
    old,new=digest(old_refs),digest(new_refs)
    changed={n for n in old.keys()|new.keys() if old.get(n)!=new.get(n)}
    if not changed or not changed<={'search.md','resume.md'}:raise RuntimeError('Undeclared reference differences')
    prepare_public(out)
    hashes={}
    for case,mode,rep in slots:
        key=f'{case}-{mode}-{rep}';root=out/key/'project';dest=root/'.agents/skills/context-keeper/references'
        shutil.rmtree(dest);shutil.copytree(old_refs if variants[rep]=='old' else new_refs,dest);hashes[key]=digest(root)
    prefix='.agents/skills/context-keeper/references/'
    nonrefs=[{k:v for k,v in h.items() if not k.startswith(prefix)} for h in hashes.values()]
    if not all(h==nonrefs[0] for h in nonrefs):raise RuntimeError('Non-reference project bytes differ; auth preparation has not started')
    dump(out/'fixtures-before.json',hashes)
    return hashes


def cleanup_owned(out,original,owned, *, folders):
    expected={p/'codex-home/auth.json' for p in folders};before=metadata(original) if owned else None;rows=[]
    for value in owned:
        link=Path(value);row={'path':str(link),'removed':False}
        if (link in expected and link.is_symlink() and link.lstat().st_uid==os.getuid()
                and os.readlink(link)==str(original) and link.resolve()==original.resolve()):
            row['link_before']=metadata(link);link.unlink();row['removed']=True
        rows.append(row)
    after=metadata(original) if owned else None
    result={'original_before':before,'original_after':after,'original_metadata_unchanged':before==after,
            'links':rows,'removed':sum(r['removed'] for r in rows)}
    dump(out/'auth-link-cleanup.json',result)
    return result


def activate_nodes(out,original,folders,create_node):
    """Rollback only links explicitly created in this activation attempt."""
    s=original.lstat()
    if s.st_uid!=os.getuid() or not stat.S_ISREG(s.st_mode):raise RuntimeError('Unverified auth owner/type')
    before=metadata(original);created=[]
    try:
        for folder in folders:create_node(folder,created)
        if metadata(original)!=before:raise RuntimeError('Original auth metadata drift')
    except BaseException:
        cleanup_owned(out,original,created,folders=folders)
        raise
    return created
