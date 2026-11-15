import { Body, Controller, Post, UnprocessableEntityException } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { UpstreamService } from '../upstream/upstream.service';
import { ApproveDecisionDto, DecisionDto } from './decision.dto';

@ApiTags('decisions')
@ApiSecurity('api-key')
@Controller('decisions')
export class DecisionsController {
  constructor(private readonly upstream: UpstreamService) {}

  @Post('simulate')
  async simulate(@Body() decision: DecisionDto) {
    const context = await this.context(decision);
    return context.simulationResult;
  }

  @Post('approve')
  async approve(@Body() decision: ApproveDecisionDto) {
    // The gateway deliberately targets the safety service, never Kubernetes or
    // the infrastructure controller. Approved actuation remains a Go concern.
    const context = await this.context(decision, true);
    const actionType = String(decision.action.type ?? '').toUpperCase();
    if (actionType !== 'NOOP') {
      const result = context.simulationResult;
      const simulated = Array.isArray(result?.results) ? result.results[0] : undefined;
      const applied = Array.isArray(result?.applied_forecasts) ? result.applied_forecasts : [];
      const sent = context.forecast?.predicted.forecasts ?? [];
      const matches = ['MIGRATE', 'PLACE'].includes(actionType) &&
        typeof decision.action.destination === 'string' && !!decision.action.destination &&
        applied.some((item: unknown) => isRecord(item) && item.node_id === decision.action.destination &&
        ['cpu', 'memory'].includes(item.metric) && sent.some((forecast) =>
        ['node_id', 'metric', 'timestamp', 'source', 'horizon_seconds', 'value'].every((key) => item[key] === forecast[key])));
      if (!isRecord(simulated) || simulated.feasible !== true ||
          String(simulated.action_type ?? '').toUpperCase() !== actionType || !matches) {
        throw new UnprocessableEntityException({ approved: false, reasons: ['counterfactual simulation is infeasible or lacks a matching applied forecast'] });
      }
    }
    return this.upstream.request('safety', '/decisions/approve', {
      method: 'POST', body: JSON.stringify({
        ...toCanonicalDecision(decision),
        ...context.safetyContext,
      }),
    });
  }

  private async context(decision: DecisionDto, approval = false) {
    const [twin, predictions] = await Promise.all([
      this.upstream.settled('twin', '/twin/state'),
      this.upstream.settled('prediction', '/predictions'),
    ]);
    const twinBody = isRecord(twin.data) ? twin.data : {};
    const nodes = (Array.isArray(twinBody.nodes) ? twinBody.nodes : []).filter(isRecord).map(toSimulationNode);
    const forecast = shortestForecast(predictions.data, decision.action);
    const action = toCanonicalAction(decision.action);
    const simulationRequest = {
        nodes,
        candidates: [action],
        predicted: forecast?.predicted ?? (approval ? {} : decision.predicted ?? {}),
        ...(forecast ? { forecast_horizon_seconds: forecast.horizon } : {}),
        dt_fidelity: twinFidelity(nodes),
    };
    const simulationResult = await this.upstream.request<Record<string, any>>('simulation', '/simulate', {
      method: 'POST', body: JSON.stringify(simulationRequest),
    });
    const simulated = Array.isArray(simulationResult?.results) ? simulationResult.results[0] : undefined;
    const predicted = simulated ? {
      cpu: simulated.predicted_cpu,
      memory: simulated.predicted_mem,
      latency: simulated.predicted_latency_ms,
      slo_violation_probability: simulated.slo_violation_prob,
      prediction_confidence: simulated.prediction_confidence ?? 0,
    } : (approval ? {} : decision.predicted ?? {});
    return {
      simulationRequest,
      simulationResult,
      forecast,
      safetyContext: {
        dt_fidelity: twinFidelity(nodes),
        destination_free_cpu: destinationFreeCpu(nodes, action.destination),
        destination_healthy: nodeHealthy(nodes, action.destination),
        source_healthy: nodeHealthy(nodes, action.source),
        predicted,
      },
    };
  }
}

function toCanonicalAction(action: Record<string, unknown>): Record<string, unknown> {
  const canonical: Record<string, unknown> = { ...action };
  const aliases: Record<string, string> = {
    serviceId: 'service',
    cpuDelta: 'cpu_delta',
    memoryDelta: 'memory_delta_mb',
  };
  for (const [from, to] of Object.entries(aliases)) {
    if (canonical[to] === undefined && canonical[from] !== undefined) canonical[to] = canonical[from];
    delete canonical[from];
  }
  return canonical;
}

