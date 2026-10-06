import { Controller, Get } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { UpstreamService } from '../upstream/upstream.service';

@ApiTags('dashboard')
@ApiSecurity('api-key')
@Controller('dashboard')
export class DashboardController {
  constructor(private readonly upstream: UpstreamService) {}

  @Get('summary')
  async summary() {
    const [nodes, services, twin, predictions] = await Promise.all([
      this.upstream.settled('infrastructure', '/nodes'),
      this.upstream.settled('infrastructure', '/services'),
      this.upstream.settled('twin', '/state'),
      this.upstream.settled('prediction', '/predictions'),
    ]);
    return {
      generatedAt: new Date().toISOString(),
      status: [nodes, services, twin, predictions].every((entry) => entry.status === 'ok')
        ? 'ok'
        : 'degraded',
      nodes,
      services,
      twin,
      predictions,
    };
  }
}
