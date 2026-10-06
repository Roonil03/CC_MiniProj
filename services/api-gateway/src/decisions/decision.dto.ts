import { ApiProperty } from '@nestjs/swagger';
import { IsIn, IsNotEmpty, IsObject, IsOptional, IsString } from 'class-validator';

export class DecisionDto {
  @ApiProperty({ example: 'decision-123' })
  @IsString()
  @IsNotEmpty()
  decisionId!: string;

  @IsString()
  @IsNotEmpty()
  policyVersion!: string;

  @IsObject()
  action!: Record<string, unknown>;

  @IsOptional()
  @IsObject()
  predicted?: Record<string, unknown>;
}

export class ApproveDecisionDto extends DecisionDto {
  @ApiProperty({ enum: ['shadow', 'canary', 'controlled'] })
  @IsIn(['shadow', 'canary', 'controlled'])
  executionMode!: 'shadow' | 'canary' | 'controlled';
}
