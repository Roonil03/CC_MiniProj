import { Body, Controller, Delete, Get, Param, ParseUUIDPipe, Patch, Post } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';
import { CreateExperimentDto, UpdateExperimentDto } from './experiment.dto';
import { ExperimentsService } from './experiments.service';

@ApiTags('experiments')
@ApiSecurity('service-token')
@Controller('experiments')
export class ExperimentsController {
  constructor(private readonly experiments: ExperimentsService) {}

  @Post()
  create(@Body() body: CreateExperimentDto) {
    return this.experiments.create(body);
  }

  @Get()
  findAll() {
    return this.experiments.findAll();
  }

  @Get(':id')
  findOne(@Param('id', ParseUUIDPipe) id: string) {
    return this.experiments.findOne(id);
  }

  @Patch(':id')
  update(@Param('id', ParseUUIDPipe) id: string, @Body() body: UpdateExperimentDto) {
    return this.experiments.update(id, body);
  }

  @Delete(':id')
  remove(@Param('id', ParseUUIDPipe) id: string) {
    return this.experiments.remove(id);
  }
}
