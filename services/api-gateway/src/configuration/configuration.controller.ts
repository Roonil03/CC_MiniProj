import { Controller, Get } from '@nestjs/common';
import { ApiSecurity, ApiTags } from '@nestjs/swagger';

@ApiTags('configuration')
@ApiSecurity('api-key')
@Controller('configuration')
export class ConfigurationController {
  @Get()
  getConfiguration() {
    return {
      environment: process.env.NODE_ENV ?? 'development',
      features: {
        experimentRegistry: true,
        counterfactualSimulation: true,
        safetyApprovalRequired: true,
        directKubernetesActuation: false,
      },
    };
  }
}
