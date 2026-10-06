import { Body, Controller, Delete, Get, Param, Patch, Post } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { UpstreamService } from '../upstream/upstream.service';
import { CreateExperimentDto, UpdateExperimentDto } from './experiment.dto';

@ApiTags('experiments')
@ApiSecurity('api-key')
@Controller('experiments')
export class ExperimentsController {
  constructor(private readonly upstream: UpstreamService) {}

  @Post()
  create(@Body() body: CreateExperimentDto) {
    return this.upstream.request('experiments', '/experiments', { method: 'POST', body: JSON.stringify(body) });
  }

  @Get()
  list() {
    return this.upstream.request('experiments', '/experiments');
  }

  @Get(':id')
  get(@Param('id') id: string) {
    return this.upstream.request('experiments', `/experiments/${encodeURIComponent(id)}`);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() body: UpdateExperimentDto) {
    return this.upstream.request('experiments', `/experiments/${encodeURIComponent(id)}`, {
      method: 'PATCH', body: JSON.stringify(body),
    });
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.upstream.request('experiments', `/experiments/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }
}
