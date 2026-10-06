import { Experiment } from './experiment.model';

export const EXPERIMENT_REPOSITORY = Symbol('EXPERIMENT_REPOSITORY');

export interface ExperimentRepository {
  create(experiment: Experiment): Promise<Experiment>;
  findAll(): Promise<Experiment[]>;
  findById(id: string): Promise<Experiment | null>;
  update(id: string, patch: Partial<Experiment>): Promise<Experiment | null>;
  delete(id: string): Promise<boolean>;
}
