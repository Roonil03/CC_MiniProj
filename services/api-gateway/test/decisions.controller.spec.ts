import { DecisionsController } from '../src/decisions/decisions.controller';
import { UpstreamService } from '../src/upstream/upstream.service';
import assert = require('node:assert/strict');
import { describe, it } from 'node:test';

describe('DecisionsController safety boundary', () => {
  it('sends approval requests only to the safety service', async () => {
    const calls: unknown[][] = [];
    const request = async (...args: unknown[]) => { calls.push(args); return { approved: true }; };
    const controller = new DecisionsController({ request } as unknown as UpstreamService);
    const decision = {
      decisionId: 'decision-123',
      policyVersion: 'ppo-v1',
      action: { type: 'MIGRATE' },
      executionMode: 'shadow' as const,
    };

    await controller.approve(decision);

    assert.deepEqual(calls, [['safety', '/decisions/approve', {
      method: 'POST',
      body: JSON.stringify({
        decision_id: 'decision-123',
        policy_version: 'ppo-v1',
        action: { type: 'MIGRATE' },
        predicted: {},
        execution_mode: 'shadow',
      }),
    }]]);
  });

  it('maps public decision actions to the simulation contract', async () => {
    const calls: unknown[][] = [];
    const request = async (...args: unknown[]) => { calls.push(args); return { results: [] }; };
    const controller = new DecisionsController({ request } as unknown as UpstreamService);
    await controller.simulate({
      decisionId: 'decision-123',
      policyVersion: 'ppo-v1',
      action: { type: 'RESOURCE_ADJUST', cpuDelta: 0.1 },
    });
    assert.deepEqual(calls[0], ['simulation', '/simulate', {
      method: 'POST',
      body: JSON.stringify({ candidates: [{ type: 'RESOURCE_ADJUST', cpu_delta: 0.1 }] }),
    }]);
  });
});
