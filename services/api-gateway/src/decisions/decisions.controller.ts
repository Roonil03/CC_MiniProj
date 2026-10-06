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
    return this.upstream.request('simulation', '/decisions/simulate', {
      method: 'POST', body: JSON.stringify(decision),
    });
  }

  @Post('approve')
  approve(@Body() decision: ApproveDecisionDto) {
    // The gateway deliberately targets the safety service, never Kubernetes or
    // the infrastructure controller. Approved actuation remains a Go concern.
    return this.upstream.request('safety', '/decisions/approve', {
      method: 'POST', body: JSON.stringify(decision),
    });
  }
}
