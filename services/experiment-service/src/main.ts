import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';

export async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableShutdownHooks();
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  const swaggerConfig = new DocumentBuilder()
    .setTitle('DT-RAM Experiment Service')
    .setDescription('Reproducible experiment registry')
    .setVersion('1.0')
    .addApiKey({ type: 'apiKey', name: 'x-service-token', in: 'header' }, 'service-token')
    .build();
  SwaggerModule.setup('docs', app, SwaggerModule.createDocument(app, swaggerConfig));

  const port = Number(process.env.EXPERIMENT_SERVICE_PORT ?? 3001);
  await app.listen(port, '0.0.0.0');
  return app;
}

if (require.main === module) {
  void bootstrap();
}
