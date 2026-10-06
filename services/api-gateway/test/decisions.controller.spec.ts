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
      body: JSON.stringify(decision),
    }]]);
  });
});
