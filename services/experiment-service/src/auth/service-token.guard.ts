import {
  CanActivate,
  ExecutionContext,
  Injectable,
  ServiceUnavailableException,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Request } from 'express';
import { IS_PUBLIC_KEY } from './public.decorator';

@Injectable()
export class ServiceTokenGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    if (this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [context.getHandler(), context.getClass()])) {
      return true;
    }
    const expected = process.env.DT_RAM_SERVICE_TOKEN;
    if (!expected) {
      throw new ServiceUnavailableException('Service authentication is not configured');
    }
    const supplied = context.switchToHttp().getRequest<Request>().header('x-service-token');
    if (supplied !== expected) {
      throw new UnauthorizedException('A valid x-service-token header is required');
    }
    return true;
  }
}
