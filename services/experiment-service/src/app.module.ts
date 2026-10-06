import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ServiceTokenGuard } from './auth/service-token.guard';
import { ExperimentsController } from './experiments/experiments.controller';
import { EXPERIMENT_REPOSITORY } from './experiments/experiments.repository';
import { ExperimentsService } from './experiments/experiments.service';
import { PostgresExperimentRepository } from './experiments/postgres-experiment.repository';
import { HealthController } from './health/health.controller';

@Module({
  controllers: [HealthController, ExperimentsController],
  providers: [
    ExperimentsService,
    PostgresExperimentRepository,
    { provide: EXPERIMENT_REPOSITORY, useExisting: PostgresExperimentRepository },
    { provide: APP_GUARD, useClass: ServiceTokenGuard },
  ],
})
export class AppModule {}
