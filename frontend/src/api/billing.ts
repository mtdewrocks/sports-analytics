import client from './client';

export const getBillingStatus = () => client.get('/billing/status');
export const createCheckout = (plan: 'monthly' | 'yearly' = 'monthly') =>
  client.post('/billing/checkout', null, { params: { plan } });
export const createPortal = () => client.post('/billing/portal');
