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
      action: { type: 'NOOP' },
      executionMode: 'shadow' as const,
    };

    await controller.approve(decision);

    assert.deepEqual(calls[3], ['safety', '/decisions/approve', {
      method: 'POST',
      body: JSON.stringify({
        decision_id: 'decision-123',
        policy_version: 'ppo-v1',
        action: { type: 'NOOP' },
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
    assert.deepEqual(calls[0], ['simulation', '/simulate', {
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

    const body = JSON.parse(String(calls[0][2] && (calls[0][2] as { body: string }).body));
    assert.equal(body.nodes[0].cpu, 0.25);
    assert.equal(body.nodes[0].memory, 0.25);
    assert.equal(body.nodes[0].network_in, 10);
    assert.equal(body.nodes[0].stale, false);
    assert.equal(body.nodes[0].health, 'healthy');
    assert.equal(body.dt_fidelity, 0.97);
  });

  it('forwards forecast provenance and only approves a feasible applied forecast', async () => {
    const timestamp = new Date().toISOString();
    const prediction = { node_id: 'a', metric: 'cpu', origin_timestamp: timestamp,
      model_id: 'model-1', horizon_seconds: 2, value: 0.7, confidence: 0.8 };
    const calls: any[][] = [];
    const request = async (...args: any[]) => {
      calls.push(args);
      if (args[0] === 'simulation') {
        const body = JSON.parse(args[2].body);
        assert.equal(body.forecast_horizon_seconds, 2);
        assert.deepEqual(body.predicted, { forecasts: [{ node_id: 'a', metric: 'cpu', timestamp,
          source: 'model-1', horizon_seconds: 2, value: 0.7 }], prediction_confidence: 0.8 });
        return { results: [{ action_type: 'MIGRATE', feasible: true, prediction_confidence: 0.8 }],
          applied_forecasts: body.predicted.forecasts };
      }
      return { approved: true };
    };
    const settled = async (name: string) => ({ status: 'ok' as const,
      data: name === 'prediction' ? { predictions: [prediction] } : { nodes: [] } });
    const controller = new DecisionsController({ request, settled } as unknown as UpstreamService);
    assert.deepEqual(await controller.approve({ decisionId: 'id', policyVersion: 'v1',
      action: { type: 'MIGRATE', source: 'a', destination: 'b' }, executionMode: 'shadow' }), { approved: true });
    const safety = JSON.parse(calls[1][2].body);
    assert.equal(safety.predicted.prediction_confidence, 0.8);
    assert.equal(safety.dt_fidelity, 0);
    assert.equal(safety.destination_healthy, false);
  });

  it('rejects missing, infeasible, or mismatched simulation evidence without using client confidence', async () => {
    const prediction = { node_id: 'a', metric: 'cpu', origin_timestamp: new Date().toISOString(),
      model_id: 'm', horizon_seconds: 5, value: 0.5, confidence: null };
    for (const mode of ['missing', 'infeasible', 'unapplied', 'mismatch']) {
      let safetyCalled = false;
      const request = async (name: string, _path: string, options: any) => {
        if (name === 'safety') { safetyCalled = true; return {}; }
        const body = JSON.parse(options.body);
        assert.equal(body.predicted.prediction_confidence, 0);
        const applied = body.predicted.forecasts.map((f: any) => mode === 'mismatch' ? { ...f, value: 0.9 } : f);
        return { results: mode === 'missing' ? [] : [{ action_type: 'MIGRATE', feasible: mode !== 'infeasible' }],
          applied_forecasts: mode === 'unapplied' ? [] : applied };
      };
      const settled = async (name: string) => ({ status: 'ok' as const,
        data: name === 'prediction' ? { predictions: [prediction] } : { nodes: [] } });
      const controller = new DecisionsController({ request, settled } as unknown as UpstreamService);
      await assert.rejects(controller.approve({ decisionId: 'id', policyVersion: 'v',
        action: { type: 'MIGRATE', source: 'a', destination: 'b' }, predicted: { prediction_confidence: 1 }, executionMode: 'shadow' }));
      assert.equal(safetyCalled, false);
    }
  });
});
