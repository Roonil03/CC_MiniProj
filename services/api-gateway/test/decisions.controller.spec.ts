import { DecisionsController } from '../src/decisions/decisions.controller';
import { UpstreamService } from '../src/upstream/upstream.service';
import assert = require('node:assert/strict');
import { describe, it } from 'node:test';

describe('DecisionsController safety boundary', () => {
  it('sends approval requests only to the safety service', async () => {
    const calls: unknown[][] = [];
    const request = async (...args: unknown[]) => { calls.push(args); return { approved: true }; };
    const settled = async (upstream: string, path: string) => {
      calls.push(['settled', upstream, path]);
      return { status: 'ok' as const, data: { nodes: [] } };
    };
    const controller = new DecisionsController({ request, settled } as unknown as UpstreamService);
    const decision = {
      decisionId: 'decision-123',
      policyVersion: 'ppo-v1',
      action: { type: 'MIGRATE' },
      executionMode: 'shadow' as const,
    };

    await controller.approve(decision);

    assert.deepEqual(calls[3], ['safety', '/decisions/approve', {
      method: 'POST',
      body: JSON.stringify({
        decision_id: 'decision-123',
        policy_version: 'ppo-v1',
        action: { type: 'MIGRATE' },
        predicted: {},
        execution_mode: 'shadow',
        dt_fidelity: 0,
        destination_free_cpu: 0,
        destination_healthy: false,
        source_healthy: false,
      }),
    }]]);
  });

  it('maps public decision actions to the simulation contract', async () => {
    const calls: unknown[][] = [];
    const request = async (...args: unknown[]) => { calls.push(args); return { results: [] }; };
    const settled = async () => ({ status: 'ok' as const, data: { nodes: [] } });
    const controller = new DecisionsController({ request, settled } as unknown as UpstreamService);
    await controller.simulate({
      decisionId: 'decision-123',
      policyVersion: 'ppo-v1',
      action: { type: 'RESOURCE_ADJUST', cpuDelta: 0.1 },
    });
    assert.deepEqual(calls[2], ['simulation', '/simulate', {
      method: 'POST',
      body: JSON.stringify({
        nodes: [],
        candidates: [{ type: 'RESOURCE_ADJUST', cpu_delta: 0.1 }],
        predicted: {},
        dt_fidelity: 0,
      }),
    }]);
  });
});
