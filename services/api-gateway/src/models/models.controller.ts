import { Controller, Get } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { UpstreamService } from '../upstream/upstream.service';

@ApiTags('models')
@ApiSecurity('api-key')
@Controller('models')
export class ModelsController {
  constructor(private readonly upstream: UpstreamService) {}

  @Get()
  list() {
    return this.upstream.request('prediction', '/models');
  }
}
