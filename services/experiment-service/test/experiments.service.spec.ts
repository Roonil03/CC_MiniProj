import { NotFoundException } from '@nestjs/common';
import assert = require('node:assert/strict');
import { beforeEach, describe, it } from 'node:test';
import { Experiment } from '../src/experiments/experiment.model';
import { ExperimentRepository } from '../src/experiments/experiments.repository';
import { ExperimentsService } from '../src/experiments/experiments.service';

class MemoryRepository implements ExperimentRepository {
  readonly records = new Map<string, Experiment>();
  async create(value: Experiment) { this.records.set(value.id, value); return value; }
  async findAll() { return [...this.records.values()]; }
  async findById(id: string) { return this.records.get(id) ?? null; }
  async update(id: string, patch: Partial<Experiment>) {
    const current = this.records.get(id);
    if (!current) return null;
    const updated = { ...current, ...patch };
    this.records.set(id, updated);
    return updated;
  }
  async delete(id: string) { return this.records.delete(id); }
}

const input = {
  name: 'burst-workload-ppo',
  gitCommit: 'abc1234',
  datasetVersion: 'v1',
  modelVersion: 'ppo-v1',
  configuration: { intervalSeconds: 5 },
  environment: 'simulation',
  kubernetesVersion: '1.31',
  nodeTopology: { edge: 2, cloud: 1 },
  randomSeed: 42,
  rlAlgorithm: 'ppo',
  hyperparameters: { gamma: 0.99 },
};

describe('ExperimentsService', () => {
  let repository: MemoryRepository;
  let service: ExperimentsService;

  beforeEach(() => {
    repository = new MemoryRepository();
    service = new ExperimentsService(repository);
  });

  it('records complete provenance on creation', async () => {
    const experiment = await service.create(input);
    assert.deepEqual(
      { ...experiment, id: undefined, createdAt: undefined, updatedAt: undefined },
      { ...input, status: 'created', results: null, id: undefined, createdAt: undefined, updatedAt: undefined },
    );
    assert.match(experiment.id, /^[0-9a-f-]{36}$/);
    assert.equal(experiment.createdAt, experiment.updatedAt);
  });

  it('updates status and results', async () => {
    const created = await service.create(input);
    const updated = await service.update(created.id, { status: 'completed', results: { p95Latency: 21.3 } });
    assert.equal(updated.status, 'completed');
    assert.deepEqual(updated.results, { p95Latency: 21.3 });
  });

  it('rejects unknown experiment identifiers', async () => {
    await assert.rejects(service.findOne('missing'), NotFoundException);
  });

  it('deletes an experiment', async () => {
    const created = await service.create(input);
    assert.deepEqual(await service.remove(created.id), { deleted: true, id: created.id });
    await assert.rejects(service.findOne(created.id), NotFoundException);
  });
});
