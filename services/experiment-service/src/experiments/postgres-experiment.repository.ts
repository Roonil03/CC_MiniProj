import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { Pool, PoolConfig } from 'pg';
import { Experiment } from './experiment.model';
import { ExperimentRepository } from './experiments.repository';

interface ExperimentRow {
  id: string;
  name: string;
  status: Experiment['status'];
  git_commit: string;
  dataset_version: string;
  model_version: string;
  configuration: Record<string, unknown>;
  environment: string;
  kubernetes_version: string;
  node_topology: Record<string, unknown>;
  random_seed: number;
  rl_algorithm: string;
  hyperparameters: Record<string, unknown>;
  results: Record<string, unknown> | null;
  created_at: Date;
  updated_at: Date;
}

@Injectable()
export class PostgresExperimentRepository implements ExperimentRepository, OnModuleInit, OnModuleDestroy {
  private readonly pool: Pool;

  constructor() {
    const config: PoolConfig = {
      host: process.env.POSTGRES_HOST ?? 'localhost',
      port: Number(process.env.POSTGRES_PORT ?? 5432),
      database: process.env.POSTGRES_DB ?? 'dt_ram',
      user: process.env.POSTGRES_USER ?? 'dt_user',
      password: process.env.POSTGRES_PASSWORD,
      max: 5,
    };
    this.pool = new Pool(config);
  }

  async onModuleInit() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS experiments (
        id uuid PRIMARY KEY,
        name text NOT NULL,
        status text NOT NULL CHECK (status IN ('created', 'running', 'completed', 'failed', 'cancelled')),
        git_commit text NOT NULL,
        dataset_version text NOT NULL,
        model_version text NOT NULL,
        configuration jsonb NOT NULL,
        environment text NOT NULL,
        kubernetes_version text NOT NULL,
        node_topology jsonb NOT NULL,
        random_seed integer NOT NULL CHECK (random_seed >= 0),
        rl_algorithm text NOT NULL,
        hyperparameters jsonb NOT NULL,
        results jsonb,
        created_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL
      )
    `);
  }

  async onModuleDestroy() {
    await this.pool.end();
  }

  async create(experiment: Experiment): Promise<Experiment> {
    const result = await this.pool.query<ExperimentRow>(
      `INSERT INTO experiments (
        id, name, status, git_commit, dataset_version, model_version, configuration,
        environment, kubernetes_version, node_topology, random_seed, rl_algorithm,
        hyperparameters, results, created_at, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
      RETURNING *`,
      [
        experiment.id, experiment.name, experiment.status, experiment.gitCommit,
        experiment.datasetVersion, experiment.modelVersion, experiment.configuration,
        experiment.environment, experiment.kubernetesVersion, experiment.nodeTopology,
        experiment.randomSeed, experiment.rlAlgorithm, experiment.hyperparameters,
        experiment.results, experiment.createdAt, experiment.updatedAt,
      ],
    );
    return this.map(result.rows[0]);
  }

  async findAll(): Promise<Experiment[]> {
    const result = await this.pool.query<ExperimentRow>('SELECT * FROM experiments ORDER BY created_at DESC');
    return result.rows.map((row) => this.map(row));
  }

  async findById(id: string): Promise<Experiment | null> {
    const result = await this.pool.query<ExperimentRow>('SELECT * FROM experiments WHERE id = $1', [id]);
    return result.rows[0] ? this.map(result.rows[0]) : null;
  }

  async update(id: string, patch: Partial<Experiment>): Promise<Experiment | null> {
    const current = await this.findById(id);
    if (!current) return null;
    const next = { ...current, ...patch, updatedAt: new Date().toISOString() };
    const result = await this.pool.query<ExperimentRow>(
      `UPDATE experiments SET name=$2, status=$3, results=$4, updated_at=$5
       WHERE id=$1 RETURNING *`,
      [id, next.name, next.status, next.results, next.updatedAt],
    );
    return this.map(result.rows[0]);
  }

  async delete(id: string): Promise<boolean> {
    const result = await this.pool.query('DELETE FROM experiments WHERE id = $1', [id]);
    return result.rowCount === 1;
  }

  private map(row: ExperimentRow): Experiment {
    return {
      id: row.id,
      name: row.name,
      status: row.status,
      gitCommit: row.git_commit,
      datasetVersion: row.dataset_version,
      modelVersion: row.model_version,
      configuration: row.configuration,
      environment: row.environment,
      kubernetesVersion: row.kubernetes_version,
      nodeTopology: row.node_topology,
      randomSeed: row.random_seed,
      rlAlgorithm: row.rl_algorithm,
      hyperparameters: row.hyperparameters,
      results: row.results,
      createdAt: row.created_at.toISOString(),
      updatedAt: row.updated_at.toISOString(),
    };
  }
}
