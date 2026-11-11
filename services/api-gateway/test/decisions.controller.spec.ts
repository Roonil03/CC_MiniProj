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
    }]);
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

  it('normalizes Go twin utilization and freshness fields for simulation', async () => {
    const calls: unknown[][] = [];
    const request = async (...args: unknown[]) => { calls.push(args); return { results: [] }; };
    const settled = async (upstream: string) => ({
      status: 'ok' as const,
      data: upstream === 'twin' ? { nodes: [{
        node_id: 'edge-a1', cpu_total: 8, cpu_used: 2, memory_total_mb: 1000,
        memory_used_mb: 250, network_in_mbps: 10, network_out_mbps: 5,
        health: 'healthy', timestamp: new Date().toISOString(), stale: false, fidelity: 0.97,
      }] } : { predictions: [] },
    });
    const controller = new DecisionsController({ request, settled } as unknown as UpstreamService);

    await controller.simulate({
      decisionId: 'decision-123',
      policyVersion: 'ppo-v1',
      action: { type: 'NOOP', source: 'edge-a1' },
    });

    const body = JSON.parse(String(calls[2][2] && (calls[2][2] as { body: string }).body));
    assert.equal(body.nodes[0].cpu, 0.25);
    assert.equal(body.nodes[0].memory, 0.25);
    assert.equal(body.nodes[0].network_in, 10);
    assert.equal(body.nodes[0].stale, false);
    assert.equal(body.nodes[0].health, 'healthy');
    assert.equal(body.dt_fidelity, 0.97);
  });
});
