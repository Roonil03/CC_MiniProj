import { NotFoundException } from '@nestjs/common';
import assert = require('node:assert/strict');
import { beforeEach, describe, it } from 'node:test';
import { validate } from 'class-validator';
import { CreateExperimentDto } from '../src/experiments/experiment.dto';
import { Experiment } from '../src/experiments/experiment.model';
import { ExperimentRepository } from '../src/experiments/experiments.repository';
import { ExperimentsService } from '../src/experiments/experiments.service';
import { PostgresExperimentRepository } from '../src/experiments/postgres-experiment.repository';

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

  it('bounds randomSeed to the PostgreSQL integer range', async () => {
    const dto = Object.assign(new CreateExperimentDto(), { ...input, randomSeed: 2147483648 });
    const errors = await validate(dto);
    assert.ok(errors.some((error) => error.property === 'randomSeed'));
  });

  it('applies concurrent partial patches without restoring stale fields', async () => {
    const repository = new PostgresExperimentRepository();
    const row = {
      id: '7f72df78-fd0b-4ace-bef8-25b7a3e9ec29', name: 'before', status: 'created' as const,
      git_commit: 'abc', dataset_version: 'v1', model_version: 'm1', configuration: {},
      environment: 'simulation', kubernetes_version: '1.31', node_topology: {}, random_seed: 1,
      rl_algorithm: 'ppo', hyperparameters: {}, results: null,
      created_at: new Date('2026-01-01T00:00:00.000Z'), updated_at: new Date('2026-01-01T00:00:00.000Z'),
    };
    const statements: string[] = [];
    let current: Record<string, any> = { ...row };
    const fakePool = {
      query: async (sql: string, values: unknown[]) => {
        statements.push(sql);
        const updated = { ...current };
        const setClause = sql.match(/SET (.+) WHERE/)?.[1] ?? '';
        for (const [, column, parameter] of setClause.matchAll(/(\w+)=\$(\d+)/g)) {
          const value = values[Number(parameter) - 1];
          updated[column] = value;
        }
        current = updated;
        return { rows: [updated] };
      },
    };
    (repository as unknown as { pool: unknown }).pool = fakePool;

    await Promise.all([
      repository.update(row.id, { name: 'renamed' }),
      repository.update(row.id, { status: 'running' }),
    ]);

    assert.equal(current.name, 'renamed');
    assert.equal(current.status, 'running');
    assert.ok(statements.some((sql) => /SET name=\$2, updated_at/.test(sql)));
    assert.ok(statements.some((sql) => /SET status=\$2, updated_at/.test(sql)));
    assert.ok(statements.every((sql) => !/SET name=.*status=/.test(sql)));
  });
});
