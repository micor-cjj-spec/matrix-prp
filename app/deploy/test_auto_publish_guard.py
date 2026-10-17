"""Evaluate the actual production-job guard against trusted and untrusted events."""
import ast
import copy
from pathlib import Path
import unittest
import yaml


def expression_value(node, context):
    if isinstance(node, ast.Expression):
        return expression_value(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return context.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = expression_value(node.value, context)
        return parent.get(node.attr) if isinstance(parent, dict) else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'always' and not node.args and not node.keywords:
        return True
    if isinstance(node, ast.BoolOp):
        values = (bool(expression_value(value, context)) for value in node.values)
        if isinstance(node.op, ast.And): return all(values)
        if isinstance(node.op, ast.Or): return any(values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        return expression_value(node.left, context) == expression_value(node.comparators[0], context)
    raise ValueError('Unsupported workflow guard expression; review required')


class AutoPublishGuardTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        self.workflow = yaml.safe_load((root/'.github/workflows/deploy-prp.yml').read_text())
        self.publish = self.workflow['jobs']['publish']
        self.expression = ast.parse('(' + self.publish['if'].replace('&&', ' and ').replace('||', ' or ').strip() + ')', mode='eval')
        self.context = {'github': {'ref': 'refs/heads/main', 'event_name': 'workflow_run',
            'repository': 'owner/repository', 'event': {'workflow_run': {
                'conclusion': 'success', 'event': 'push', 'head_branch': 'main',
                'head_repository': {'full_name': 'owner/repository'}}}},
            'needs': {'build': {'result': 'success'},'release_control': {'result':'success','outputs':{'publish_allowed':'true'}}}, 'inputs': {}}

    def allowed(self, context):
        return bool(expression_value(self.expression, context))

    def test_only_successful_same_repository_main_push_ci_can_auto_publish(self):
        self.assertTrue(self.allowed(self.context))
        variants = [('conclusion', 'failure'), ('conclusion', 'cancelled'),
                    ('conclusion', None), ('event', 'pull_request'), ('event', 'workflow_dispatch'),
                    ('head_branch', 'feature'), ('head_repository', {'full_name': 'attacker/fork'}),
                    ('head_repository', None)]
        for key, value in variants:
            context = copy.deepcopy(self.context)
            context['github']['event']['workflow_run'][key] = value
            with self.subTest(key=key, value=value): self.assertFalse(self.allowed(context))
        for result in ['failure', 'cancelled', 'skipped', None]:
            context = copy.deepcopy(self.context); context['needs']['build']['result'] = result
            self.assertFalse(self.allowed(context))
        context = copy.deepcopy(self.context); context['github']['ref'] = 'refs/heads/feature'
        self.assertFalse(self.allowed(context))

    def test_manual_controls_keep_build_requirements_and_do_not_publish_build_only(self):
        for action, result, expected in [('deploy','success',True), ('deploy','failure',False),
                ('promote','skipped',True), ('check','skipped',True), ('rollback','skipped',True),
                ('promote','failure',False), ('build','success',False)]:
            context = copy.deepcopy(self.context); context['github']['event_name'] = 'workflow_dispatch'
            context['inputs']['action'] = action; context['needs']['build']['result'] = result
            with self.subTest(action=action, result=result): self.assertEqual(self.allowed(context), expected)
        context['github']['event_name'] = 'pull_request'
        self.assertFalse(self.allowed(context))

    def test_publication_hold_blocks_auto_and_all_mutating_manual_actions(self):
        context=copy.deepcopy(self.context)
        context['needs']['release_control']['outputs']['publish_allowed']='false'
        self.assertFalse(self.allowed(context))
        for action in ('deploy','promote','rollback','build','unknown'):
            c=copy.deepcopy(context);c['github']['event_name']='workflow_dispatch'
            c['inputs']['action']=action;c['needs']['build']['result']='success' if action in ('deploy','build') else 'skipped'
            with self.subTest(action=action):self.assertFalse(self.allowed(c))
        c=copy.deepcopy(context);c['github']['event_name']='workflow_dispatch'
        c['inputs']['action']='check';c['needs']['build']['result']='skipped'
        self.assertTrue(self.allowed(c))
        for state in ('failure','cancelled','skipped',None):
            c['needs']['release_control']['result']=state
            with self.subTest(state=state):self.assertFalse(self.allowed(c))

    def test_publish_still_requires_protected_environment_and_all_preoperation_gates(self):
        self.assertEqual(self.publish['environment']['name'], 'production')
        self.assertEqual(self.workflow['concurrency'], {'group':'prp-production', 'cancel-in-progress':False})
        steps = self.publish['steps']; names = [s.get('name') for s in steps]
        operation = next(i for i,s in enumerate(steps) if s.get('id') == 'production_operation')
        for gate in ['Reject stale main revision', 'Validate artifact matches the tested main commit',
                     'Verify restricted SSH boundary before production operation',
                     'Verify approved production controller before deploying']:
            self.assertLess(names.index(gate), operation)
        self.assertEqual(self.publish['needs'], ['build','release_control'])


if __name__ == '__main__': unittest.main()
