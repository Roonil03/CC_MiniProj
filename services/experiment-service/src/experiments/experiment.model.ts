export type ExperimentStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Experiment {
  id: string;
  name: string;
  status: ExperimentStatus;
  gitCommit: string;
  datasetVersion: string;
  modelVersion: string;
  configuration: Record<string, unknown>;
  environment: string;
  kubernetesVersion: string;
  nodeTopology: Record<string, unknown>;
  randomSeed: number;
  rlAlgorithm: string;
  hyperparameters: Record<string, unknown>;
  results: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
}
