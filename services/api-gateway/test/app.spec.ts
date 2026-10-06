import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import assert = require('node:assert/strict');
import { after, before, describe, it } from 'node:test';
import request = require('supertest');
import { AppModule } from '../src/app.module';

describe('API gateway', () => {
  let app: INestApplication;

  before(async () => {
    process.env.DT_RAM_API_KEY = 'test-api-key';
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = moduleRef.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }));
    await app.init();
  });

  after(async () => {
    delete process.env.DT_RAM_API_KEY;
    await app.close();
  });

  it('exposes a public health endpoint', async () => {
    await request(app.getHttpServer())
      .get('/health')
      .expect(200)
      .expect({ status: 'ok', service: 'api-gateway' });
  });

  it('protects application endpoints', async () => {
    await request(app.getHttpServer()).get('/configuration').expect(401);
  });

  it('returns only non-secret configuration', async () => {
    const response = await request(app.getHttpServer())
      .get('/configuration')
      .set('x-api-key', 'test-api-key')
      .expect(200);
    assert.equal(response.body.features.directKubernetesActuation, false);
    assert.equal(JSON.stringify(response.body).includes('test-api-key'), false);
  });

  it('validates decision requests before proxying them', async () => {
    await request(app.getHttpServer())
      .post('/decisions/simulate')
      .set('x-api-key', 'test-api-key')
      .send({ decisionId: 'missing-required-fields' })
      .expect(400);
  });
});
