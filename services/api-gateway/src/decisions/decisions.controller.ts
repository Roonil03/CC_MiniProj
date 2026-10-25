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
  simulate(@Body() decision: DecisionDto) {
    return this.upstream.request('simulation', '/simulate', {
      method: 'POST', body: JSON.stringify({
        candidates: [toCanonicalAction(decision.action)],
        predicted: decision.predicted,
      }),
    });
  }

  @Post('approve')
  approve(@Body() decision: ApproveDecisionDto) {
    // The gateway deliberately targets the safety service, never Kubernetes or
    // the infrastructure controller. Approved actuation remains a Go concern.
    return this.upstream.request('safety', '/decisions/approve', {
      method: 'POST', body: JSON.stringify(toCanonicalDecision(decision)),
    });
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
