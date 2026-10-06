import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ApiKeyGuard } from './auth/api-key.guard';
import { ConfigurationController } from './configuration/configuration.controller';
import { DashboardController } from './dashboard/dashboard.controller';
import { DecisionsController } from './decisions/decisions.controller';
import { ExperimentsController } from './experiments/experiments.controller';
import { HealthController } from './health/health.controller';
import { ModelsController } from './models/models.controller';
import { StateController } from './state/state.controller';
import { UpstreamService } from './upstream/upstream.service';

@Module({
  controllers: [
    HealthController,
    ConfigurationController,
    ExperimentsController,
    StateController,
    DecisionsController,
    ModelsController,
    DashboardController,
  ],
  providers: [
    UpstreamService,
    { provide: APP_GUARD, useClass: ApiKeyGuard },
  ],
})
export class AppModule {}
