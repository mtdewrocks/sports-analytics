import client from './client';

export const register = (
  email: string,
  password: string,
  first_name: string,
  last_name: string,
  state?: string,
  favorite_sport?: string,
  favorite_teams?: string,
) =>
  client.post('/auth/register', { email, password, first_name, last_name, state, favorite_sport, favorite_teams });

export const login = (email: string, password: string) =>
  client.post('/auth/login', { email, password });

export const getMe = () => client.get('/auth/me');
