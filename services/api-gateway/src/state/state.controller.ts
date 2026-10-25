import { Controller, Get } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { UpstreamService } from '../upstream/upstream.service';

@ApiTags('state')
@ApiSecurity('api-key')
@Controller()
export class StateController {
  constructor(private readonly upstream: UpstreamService) {}

  @Get('nodes')
  nodes() {
    return this.upstream.request('infrastructure', '/infrastructure/nodes');
  }

  @Get('services')
  services() {
    return this.upstream.request('infrastructure', '/infrastructure/pods');
  }

  @Get('twin/state')
  twinState() {
    return this.upstream.request('twin', '/twin/state');
  }

  @Get('predictions')
  predictions() {
    return this.upstream.request('prediction', '/predictions');
  }

  @Get('policies')
  policies() {
    return this.upstream.request('safety', '/policies');
  }
}
