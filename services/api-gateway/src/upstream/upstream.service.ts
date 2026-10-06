import { BadGatewayException, Injectable } from '@nestjs/common';

export type Upstream =
  | 'experiments'
  | 'infrastructure'
  | 'twin'
  | 'prediction'
  | 'simulation'
  | 'safety';

const DEFAULT_URLS: Record<Upstream, string> = {
  experiments: 'http://localhost:3001',
  infrastructure: 'http://localhost:8081',
  twin: 'http://localhost:8080',
  prediction: 'http://localhost:5000',
  simulation: 'http://localhost:5002',
  safety: 'http://localhost:5003',
};

const ENV_KEYS: Record<Upstream, string> = {
  experiments: 'EXPERIMENT_SERVICE_URL',
  infrastructure: 'INFRASTRUCTURE_CONTROLLER_URL',
  twin: 'TWIN_MANAGER_URL',
  prediction: 'PREDICTION_SERVICE_URL',
  simulation: 'SIMULATION_SERVICE_URL',
  safety: 'SAFETY_SERVICE_URL',
};

@Injectable()
export class UpstreamService {
  async request<T>(upstream: Upstream, path: string, init: RequestInit = {}): Promise<T> {
    const baseUrl = process.env[ENV_KEYS[upstream]] ?? DEFAULT_URLS[upstream];
    const headers = new Headers(init.headers);
    headers.set('accept', 'application/json');
    if (init.body !== undefined) {
      headers.set('content-type', 'application/json');
    }
    const serviceToken = process.env.DT_RAM_SERVICE_TOKEN;
    if (serviceToken) {
      headers.set('x-service-token', serviceToken);
    }

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers,
        signal: AbortSignal.timeout(5_000),
      });
      const payload = await this.readPayload(response);
      if (!response.ok) {
        throw new BadGatewayException({
          message: `The ${upstream} service rejected the request`,
          upstreamStatus: response.status,
          upstreamResponse: payload,
        });
      }
      return payload as T;
    } catch (error) {
      if (error instanceof BadGatewayException) {
        throw error;
      }
      throw new BadGatewayException(`The ${upstream} service is unavailable`);
    }
  }

  async settled(upstream: Upstream, path: string): Promise<{ status: 'ok' | 'unavailable'; data?: unknown }> {
    try {
      return { status: 'ok', data: await this.request(upstream, path) };
    } catch {
      return { status: 'unavailable' };
    }
  }

  private async readPayload(response: Response): Promise<unknown> {
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
}
