import { ApiProperty, PartialType, PickType } from '@nestjs/swagger';
import { IsIn, IsInt, IsNotEmpty, IsObject, IsOptional, IsString, Max, MaxLength, Min } from 'class-validator';
import { ExperimentStatus } from './experiment.model';

export class CreateExperimentDto {
  @ApiProperty({ example: 'burst-workload-ppo' })
  @IsString() @IsNotEmpty() @MaxLength(200) name!: string;

  @IsString() @IsNotEmpty() @MaxLength(128) gitCommit!: string;
  @IsString() @IsNotEmpty() @MaxLength(128) datasetVersion!: string;
  @IsString() @IsNotEmpty() @MaxLength(128) modelVersion!: string;
  @IsObject() configuration!: Record<string, unknown>;
  @IsString() @IsNotEmpty() @MaxLength(128) environment!: string;
  @IsString() @IsNotEmpty() @MaxLength(64) kubernetesVersion!: string;
  @IsObject() nodeTopology!: Record<string, unknown>;
  @IsInt() @Min(0) @Max(2147483647) randomSeed!: number;
  @IsString() @IsNotEmpty() @MaxLength(64) rlAlgorithm!: string;
  @IsObject() hyperparameters!: Record<string, unknown>;
}

export class UpdateExperimentDto extends PartialType(PickType(CreateExperimentDto, ['name'] as const)) {
  @IsOptional()
  @IsIn(['created', 'running', 'completed', 'failed', 'cancelled'])
  status?: ExperimentStatus;

  @IsOptional()
  @IsObject()
  results?: Record<string, unknown>;
}
