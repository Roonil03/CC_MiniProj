import { Body, Controller, Post } from '@nestjs/common';
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
    const context = await this.context(decision);
    return this.upstream.request('safety', '/decisions/approve', {
      method: 'POST', body: JSON.stringify({
        ...toCanonicalDecision(decision),
        ...context.safetyContext,
      }),
    });
  }

  private async context(decision: DecisionDto) {
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
        predicted: forecast ?? decision.predicted ?? {},
        dt_fidelity: twinFidelity(nodes),
    };
    const simulationResult = await this.upstream.request<Record<string, any>>('simulation', '/simulate', {
      method: 'POST', body: JSON.stringify(simulationRequest),
    });
    const simulated = Array.isArray(simulationResult.results) ? simulationResult.results[0] : undefined;
    const predicted = simulated ? {
      cpu: simulated.predicted_cpu,
      memory: simulated.predicted_mem,
      latency: simulated.predicted_latency_ms,
      slo_violation_probability: simulated.slo_violation_prob,
      prediction_confidence: simulated.prediction_confidence ?? 0,
    } : (forecast ?? decision.predicted ?? {});
    return {
      simulationRequest,
      simulationResult,
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

function shortestForecast(value: unknown, action: Record<string, unknown>): Record<string, unknown> | undefined {
  const body = isRecord(value) ? value : {};
  const predictions = Array.isArray(body.predictions) ? body.predictions.filter(isRecord) : [];
  const nodeIds = [action.source, action.destination].filter((id): id is string => typeof id === 'string');
  const candidate = predictions
    .filter((prediction) => nodeIds.length === 0 || nodeIds.includes(String(prediction.node_id)))
    .sort((left, right) => Number(left.horizon_seconds ?? Infinity) - Number(right.horizon_seconds ?? Infinity))[0];
  if (!candidate) return undefined;
  const metric = String(candidate.metric ?? 'cpu');
  return {
    [metric]: candidate.value,
    prediction_confidence: candidate.confidence ?? 0,
    horizon_seconds: candidate.horizon_seconds,
    model_id: candidate.model_id,
  };
}

function nodeHealthy(nodes: unknown[], nodeId: unknown): boolean {
  if (typeof nodeId !== 'string') return true;
  const node = nodes.find((candidate) => isRecord(candidate) && candidate.node_id === nodeId);
  return !node || String(node.health ?? 'healthy').toLowerCase() === 'healthy';
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
    .map((node) => Number(node.fidelity))
    .filter((value) => Number.isFinite(value));
  return values.length ? Math.min(...values) : 0;
}

function toSimulationNode(node: Record<string, any>): Record<string, unknown> {
  const cpuTotal = Number(node.cpu_total ?? 8);
  const memoryTotal = Number(node.memory_total_mb ?? 16384);
  return {
    node_id: node.node_id,
    cpu: node.cpu !== undefined ? Number(node.cpu) : Number(node.cpu_used ?? 0) / Math.max(cpuTotal, 1e-9),
    memory: node.memory !== undefined ? Number(node.memory) : Number(node.memory_used_mb ?? 0) / Math.max(memoryTotal, 1e-9),
    cpu_total: cpuTotal,
    memory_total_mb: memoryTotal,
    network_in: node.network_in ?? node.network_in_mbps ?? 0,
    network_out: node.network_out ?? node.network_out_mbps ?? 0,
    health: node.health ?? 'healthy',
    fidelity: node.fidelity,
  };
}
