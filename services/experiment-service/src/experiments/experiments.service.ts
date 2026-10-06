import { Inject, Injectable, NotFoundException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { CreateExperimentDto, UpdateExperimentDto } from './experiment.dto';
import { Experiment } from './experiment.model';
import { EXPERIMENT_REPOSITORY, ExperimentRepository } from './experiments.repository';

@Injectable()
export class ExperimentsService {
  constructor(@Inject(EXPERIMENT_REPOSITORY) private readonly repository: ExperimentRepository) {}

  create(dto: CreateExperimentDto): Promise<Experiment> {
    const now = new Date().toISOString();
    return this.repository.create({
      id: randomUUID(),
      ...dto,
      status: 'created',
      results: null,
      createdAt: now,
      updatedAt: now,
    });
  }

  findAll() {
    return this.repository.findAll();
  }

  async findOne(id: string) {
    const experiment = await this.repository.findById(id);
    if (!experiment) throw new NotFoundException(`Experiment ${id} was not found`);
    return experiment;
  }

  async update(id: string, dto: UpdateExperimentDto) {
    const experiment = await this.repository.update(id, dto);
    if (!experiment) throw new NotFoundException(`Experiment ${id} was not found`);
    return experiment;
  }

  async remove(id: string) {
    if (!(await this.repository.delete(id))) {
      throw new NotFoundException(`Experiment ${id} was not found`);
    }
    return { deleted: true, id };
  }
}