function toCanonicalDecision(decision: ApproveDecisionDto): Record<string, unknown> {
  return {
    decision_id: decision.decisionId,
    policy_version: decision.policyVersion,
    action: toCanonicalAction(decision.action),
    predicted: decision.predicted ?? {},
    execution_mode: decision.executionMode,
  };
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function shortestForecast(value: unknown, action: Record<string, unknown>): { predicted: { forecasts: Record<string, unknown>[]; prediction_confidence: number }; horizon: number } | undefined {
  const body = isRecord(value) ? value : {};
  const type = String(action.type ?? '').toUpperCase();
  const relevant = ['MIGRATE', 'PLACE'].includes(type) ? [action.destination] : [action.source, action.destination];
  const nodeIds = relevant.filter((id): id is string => typeof id === 'string' && !!id);
  const predictions = (Array.isArray(body.predictions) ? body.predictions.filter(isRecord) : [])
    .filter((p) => nodeIds.includes(p.node_id) && ['cpu', 'memory'].includes(p.metric) &&
      typeof p.origin_timestamp === 'string' && /(?:Z|[+-]\d\d:\d\d)$/i.test(p.origin_timestamp) && Number.isFinite(Date.parse(p.origin_timestamp)) &&
      typeof p.model_id === 'string' && !!p.model_id && Number.isInteger(p.horizon_seconds) && p.horizon_seconds > 0 && p.horizon_seconds <= 3600 &&
      typeof p.value === 'number' && Number.isFinite(p.value) && p.value >= 0 && p.value <= 1)
    .sort((a, b) => a.horizon_seconds - b.horizon_seconds);
  if (!predictions.length) return undefined;
  const horizon = predictions[0].horizon_seconds;
  const seen = new Set<string>();
  const selected = predictions.filter((p) => {
    const key = `${p.node_id}:${p.metric}`;
    if (p.horizon_seconds !== horizon || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return {
    horizon,
    predicted: {
      forecasts: selected.map((p) => ({ node_id: p.node_id, metric: p.metric, timestamp: p.origin_timestamp,
        source: p.model_id, horizon_seconds: p.horizon_seconds, value: p.value })),
      prediction_confidence: Math.min(...selected.map((p) =>
        typeof p.confidence === 'number' && Number.isFinite(p.confidence) && p.confidence >= 0 && p.confidence <= 1 ? p.confidence : 0)),
    },
  };
}

function nodeHealthy(nodes: unknown[], nodeId: unknown): boolean {
  if (typeof nodeId !== 'string' || !nodeId) return false;
  const node = nodes.find((candidate) => isRecord(candidate) && candidate.node_id === nodeId);
  return isRecord(node) && node.stale === false && String(node.health ?? 'unknown').toLowerCase() === 'healthy';
}

function destinationFreeCpu(nodes: unknown[], nodeId: unknown): number {
  if (typeof nodeId !== 'string') return 0;
  const node = nodes.find((candidate) => isRecord(candidate) && candidate.node_id === nodeId);
  if (!isRecord(node)) return 0;
  if (typeof node.free_cpu_cores === 'number') return node.free_cpu_cores;
  return Math.max(0, Number(node.cpu_total ?? 0) - Number(node.cpu_used ?? 0));
}

function twinFidelity(nodes: unknown[]): number {
  const values = nodes
    .filter(isRecord)
    .map((node) => node.stale === false ? Number(node.fidelity) : 0)
    .filter((value) => Number.isFinite(value));
  return values.length ? Math.min(...values) : 0;
}

function toSimulationNode(node: Record<string, any>): Record<string, unknown> {
  const cpuTotal = Number(node.cpu_total ?? 8);
  const memoryTotal = Number(node.memory_total_mb ?? 16384);
  const stale = isNodeStale(node);
  return {
    node_id: node.node_id,
    cpu: node.cpu !== undefined ? Number(node.cpu) : Number(node.cpu_used ?? 0) / Math.max(cpuTotal, 1e-9),
    cpu_used: node.cpu_used !== undefined ? Number(node.cpu_used) : Number(node.cpu ?? 0) * cpuTotal,
    memory: node.memory !== undefined ? Number(node.memory) : Number(node.memory_used_mb ?? 0) / Math.max(memoryTotal, 1e-9),
    memory_used_mb: node.memory_used_mb !== undefined ? Number(node.memory_used_mb) : Number(node.memory ?? 0) * memoryTotal,
    cpu_total: cpuTotal,
    memory_total_mb: memoryTotal,
    network_in: node.network_in ?? node.network_in_mbps ?? 0,
    network_out: node.network_out ?? node.network_out_mbps ?? 0,
    health: stale ? 'unknown' : node.health ?? 'unknown',
    timestamp: node.timestamp,
    stale,
    fidelity: node.fidelity,
  };
}

function isNodeStale(node: Record<string, any>, now = Date.now()): boolean {
  if (node.stale === true) return true;
  if (typeof node.timestamp !== 'string') return true;
  const timestamp = Date.parse(node.timestamp);
  // Match the twin manager's default five-second freshness window. Invalid,
  // missing, or future timestamps are unsafe to treat as current state.
  return !Number.isFinite(timestamp) || timestamp > now || now - timestamp > 5_000;
}
