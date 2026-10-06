import { ApiProperty } from '@nestjs/swagger';
import { IsIn, IsInt, IsNotEmpty, IsObject, IsOptional, IsString, Min } from 'class-validator';

export class CreateExperimentDto {
  @ApiProperty({ example: 'burst-workload-ppo' })
  @IsString()
  @IsNotEmpty()
  name!: string;

  @IsString()
  @IsNotEmpty()
  gitCommit!: string;

  @IsString()
  @IsNotEmpty()
  datasetVersion!: string;

  @IsString()
  @IsNotEmpty()
  modelVersion!: string;

  @IsObject()
  configuration!: Record<string, unknown>;

  @IsString()
  @IsNotEmpty()
  environment!: string;

  @IsString()
  @IsNotEmpty()
  kubernetesVersion!: string;

  @IsObject()
  nodeTopology!: Record<string, unknown>;

  @IsInt()
  @Min(0)
  randomSeed!: number;

  @IsString()
  @IsNotEmpty()
  rlAlgorithm!: string;

  @IsObject()
  hyperparameters!: Record<string, unknown>;
}

export class UpdateExperimentDto {
  @IsOptional() @IsString() @IsNotEmpty() name?: string;
  @IsOptional() @IsIn(['created', 'running', 'completed', 'failed', 'cancelled']) status?: string;
  @IsOptional() @IsObject() results?: Record<string, unknown>;
}
