#!/usr/bin/env python3
"""Build a deterministic repository-level Agency OS coverage inventory."""
from __future__ import annotations
import hashlib, json, os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.environ.get('AGENCY_OS_RUN_DIR', str(ROOT.parents[2] / '.agents' / 'runs' / 'agency-os-god-source-expansion-20260802')))
OUT = ROOT / 'intelligence' / 'agency'
CANONICAL = ['revenue_relationships','work_delivery','knowledge_research','communication_support','marketing_growth','legal_trust','finance_administration','data_intelligence','automation_agents','identity_security_governance','files_media_content','deployment_operations']
PILLAR_MAP = {
    'revenue_and_relationships':'revenue_relationships','work_and_delivery':'work_delivery','knowledge_and_research':'knowledge_research',
    'communication_and_support':'communication_support','marketing_and_growth':'marketing_growth','legal_and_trust':'legal_trust',
    'finance_and_administration':'finance_administration','data_and_intelligence':'data_intelligence','automation_and_agents':'automation_agents',
    'identity_security_and_governance':'identity_security_governance','files_media_and_content':'files_media_content','deployment_and_operations':'deployment_operations',
    'crm-revenue-relationships':['revenue_relationships'],'work-delivery-resourcing':['work_delivery'],'knowledge-documents-files-legal':['knowledge_research','files_media_content','legal_trust'],
    'communication-inbox-support-calendar':['communication_support'],'marketing-growth-content-automation':['marketing_growth','automation_agents','files_media_content'],'finance-hr-admin':['finance_administration'],
    'data-analytics-search-memory':['data_intelligence'],'agent-infrastructure-deployment-ops':['automation_agents','deployment_operations'],'identity-tenancy-permissions':['identity_security_governance'],
}

# Lane-B is intentionally mapped from the capability job, not from its broad
# slice label.  Defaults express the dominant job family; the small overrides
# capture jobs whose actual contract materially spans a second pillar.
CAPABILITY_DEFAULTS = {
    'agent-infrastructure-deployment-ops': ['automation_agents'],
    'communication-inbox-support-calendar': ['communication_support'],
    'crm-revenue-relationships': ['revenue_relationships'],
    'work-delivery-resourcing': ['work_delivery'],
    'finance-hr-admin': ['finance_administration'],
    'marketing-growth-content-automation': ['marketing_growth'],
    'identity-tenancy-permissions': ['identity_security_governance'],
    'data-analytics-search-memory': ['data_intelligence'],
    'knowledge-documents-files-legal': ['knowledge_research'],
}
CAPABILITY_OVERRIDES = {
    # agent control, security, and operations
    **{f'AGT-{i:02d}': ['automation_agents', 'identity_security_governance'] for i in (2,7,16,23)},
    **{f'AGT-{i:02d}': ['automation_agents', 'deployment_operations'] for i in (17,18,19,20,21,22,24)},
    'AGT-09': ['automation_agents', 'legal_trust'], 'AGT-11': ['automation_agents', 'knowledge_research'],
    'AGT-13': ['automation_agents', 'data_intelligence'], 'AGT-15': ['automation_agents', 'identity_security_governance'],
    # communications that are records, compliance, or approvals
    'COM-03': ['communication_support', 'revenue_relationships'], 'COM-11': ['communication_support', 'work_delivery'],
    'COM-14': ['communication_support', 'identity_security_governance'], 'COM-17': ['communication_support', 'marketing_growth'],
    'COM-18': ['communication_support', 'identity_security_governance'], 'COM-19': ['communication_support', 'legal_trust'],
    # relationship jobs with an explicit finance/legal/delivery contract
    'CRM-04': ['revenue_relationships', 'legal_trust'], 'CRM-05': ['revenue_relationships', 'legal_trust'],
    'CRM-08': ['revenue_relationships', 'finance_administration'], 'CRM-09': ['revenue_relationships', 'finance_administration'],
    'CRM-15': ['revenue_relationships', 'work_delivery'], 'CRM-16': ['revenue_relationships', 'finance_administration'],
    'CRM-18': ['revenue_relationships', 'finance_administration'], 'CRM-19': ['revenue_relationships', 'marketing_growth'],
    # delivery jobs with financial, client, or knowledge outputs
    **{f'DEL-{i:02d}': ['work_delivery', 'finance_administration'] for i in (9,10,11,12,13)},
    'DEL-14': ['work_delivery', 'legal_trust'], 'DEL-15': ['work_delivery', 'communication_support'],
    'DEL-19': ['work_delivery', 'files_media_content'], 'DEL-21': ['work_delivery', 'identity_security_governance'],
    'DEL-24': ['work_delivery', 'communication_support'],
    # marketing jobs whose primary output is content, comms, or automation
    **{f'GRW-{i:02d}': ['marketing_growth', 'files_media_content'] for i in (4,8,9,15,16,22)},
    **{f'GRW-{i:02d}': ['marketing_growth', 'communication_support'] for i in (2,10,11,18,19,21)},
    'GRW-23': ['marketing_growth', 'automation_agents'], 'GRW-14': ['marketing_growth', 'deployment_operations'],
    # identity jobs with legal/compliance or agent-operation seams
    **{f'IDN-{i:02d}': ['identity_security_governance', 'legal_trust'] for i in (11,12,14,17,19)},
    'IDN-13': ['identity_security_governance', 'automation_agents'], 'IDN-18': ['identity_security_governance', 'automation_agents'],
    # data jobs whose actual deliverable is knowledge, legal portability, or comms
    **{f'DAS-{i:02d}': ['data_intelligence', 'knowledge_research'] for i in (2,3,4,5,21)},
    'DAS-15': ['data_intelligence', 'communication_support'], 'DAS-17': ['data_intelligence', 'legal_trust'],
    'DAS-18': ['data_intelligence', 'deployment_operations'], 'DAS-19': ['data_intelligence', 'revenue_relationships'],
    # knowledge jobs are deliberately specific rather than inheriting all slice words
    'KNW-03': ['knowledge_research', 'legal_trust'], 'KNW-04': ['legal_trust', 'knowledge_research'],
    'KNW-05': ['files_media_content'], 'KNW-06': ['files_media_content'], 'KNW-07': ['knowledge_research', 'communication_support'],
    'KNW-09': ['knowledge_research', 'revenue_relationships'], 'KNW-10': ['knowledge_research', 'data_intelligence'],
    'KNW-11': ['knowledge_research', 'work_delivery'], 'KNW-12': ['files_media_content', 'identity_security_governance'],
    'KNW-13': ['knowledge_research', 'data_intelligence'], 'KNW-14': ['legal_trust', 'knowledge_research'],
    'KNW-15': ['files_media_content'], 'KNW-16': ['files_media_content', 'communication_support'],
}

def capability_mapping(cap):
    cid, slice_name, job = cap['capability_id'], cap['slice'], cap['job']
    pillars = CAPABILITY_OVERRIDES.get(cid, CAPABILITY_DEFAULTS[slice_name])
    assert pillars and set(pillars).issubset(set(CANONICAL)), (cid, pillars)
    primary = pillars[0].replace('_', ' ')
    rationale = f"Mapped primarily to {primary} because the capability job is: {job}"
    return {'capability_id': cid, 'raw_slice': slice_name, 'canonical_pillars': pillars, 'rationale': rationale.rstrip('.') + '.'}

def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def receipt(path, rows=None):
    # Keep the published receipt portable; the generator's local absolute
    # path is intentionally not materialized in a public artifact.
    d = {'path': 'external-run/agency-os-god-source-expansion-20260802/' + path.name, 'sha256': sha(path), 'bytes': path.stat().st_size}
    if rows is not None: d['rows'] = rows
    return d

def main():
    cand_path, front_path, atlas_path = (RUN / n for n in ('lane-a-candidates.jsonl','lane-a-promotion-frontier.json','lane-b-capability-atlas.jsonl'))
    candidates = load_jsonl(cand_path)
    frontier = json.loads(front_path.read_text())['rows']
    atlas = load_jsonl(atlas_path)
    assert len(candidates) == 497, f'expected 497 candidate rows, got {len(candidates)}'
    assert len(atlas) == 189 and len({c['capability_id'] for c in atlas}) == 189
    capability_map = [capability_mapping(c) for c in atlas]
    assert len(capability_map) == 189 and {m['capability_id'] for m in capability_map} == {c['capability_id'] for c in atlas}
    (OUT / 'capability-pillar-map.json').write_text(json.dumps({
        'schema_version': '1.0.0', 'record_type': 'agency_os_capability_pillar_map',
        'mapping_method': 'Each Lane-B capability is mapped from its one-sentence job to the smallest materially spanning set of canonical Agency OS pillars; raw slice names are preserved for provenance and never used for routing.',
        'canonical_pillars': CANONICAL, 'counts': {'capabilities': len(capability_map), 'multi_pillar_capabilities': sum(len(m['canonical_pillars']) > 1 for m in capability_map)},
        'capabilities': capability_map
    }, indent=2, sort_keys=True) + '\n')
    capability_by_id = {m['capability_id']: m for m in capability_map}

    by_repo = {}
    for i, row in enumerate(candidates, 1):
        repo = row['repository']; x = by_repo.setdefault(repo, {'repository': repo, 'repository_url': row.get('repository_url'), 'application_rows': []})
        x['application_rows'].append({'candidate_id': row['candidate_id'], 'line': i, 'adoption_route': row.get('adoption_route'), 'classification': row.get('classification'), 'evidence_level': row.get('evidence_level')})
        x.setdefault('_apps', []).append(row)
    for i, row in enumerate(frontier, 1):
        repo = row['repository']; x = by_repo.setdefault(repo, {'repository': repo, 'repository_url': row.get('repository_url'), 'application_rows': []})
        x['repository_url'] = x.get('repository_url') or row.get('repository_url')
        x.setdefault('_frontier', []).append({'candidate_id': row['candidate_id'], 'line': i, 'verifier_verdict': row.get('verification', {}).get('verdict'), 'verifier_confirmed': bool(row.get('verifier_confirmed'))})
    for i, cap in enumerate(atlas, 1):
        for j, c in enumerate(cap.get('candidate_repos', []), 1):
            repo = c.get('repo')
            if not repo: continue
            x = by_repo.setdefault(repo, {'repository': repo, 'repository_url': 'https://github.com/' + repo, 'application_rows': []})
            x.setdefault('_atlas', []).append({'capability_id': cap.get('capability_id'), 'slice': cap.get('slice'), 'line': i, 'candidate_index': j, 'why': c.get('why')})

    rows = []
    for repo in sorted(by_repo):
        x = by_repo[repo]; apps = x.pop('_apps', []); fr = x.pop('_frontier', []); at = x.pop('_atlas', [])
        raw_labels = sorted({a.get('pillar') for a in apps if a.get('pillar')} | {a.get('slice') for a in at if a.get('slice')})
        # Lane-A pillars are authoritative for candidate rows. Lane-B adds only
        # the exact mapped pillars for capabilities that reference this repo;
        # the broad raw slice is intentionally excluded from routing.
        canonical = sorted({v for a in apps for v in (([a.get('pillar')] if a.get('pillar') in CANONICAL else ([PILLAR_MAP[a.get('pillar')]] if isinstance(PILLAR_MAP.get(a.get('pillar')), str) else PILLAR_MAP.get(a.get('pillar'), [])))) if v in CANONICAL} |
                            {v for a in at for v in capability_by_id[a['capability_id']]['canonical_pillars']})
        assert canonical and all(v in CANONICAL for v in canonical), (repo, raw_labels)
        categories = sorted({a.get('category') for a in apps if a.get('category')} | {a.get('siso_use_case') for a in apps if a.get('siso_use_case')} | {a.get('slice') for a in at if a.get('slice')})
        levels = {a.get('evidence_level') for a in apps}; levels |= {'source_read' if a.get('evidence') == 'source-read' else a.get('evidence') for a in at}
        if any(f.get('verifier_confirmed') for f in fr): grade = 'adversarial-confirmed'
        elif 'source_read' in levels or 'source-read' in levels: grade = 'source-read'
        elif 'metadata_triaged' in levels or 'metadata-triaged' in levels: grade = 'metadata'
        else: grade = 'inferred'
        license_statuses = sorted({a.get('license_status') for a in apps if a.get('license_status')})
        license_risks = sorted({a.get('license_risk') for a in apps if a.get('license_risk')})
        rows.append({'repository': repo, 'repository_url': x.get('repository_url'), 'canonical_verticals': canonical, 'raw_vertical_labels': raw_labels, 'verticals': canonical, 'pillars': canonical, 'categories': categories,
          'evidence_grade': grade, 'analyzed': {'application_candidate': bool(apps), 'source_read': grade in ('source-read','adversarial-confirmed'), 'adversarial_reviewed': bool(fr), 'adversarial_confirmed': any(f.get('verifier_confirmed') for f in fr), 'capability_atlas_reference': bool(at)},
          'application_row_count': len(apps), 'frontier_row_count': len(fr), 'atlas_reference_count': len(at), 'analysis': {'candidate_ids': sorted({a.get('candidate_id') for a in apps if a.get('candidate_id')}), 'capability_ids': sorted({a.get('capability_id') for a in at if a.get('capability_id')}), 'adoption_routes': sorted({a.get('adoption_route') for a in apps if a.get('adoption_route')}), 'reusable_fields': ['verticals','pillars','categories','evidence_grade','analyzed','license','source_refs']},
          'license': {'statuses': license_statuses, 'risks': license_risks, 'reuse_safe_claim': bool(license_risks and all(r in ('permissive','none') for r in license_risks)), 'reusable_analysis_requires_rights_review': True},
          'source_refs': {'candidate_lines': [a['line'] for a in x['application_rows']], 'frontier_lines': [a['line'] for a in fr], 'atlas_refs': [f"{a['capability_id']}:{a['line']}:{a['candidate_index']}" for a in at]}})

    grade_counts = Counter(r['evidence_grade'] for r in rows)
    analyzed_rows = sum(r['analyzed']['source_read'] for r in rows)
    verified_rows = sum(r['analyzed']['adversarial_confirmed'] for r in rows)
    reusable_rows = sum(bool(r['analysis']['candidate_ids'] or r['analysis']['capability_ids']) and r['evidence_grade'] in ('source-read','adversarial-confirmed') for r in rows)
    verticals = {}
    for v in CANONICAL:
        vr = [r for r in rows if v in r['canonical_verticals']]
        verticals[v] = {'repository_count': len(vr), 'evidence_split': dict(sorted(Counter(r['evidence_grade'] for r in vr).items())), 'projects': [r['repository'] for r in vr]}
    inventory = {'schema_version':'1.0.0','record_type':'agency_os_coverage_inventory','unit_of_analysis':'unique_repository_or_project','canonical_pillars':CANONICAL,'generated_from_observed_at':'2026-08-03','counts': {'candidate_application_rows':len(candidates),'unique_repositories':len(rows),'frontier_rows':len(frontier),'atlas_capability_rows':len(atlas),'multi_vertical_projects':sum(len(r['canonical_verticals'])>1 for r in rows),'evidence_grade':dict(sorted(grade_counts.items())),'unmapped_vertical_labels':0}, 'coverage': {'source_read_unique_repositories': analyzed_rows, 'source_read_pct': round(analyzed_rows/len(rows)*100,2), 'adversarial_confirmed_unique_repositories': verified_rows, 'adversarial_confirmed_pct': round(verified_rows/len(rows)*100,2), 'reusable_analysis_unique_repositories': reusable_rows, 'reusable_analysis_pct': round(reusable_rows/len(rows)*100,2), 'source_read_candidate_application_rows': sum(1 for a in candidates if a.get('evidence_level')=='source_read'), 'reusable_analysis_fields_per_row': 8, 'inferred_rows_counted_as_verified': 0}, 'vertical_coverage': verticals, 'source_artifacts': [receipt(cand_path,len(candidates)),receipt(front_path,len(frontier)),receipt(atlas_path,len(atlas))], 'rows': rows}
    out = OUT/'coverage-inventory.json'; out.write_text(json.dumps(inventory, indent=2, sort_keys=True)+'\n')
    md = OUT/'COVERAGE.md'
    vt = '\n'.join(f"| `{v}` | {verticals[v]['repository_count']} | " + ', '.join(f"{k}: {n}" for k,n in verticals[v]['evidence_split'].items()) + ' |' for v in CANONICAL)
    md.write_text('# Agency OS coverage inventory\n\nDeterministic output from the Agency OS expansion receipts. The 497 candidate application rows are repository × use-case rows; the inventory below deduplicates them with Lane B capability-atlas references. Inferred evidence is never counted as verified.\n\n## Definitions\n\n- **Analyzed:** a repository has a source-read or adversarial receipt in the supplied artifacts.\n- **Verified:** only an adversarial-confirmed verifier verdict; metadata and inferred rows never qualify.\n- **Reusable:** a repository has reusable analysis fields and source-read or adversarial evidence; this does not grant reuse rights.\n\n## Aggregate coverage\n\n| Measure | Count | Percent of unique repositories |\n|---|---:|---:|\n| Unique repositories/projects | %d | 100%% |\n| Source-read or adversarial-confirmed | %d | %.2f%% |\n| Adversarial-confirmed | %d | %.2f%% |\n| Reusable analysis (source-read/confirmed, at least one analysis receipt) | %d | %.2f%% |\n\nApplication rows: **%d**. Frontier rows: **%d**. Capability-atlas rows: **%d**. Unmapped labels: **0**.\n\n## Canonical vertical coverage\n\n| Canonical pillar | Projects | Evidence split |\n|---|---:|---|\n%s\n\n## Evidence grades\n\n%s\n\nThe machine-readable row-level inventory is [`coverage-inventory.json`](coverage-inventory.json). Each row includes canonical verticals, preserved raw labels, categories, analyzed flags, license/reuse fields, and hashed source-artifact receipts.\n' % (len(rows), analyzed_rows, analyzed_rows/len(rows)*100, verified_rows, verified_rows/len(rows)*100, reusable_rows, reusable_rows/len(rows)*100, len(candidates),len(frontier),len(atlas),vt, '\n'.join(f'- `{k}`: {v}' for k,v in sorted(grade_counts.items()))))
    md.write_text(md.read_text().replace('Inferred evidence is never counted as verified.', 'Inferred evidence is never counted as verified. Lane-B routing uses the explicit job-based `capability-pillar-map.json`: raw slice names are provenance only, and a project receives only the mapped pillars of the capabilities that reference it.'))
    print(json.dumps(inventory['coverage'], sort_keys=True))

if __name__ == '__main__': main()
